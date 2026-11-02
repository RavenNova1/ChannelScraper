# -*- coding: utf-8 -*-
"""ChannelScraper Web Application & REST API Server.

Supports:
- Completely isolated workspaces per run in runs/<run_id>/ (no overlapping)
- Instant run switching & run history management
- 1-Click Complete Auto-Pipeline (runs stages 1 -> 2 -> 3 -> 4 -> 5)
- Fast multi-threaded caption fetching with ETA & progress
- Real-time event streaming and Windows shell integration
"""

import json
import os
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pipeline

ROOT = pipeline.ROOT
CORE_DIR = pipeline.CORE_DIR
UI_PATH = os.path.join(CORE_DIR, "ui", "index.html") if os.path.exists(os.path.join(CORE_DIR, "ui", "index.html")) else os.path.join(ROOT, "ui", "index.html")
YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"

LOCK = threading.Lock()
STOP = threading.Event()
WORKER = None
WORKER_MODE = "idle"  # "stage" or "pipeline"
RUN_WORKERS_COUNT = 4

LOG = deque(maxlen=600)
STATE = {
    "running": False,
    "mode": "idle",
    "stage": 0,
    "error": "",
    "ytdlp": "",
    "active_run": "",
    "pipeline_progress": 0,
}


def log(msg):
    msg = (msg or "").rstrip()
    if not msg:
        return
    line = "%s  %s" % (time.strftime("%H:%M:%S"), msg)
    LOG.append(line)
    ws = pipeline.get_active_workspace()
    if ws:
        ws.log(msg)


def ensure_ytdlp():
    exe = pipeline.YTDLP
    if os.path.exists(exe) and os.path.getsize(exe) > 1000000:
        return True
    log("yt-dlp غير موجود — جاري تنزيله تلقائيًا…")
    os.makedirs(pipeline.BIN, exist_ok=True)
    tmp = exe + ".part"
    try:
        with urllib.request.urlopen(YTDLP_URL, timeout=120) as r, open(tmp, "wb") as fh:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                fh.write(chunk)
        os.replace(tmp, exe)
        log("تم تنزيل yt-dlp بنجاح.")
        return True
    except Exception as exc:
        log("تعذّر تنزيل yt-dlp: %s" % exc)
        return False


def ytdlp_version():
    try:
        p = __import__("subprocess").run(
            [pipeline.YTDLP, "--version"], capture_output=True, text=True,
            creationflags=pipeline.CREATE_NO_WINDOW, timeout=30)
        return (p.stdout or "").strip().splitlines()[0] if p.stdout else ""
    except Exception:
        return ""


def human_time(sec):
    sec = max(0, int(sec or 0))
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    if h:
        return "%d س %02d د" % (h, m)
    if m:
        return "%d د" % m
    return "%d ث" % s


# --------------------------------------------------------------------------
# Stage Runners (against the Active Workspace)
# --------------------------------------------------------------------------
STAGES_INFO = [
    (1, "قائمة الفيديوهات", "استخراج عناوين الفيديوهات ومدتها من الرابط."),
    (2, "تحميل التفريغات", "تنزيل التفريغ الآلي بالتوازي مع استكمال المتوقف."),
    (3, "تجهيز الكلمات", "تحويل التفريغات إلى كلمات وتوقيتات بالثانية."),
    (4, "دمج الملفات", "إنتاج الملف المنسق للقراءة والملف الخام للبحث."),
    (5, "صفحة البحث", "بناء تطبيق البحث التفاعلي المستقل بدون إنترنت."),
]

STAGE_STATES = {}


def set_stage_state(n, **kw):
    with LOCK:
        cur = STAGE_STATES.setdefault(str(n), {})
        cur.update(kw)
        return dict(cur)


def run_stage1_worker(ws, target_url):
    set_stage_state(1, status="running", done=0, total=0, eta=0, note="جاري جلب القائمة…")
    log("المرحلة 1: الهدف %s" % target_url)

    def on_line(line):
        if line and not line.startswith("{"):
            log(line)

    n = ws.stage_list(target_url, on_line, STOP)
    if STOP.is_set():
        set_stage_state(1, status="ready", note="توقفت")
        return False

    vids = ws.load_videos()
    meta = ws.load_meta()
    meta["target"] = target_url
    meta["video_count"] = len(vids)

    # Detect channel title from first line if available
    try:
        with open(ws.channel_json, encoding="utf-8") as fh:
            first = json.loads(fh.readline() or "{}")
        for key in ("channel", "uploader", "playlist_channel", "playlist_uploader", "playlist_title"):
            if first.get(key):
                meta["title"] = first[key].strip()
                break
    except Exception:
        pass

    ws.save_meta(meta)
    stats = ws.get_stats()
    log("تم جلب %d فيديو (إجمالي %.1f ساعة)" % (stats["videos"], stats["hours"]))
    set_stage_state(1, status="done", done=stats["videos"], total=stats["videos"],
                    note="%d فيديو · %.1f ساعة" % (stats["videos"], stats["hours"]), eta=0)
    return True


def run_stage2_worker(ws, workers=4):
    vids = ws.load_videos()
    if not vids:
        set_stage_state(2, status="error", note="يجب تنفيذ المرحلة الأولى أولاً")
        return False

    total = len(vids)
    have_before = sum(1 for v in vids if ws.caption_path(v[0]))
    todo_count = total - have_before

    log("المرحلة 2: تحميل التفريغات (%d متبقٍ من %d) باستخدام %d مسارات بالتوازي…"
        % (todo_count, total, workers))
    set_stage_state(2, status="running", done=have_before, total=total, eta=0,
                    note="جاري التنزيل بالتوازي…")

    def on_progress(done, tot, eta, cur_title):
        set_stage_state(2, done=done, total=tot, eta=eta,
                        note="%d من %d · باقي %s" % (done, tot, human_time(eta)))

    current_have, failed_count = ws.fetch_captions_parallel(
        on_progress=on_progress, on_log=log, stop_event=STOP, max_workers=workers
    )

    if STOP.is_set():
        set_stage_state(2, status="ready", done=current_have, total=total, eta=0,
                        note="توقفت — يمكن الاستكمال في أي وقت")
        return False

    note_text = "%d من %d" % (current_have, total)
    if failed_count:
        note_text += " (%d بلا تفريغ)" % failed_count
    log("المرحلة 2 اكتملت: %s" % note_text)
    set_stage_state(2, status="done", done=current_have, total=total, eta=0, note=note_text)
    return True


def run_stage3_worker(ws):
    vids = ws.load_videos()
    if not vids:
        set_stage_state(3, status="error", note="يجب تنفيذ المرحلة الأولى أولاً")
        return False

    total = len(vids)
    have_before = sum(1 for v in vids if os.path.exists(ws.words_path(v[0])))
    todo_count = sum(1 for v in vids if ws.caption_path(v[0]) and not os.path.exists(ws.words_path(v[0])))

    log("المرحلة 3: تجهيز الكلمات والتوقيتات (%d فيديو)…" % todo_count)
    set_stage_state(3, status="running", done=have_before, total=total, eta=0, note="جاري معالجة الكلمات…")

    def on_progress(done, tot, eta, title):
        set_stage_state(3, done=done, total=tot, eta=eta,
                        note="%d من %d · باقي %s" % (done, tot, human_time(eta)))

    current_have, empty_count = ws.build_all_words_parallel(
        on_progress=on_progress, on_log=log, stop_event=STOP
    )

    if STOP.is_set():
        set_stage_state(3, status="ready", done=current_have, total=total, eta=0, note="توقفت")
        return False

    log("المرحلة 3 اكتملت: %d فيديو جاهز" % current_have)
    set_stage_state(3, status="done", done=current_have, total=total, eta=0,
                    note="%d من %d جاهز" % (current_have, total))
    return True


def run_stage4_worker(ws):
    vids = ws.load_videos()
    ready = [v for v in vids if os.path.exists(ws.words_path(v[0]))]
    if not ready:
        set_stage_state(4, status="error", note="لا توجد كلمات مجهزة بعد")
        return False

    set_stage_state(4, status="running", done=0, total=len(ready), eta=0, note="جاري دمج الملفات…")
    log("المرحلة 4: دمج تفريغ %d فيديو…" % len(ready))

    un, fo, stats = ws.merge_outputs()
    size_u = os.path.getsize(un) / 1048576.0
    size_f = os.path.getsize(fo) / 1048576.0
    log("تم دمج: %s (%.1f م.ب) · %s (%.1f م.ب) · %s كلمة" %
        (os.path.basename(un), size_u, os.path.basename(fo), size_f, f"{stats['words']:,}"))

    # Mirror to root output folder for convenience
    try:
        import shutil
        os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)
        shutil.copy2(un, os.path.join(ROOT, "output", os.path.basename(un)))
        shutil.copy2(fo, os.path.join(ROOT, "output", os.path.basename(fo)))
    except Exception:
        pass

    set_stage_state(4, status="done", done=stats["videos"], total=stats["videos"], eta=0,
                    note="%d فيديو · %s كلمة" % (stats["videos"], f"{stats['words']:,}"))
    return True


def run_stage5_worker(ws):
    set_stage_state(5, status="running", done=0, total=1, eta=0, note="جاري بناء صفحة البحث…")
    log("المرحلة 5: بناء صفحة search.html…")

    try:
        v, lines, size = ws.build_search_page(compress=True)
        size_mb = size / 1048576.0
        log("صفحة البحث جاهزة: %d فيديو · %d مقطعًا · %.1f م.ب" % (v, lines, size_mb))

        # Mirror to root output folder
        try:
            import shutil
            page_src = os.path.join(ws.out_dir, "search.html")
            os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)
            shutil.copy2(page_src, os.path.join(ROOT, "output", "search.html"))
        except Exception:
            pass

        set_stage_state(5, status="done", done=1, total=1, eta=0,
                        note="%d فيديو · %d مقطعًا · %.1f م.ب" % (v, lines, size_mb))
        return True
    except Exception as exc:
        set_stage_state(5, status="error", note=str(exc))
        raise


def run_full_pipeline_worker(ws, target_url, workers=4, auto_open=True):
    """Executes Stages 1 through 5 seamlessly from start to finish."""
    log("=" * 60)
    log("بدء التشغيل الكامل التلقائي للتشغيل [%s]" % ws.id)
    t_start = time.time()

    try:
        # Stage 1: List videos (if not already listed or if new target given)
        vids = ws.load_videos()
        if not vids or target_url:
            target = target_url or ws.load_meta().get("target")
            if not target:
                raise ValueError("يرجى كتابة رابط القناة أو الفيديو أولاً.")
            ok = run_stage1_worker(ws, target)
            if not ok or STOP.is_set():
                return

        # Stage 2: Download captions
        ok = run_stage2_worker(ws, workers=workers)
        if not ok or STOP.is_set():
            return

        # Stage 3: Process words
        ok = run_stage3_worker(ws)
        if not ok or STOP.is_set():
            return

        # Stage 4: Merge outputs
        ok = run_stage4_worker(ws)
        if not ok or STOP.is_set():
            return

        # Stage 5: Build search page
        ok = run_stage5_worker(ws)
        if not ok or STOP.is_set():
            return

        total_time = human_time(time.time() - t_start)
        log("🎉 مبروك! اكتملت جميع المراحل بنجاح في %s!" % total_time)

        # Update meta status
        meta = ws.load_meta()
        meta["status"] = "completed"
        meta["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        ws.save_meta(meta)

        # Auto open search.html if requested
        stats = ws.get_stats()
        if auto_open and stats["page_exists"]:
            log("فتح صفحة البحث في المتصفح…")
            webbrowser.open("file:///" + stats["page_path"].replace("\\", "/"))

    except Exception as exc:
        log("حدث خطأ أثناء التشغيل الكامل: %s" % exc)
        log(traceback.format_exc()[-1000:])
        with LOCK:
            STATE["error"] = str(exc)


def execute_background_job(job_fn, mode="stage", stage_num=0):
    global WORKER, WORKER_MODE
    STOP.clear()
    with LOCK:
        STATE["running"] = True
        STATE["mode"] = mode
        STATE["stage"] = stage_num
        STATE["error"] = ""

    def runner():
        global WORKER
        started = time.time()
        try:
            job_fn()
        except Exception as exc:
            log("خطأ غير متوقع: %s" % exc)
            with LOCK:
                STATE["error"] = str(exc)
        finally:
            with LOCK:
                STATE["running"] = False
                STATE["mode"] = "idle"
                STATE["stage"] = 0
            log("انتهت المهمة في %s" % human_time(time.time() - started))
            WORKER = None

    WORKER = threading.Thread(target=runner, daemon=True)
    WORKER.start()


# --------------------------------------------------------------------------
# State View Generator
# --------------------------------------------------------------------------
def refresh_stage_states_from_disk(ws):
    stats = ws.get_stats()
    vids_count = stats["videos"]

    def put(n, status, **kw):
        cur = STAGE_STATES.setdefault(str(n), {})
        if cur.get("status") in ("running", "error") and STATE["running"]:
            return
        cur.update(status=status, **kw)

    if vids_count > 0:
        put(1, "done", done=vids_count, total=vids_count,
            note="%d فيديو · %.1f ساعة" % (vids_count, stats["hours"]))

        # Check failed videos count from failed.tsv
        failed_count = 0
        if os.path.exists(ws.failed_path):
            try:
                with open(ws.failed_path, encoding="utf-8") as fh:
                    failed_count = sum(1 for line in fh if line.strip())
            except Exception:
                pass

        stage2_done = (stats["captions"] + failed_count >= vids_count) or (stats["captions"] >= vids_count)
        stage3_done = (stats["words"] >= stats["captions"] and stats["captions"] > 0)

        put(2, "done" if stage2_done else ("ready" if stats["captions"] > 0 else "idle"),
            done=stats["captions"], total=vids_count,
            note="%d من %d محمّل%s" % (stats["captions"], vids_count, (" · %d بلا تفريغ" % failed_count) if failed_count else ""))
        put(3, "done" if stage3_done else ("ready" if stats["words"] > 0 else "idle"),
            done=stats["words"], total=vids_count,
            note="%d من %d جاهز" % (stats["words"], vids_count))
    else:
        put(1, "idle", note="")
        put(2, "idle", note="")
        put(3, "idle", note="")

    put(4, "done" if stats["unformatted_exists"] else "idle",
        note=pipeline.safe_name(stats["sizes"]["unformatted"] and ("%.1f م.ب" % (stats["sizes"]["unformatted"] / 1048576.0)) or ""))
    put(5, "done" if stats["page_exists"] else "idle",
        note=pipeline.safe_name(stats["sizes"]["page"] and ("%.1f م.ب" % (stats["sizes"]["page"] / 1048576.0)) or ""))

    if not STATE["running"] and stats["page_exists"]:
        STATE["error"] = ""


def get_full_state():
    ws = pipeline.get_active_workspace()
    if ws:
        refresh_stage_states_from_disk(ws)
        meta = ws.load_meta()
        stats = ws.get_stats()
        active_id = ws.id
    else:
        meta = {}
        stats = {}
        active_id = ""

    with LOCK:
        stages_view = [
            dict(id=i, title=t, desc=d, **STAGE_STATES.get(str(i), {"status": "idle"}))
            for i, t, d in STAGES_INFO
        ]
        return {
            "running": STATE["running"],
            "mode": STATE["mode"],
            "stage": STATE["stage"],
            "error": STATE["error"],
            "ytdlp": STATE["ytdlp"],
            "active_run": active_id,
            "meta": meta,
            "stats": stats,
            "stages": stages_view,
            "runs": pipeline.list_runs(),
            "log": list(LOG)[-160:],
            "clock": time.time(),
        }


# --------------------------------------------------------------------------
# HTTP Server & API Dispatcher
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "ChannelScraper/2.0"

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            try:
                with open(UI_PATH, encoding="utf-8") as fh:
                    self._send(200, fh.read(), "text/html; charset=utf-8")
            except OSError as exc:
                self._send(500, "واجهة المستخدم غير موجودة: %s" % exc, "text/plain; charset=utf-8")
            return

        if path == "/api/state":
            self._json(get_full_state())
            return

        if path == "/api/runs":
            self._json({"runs": pipeline.list_runs(), "active": pipeline.get_active_run_id()})
            return

        self._send(404, '{"error":"not found"}')

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            body = {}

        # 1-Click Complete Pipeline Execution
        if path == "/api/run_pipeline":
            with LOCK:
                if STATE["running"]:
                    self._json({"ok": False, "msg": "توجد عملية قيد التنفيذ حالياً"}, 400)
                    return
            target = (body.get("target") or "").strip()
            workers = int(body.get("workers") or RUN_WORKERS_COUNT)
            auto_open = bool(body.get("auto_open", True))
            ws = pipeline.get_active_workspace()

            # If user specified a new target or asked for a fresh run, create run
            new_run_name = (body.get("name") or "").strip()
            if body.get("create_new"):
                if not target:
                    self._json({"ok": False, "msg": "اكتب رابط القناة أو الفيديو أولاً"}, 400)
                    return
                copy_from = body.get("copy_captions_from")
                ws = pipeline.create_run(target, new_run_name, copy_captions_from=copy_from)

            execute_background_job(
                lambda: run_full_pipeline_worker(ws, target, workers=workers, auto_open=auto_open),
                mode="pipeline"
            )
            self._json({"ok": True, "run_id": ws.id})
            return

        # Granular Single Stage Execution
        if path == "/api/run":
            with LOCK:
                if STATE["running"]:
                    self._json({"ok": False, "msg": "توجد عملية قيد التنفيذ حالياً"}, 400)
                    return
            n = int(body.get("stage") or 0)
            target = (body.get("target") or "").strip()
            workers = int(body.get("workers") or RUN_WORKERS_COUNT)
            ws = pipeline.get_active_workspace()

            if n == 1:
                if not target:
                    target = ws.load_meta().get("target")
                if not target:
                    self._json({"ok": False, "msg": "اكتب رابط القناة أو الفيديو أولاً"}, 400)
                    return
                execute_background_job(lambda: run_stage1_worker(ws, target), mode="stage", stage_num=1)
            elif n == 2:
                execute_background_job(lambda: run_stage2_worker(ws, workers=workers), mode="stage", stage_num=2)
            elif n == 3:
                execute_background_job(lambda: run_stage3_worker(ws), mode="stage", stage_num=3)
            elif n == 4:
                execute_background_job(lambda: run_stage4_worker(ws), mode="stage", stage_num=4)
            elif n == 5:
                execute_background_job(lambda: run_stage5_worker(ws), mode="stage", stage_num=5)
            else:
                self._json({"ok": False, "msg": "مرحلة غير معروفة"}, 400)
                return

            self._json({"ok": True})
            return

        # Stop
        if path == "/api/stop":
            STOP.set()
            log("تم إرسال طلب إيقاف…")
            self._json({"ok": True})
            return

        # Run Management
        if path == "/api/runs/create":
            target = (body.get("target") or "").strip()
            if not target:
                self._json({"ok": False, "msg": "اكتب رابط القناة أو الفيديو أولاً"}, 400)
                return
            custom_name = (body.get("name") or "").strip()
            copy_from = body.get("copy_captions_from")
            try:
                ws = pipeline.create_run(target, custom_name, copy_captions_from=copy_from)
                log("تم إنشاء تشغيل جديد ومستقل: %s" % ws.id)
                self._json({"ok": True, "run_id": ws.id})
            except Exception as exc:
                self._json({"ok": False, "msg": str(exc)}, 400)
            return

        if path == "/api/runs/select":
            run_id = (body.get("run_id") or "").strip()
            runs = [r["id"] for r in pipeline.list_runs()]
            if run_id in runs:
                pipeline.set_active_run(run_id)
                log("تم التبديل إلى التشغيل: %s" % run_id)
                self._json({"ok": True})
            else:
                self._json({"ok": False, "msg": "التشغيل غير موجود"}, 404)
            return

        if path == "/api/runs/delete":
            run_id = (body.get("run_id") or "").strip()
            with LOCK:
                if STATE["running"] and STATE["active_run"] == run_id:
                    self._json({"ok": False, "msg": "لا يمكن حذف تشغيل قيد التنفيذ حالياً"}, 400)
                    return
            pipeline.delete_run(run_id)
            log("تم حذف التشغيل: %s" % run_id)
            self._json({"ok": True})
            return

        # Open outputs / folder
        if path == "/api/open":
            what = body.get("what") or "folder"
            run_id = body.get("run_id") or pipeline.get_active_run_id()
            ws = pipeline.Workspace(os.path.join(pipeline.RUNS_DIR, run_id)) if run_id else pipeline.get_active_workspace()

            if what == "page":
                page = os.path.join(ws.out_dir, "search.html")
                if os.path.exists(page):
                    webbrowser.open("file:///" + page.replace("\\", "/"))
                else:
                    self._json({"ok": False, "msg": "صفحة البحث لم تُنشأ بعد"}, 400)
                    return
            elif what == "formatted":
                fo = os.path.join(ws.out_dir, ws.output_name() + "_formatted.txt")
                if os.path.exists(fo):
                    os.startfile(fo)
                else:
                    os.startfile(ws.out_dir)
            elif what == "unformatted":
                un = os.path.join(ws.out_dir, ws.output_name() + "_unformatted.txt")
                if os.path.exists(un):
                    os.startfile(un)
                else:
                    os.startfile(ws.out_dir)
            elif what == "output":
                os.startfile(ws.out_dir)
            elif what == "folder":
                os.startfile(ws.root)
            self._json({"ok": True})
            return

        # Update yt-dlp
        if path == "/api/update":
            with LOCK:
                if STATE["running"]:
                    self._json({"ok": False, "msg": "توجد عملية قيد التنفيذ حالياً"}, 400)
                    return
                STATE["running"] = True

            def job():
                try:
                    ensure_ytdlp()
                    log("جاري تحديث yt-dlp…")
                    pipeline.run_stream([pipeline.YTDLP, "-U"], log)
                    with LOCK:
                        STATE["ytdlp"] = ytdlp_version()
                    log("إصدار yt-dlp الحالي: %s" % STATE["ytdlp"])
                finally:
                    with LOCK:
                        STATE["running"] = False

            threading.Thread(target=job, daemon=True).start()
            self._json({"ok": True})
            return

        self._send(404, '{"error":"not found"}')


def pick_port(preferred=8760):
    import socket
    for port in range(preferred, preferred + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return 0


def check_already_running(preferred=8760):
    """If ChannelScraper is already running, open browser and return True."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/state" % preferred, timeout=0.8) as r:
            if r.status == 200:
                return True
    except Exception:
        pass
    return False


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    port = 8760
    if "--force" not in sys.argv and check_already_running(port):
        url = "http://127.0.0.1:%d/" % port
        print("==================================================")
        print(" ChannelScraper 2.0 is already running!")
        print(" Opening dashboard: %s" % url)
        print("==================================================")
        if "--no-browser" not in sys.argv:
            webbrowser.open(url)
        return

    ensure_ytdlp()
    with LOCK:
        STATE["ytdlp"] = ytdlp_version()

    port = pick_port(port)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d/" % port
    print("==================================================")
    print(" ChannelScraper 2.0 running at: %s" % url)
    print("==================================================")

    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
