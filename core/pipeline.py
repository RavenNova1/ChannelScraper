# -*- coding: utf-8 -*-
"""Core pipeline for ChannelScraper with multi-run isolated workspaces and parallel downloading.

Each run has its own dedicated directory inside runs/<run_id>/ so that multiple runs
and multiple channels never overlap or clobber each other:

    runs/<run_id>/
        meta.json           run configuration & metadata
        data/
            channel.jsonl   video list
        captions/           raw json3 captions
        words/              <id>.tsv (millisecond timestamps + cleaned words)
        formatted/          <id>.txt (human readable transcript with minute markers)
        output/             <name>_formatted.txt, <name>_unformatted.txt, search.html
        logs/               run.log, failed.tsv
"""

import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

CORE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CORE_DIR) if os.path.basename(CORE_DIR) == "core" else CORE_DIR
BIN = os.path.join(CORE_DIR, "bin") if os.path.exists(os.path.join(CORE_DIR, "bin")) else os.path.join(ROOT, "bin")
YTDLP = os.path.join(BIN, "yt-dlp.exe")
RUNS_DIR = os.path.join(ROOT, "runs")
OUTPUT_DIR = os.path.join(ROOT, "output")
OUT = OUTPUT_DIR

for d in (BIN, RUNS_DIR, OUTPUT_DIR):
    os.makedirs(d, exist_ok=True)

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
BAD_CHARS = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")


# --------------------------------------------------------------------------
# General helpers
# --------------------------------------------------------------------------
def is_video_id(s):
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{11}", s))


def watch_url(vid, sec=None):
    if sec is not None:
        return "https://www.youtube.com/watch?v=%s&t=%ds" % (vid, int(sec))
    return "https://www.youtube.com/watch?v=" + vid


def safe_name(s, limit=60):
    s = re.sub(r'[\\/:*?"<>|]+', " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit] or "channel"


def parse_target(text):
    """Turn whatever the user pasted into ('channel'|'video', url, name)."""
    t = (text or "").strip()
    if not t:
        raise ValueError("اكتب رابط القناة أو الفيديو أولًا")
    if is_video_id(t):
        return "video", watch_url(t), t
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/live/)([A-Za-z0-9_-]{11})", t)
    if m and ("watch" in t or "youtu.be" in t or "/shorts/" in t or "/live/" in t):
        vid = m.group(1)
        return "video", watch_url(vid), vid
    name = t.rstrip("/").split("/")[-1] or "channel"
    if name.startswith("@"):
        name = name[1:]
    if not t.startswith("http"):
        if t.startswith("UC") and len(t) >= 20:
            t = "https://www.youtube.com/channel/" + t
        elif t.startswith("@"):
            t = "https://www.youtube.com/" + t
        else:
            t = "https://www.youtube.com/@" + t
    if "/videos" not in t and "/channel/" not in t:
        t = t.rstrip("/") + "/videos"
    return "channel", t, safe_name(name)


def ytdlp_cmd(*args):
    return [YTDLP, *args]


def run_stream(cmd, on_line, stop_event=None, cwd=None):
    """Run a command, feed every output line to on_line, return exit code."""
    p = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW, cwd=cwd,
        text=True, encoding="utf-8", errors="replace", bufsize=1)
    try:
        for line in p.stdout:
            if stop_event is not None and stop_event.is_set():
                p.kill()
                break
            if on_line:
                on_line(line.rstrip("\n"))
    finally:
        try:
            p.stdout.close()
        except Exception:
            pass
    return p.wait()


def hms(sec):
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return "%d:%02d:%02d" % (h, m, s)


# --------------------------------------------------------------------------
# Caption parsing & NLP stripping
# --------------------------------------------------------------------------
def read_json3(path):
    """[(start_ms, word)] with rolling duplicates removed."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    toks = []
    for ev in data.get("events") or []:
        base = ev.get("tStartMs") or 0
        segs = ev.get("segs") or []
        for sg in segs:
            txt = BAD_CHARS.sub("", sg.get("utf8") or "")
            txt = re.sub(r"\s+", " ", txt).strip()
            if not txt:
                continue
            ms = base + (sg.get("tOffsetMs") or 0)
            for piece in txt.split(" "):
                if piece:
                    toks.append((int(ms), piece))
    # Rolling caption deduplication
    clean = []
    for ms, w in toks:
        if clean and clean[-1][0] == ms and clean[-1][1] == w:
            continue
        clean.append((ms, w))
    return clean


def read_vtt_words(path):
    """Fallback for old .vtt files that carry <00:00:01.234> tags."""
    text = open(path, encoding="utf-8", errors="replace").read()
    out = []
    for line in text.splitlines():
        for m in re.finditer(r"<(\d{2}):(\d{2}):(\d{2})\.(\d{3})><c>([^<]*)</c>", line):
            h, mi, s, ms, w = m.groups()
            word = BAD_CHARS.sub("", w).strip()
            if word:
                out.append((int(h) * 3600000 + int(mi) * 60000 + int(s) * 1000 + int(ms), word))
    return out


def strip_annotations(toks):
    """Drop [sound] annotations ([أصوات شخير], [موسيقى] ...) but keep real words."""
    out = []
    inside = False
    for ms, w in toks:
        if "[" not in w and "]" not in w and not inside:
            if any(ch.isalnum() for ch in w):
                out.append((ms, w))
            continue
        buf = []
        for ch in w:
            if inside:
                if ch == "]":
                    inside = False
            elif ch == "[":
                inside = True
            else:
                buf.append(ch)
        piece = "".join(buf).strip()
        if piece and any(ch.isalnum() for ch in piece):
            out.append((ms, piece))
    return out


def split_minutes(toks):
    """[(minuteStartSec, [words])] -- one group per minute."""
    groups, cur, curmin = [], [], None
    for ms, w in toks:
        m = ms // 60000
        if curmin is None:
            curmin = m
        if m != curmin:
            if cur:
                groups.append((curmin * 60, cur))
            cur, curmin = [], m
        cur.append(w)
    if cur:
        groups.append((curmin * 60, cur))
    return groups


# --------------------------------------------------------------------------
# Isolated Workspace Class (Guarantees No Overlapping Between Runs)
# --------------------------------------------------------------------------
class Workspace:
    """Manages an isolated workspace directory for a specific run."""

    def __init__(self, run_dir):
        self.root = os.path.abspath(run_dir)
        self.id = os.path.basename(self.root)
        self.data_dir = os.path.join(self.root, "data")
        self.cap_dir = os.path.join(self.root, "captions")
        self.words_dir = os.path.join(self.root, "words")
        self.form_dir = os.path.join(self.root, "formatted")
        self.out_dir = os.path.join(self.root, "output")
        self.logs_dir = os.path.join(self.root, "logs")

        for d in (self.root, self.data_dir, self.cap_dir, self.words_dir,
                  self.form_dir, self.out_dir, self.logs_dir):
            os.makedirs(d, exist_ok=True)

        self.meta_path = os.path.join(self.root, "meta.json")
        self.channel_json = os.path.join(self.data_dir, "channel.jsonl")
        self.failed_path = os.path.join(self.logs_dir, "failed.tsv")
        self.log_path = os.path.join(self.logs_dir, "run.log")

    def log(self, msg):
        msg = (msg or "").rstrip()
        if not msg:
            return
        line = "%s  %s" % (time.strftime("%H:%M:%S"), msg)
        try:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass

    def load_meta(self):
        try:
            if os.path.exists(self.meta_path):
                with open(self.meta_path, encoding="utf-8") as fh:
                    return json.load(fh)
        except (OSError, ValueError):
            pass
        return {}

    def save_meta(self, obj):
        try:
            with open(self.meta_path, "w", encoding="utf-8") as fh:
                json.dump(obj, fh, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def load_videos(self):
        """[(id, title, duration, url)] in playlist order, unique by id."""
        out, seen = [], set()
        if not os.path.exists(self.channel_json):
            return out
        with open(self.channel_json, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                vid = o.get("id")
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                out.append((
                    vid,
                    (o.get("title") or "بدون عنوان").strip(),
                    int(o.get("duration") or 0),
                    o.get("webpage_url") or o.get("url") or watch_url(vid)
                ))
        return out

    def load_failed(self):
        failed = set()
        if os.path.exists(self.failed_path):
            with open(self.failed_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    parts = line.strip().split("\t")
                    if parts and parts[0]:
                        failed.add(parts[0])
        return failed

    def caption_path(self, vid):
        for ext in (".ar-orig.json3", ".ar.json3", ".ar.vtt", ".vtt"):
            p = os.path.join(self.cap_dir, vid + ext)
            if os.path.exists(p) and os.path.getsize(p) > 200:
                return p
        return None

    def words_path(self, vid):
        return os.path.join(self.words_dir, vid + ".tsv")

    def formatted_path(self, vid):
        return os.path.join(self.form_dir, vid + ".txt")

    def load_words(self, vid):
        out = []
        p = self.words_path(vid)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    ms, _, w = line.rstrip("\n").partition("\t")
                    if ms.isdigit() and w:
                        out.append((int(ms), w))
        return out

    def output_name(self):
        meta = self.load_meta()
        name = meta.get("name") or meta.get("title") or ""
        if not name:
            kind, _u, name = parse_target(meta.get("target") or "channel")
        return safe_name(name) or "channel"

    def get_stats(self):
        vids = self.load_videos()
        have_cap = sum(1 for v in vids if self.caption_path(v[0]))
        have_words = sum(1 for v in vids if os.path.exists(self.words_path(v[0])))
        hours = round(sum(v[2] for v in vids) / 3600.0, 1) if vids else 0
        name = self.output_name()

        un = os.path.join(self.out_dir, name + "_unformatted.txt")
        fo = os.path.join(self.out_dir, name + "_formatted.txt")
        page = os.path.join(self.out_dir, "search.html")

        return {
            "videos": len(vids),
            "hours": hours,
            "captions": have_cap,
            "words": have_words,
            "unformatted_exists": os.path.exists(un),
            "formatted_exists": os.path.exists(fo),
            "page_exists": os.path.exists(page),
            "unformatted_path": un if os.path.exists(un) else "",
            "formatted_path": fo if os.path.exists(fo) else "",
            "page_path": page if os.path.exists(page) else "",
            "sizes": {
                "unformatted": os.path.getsize(un) if os.path.exists(un) else 0,
                "formatted": os.path.getsize(fo) if os.path.exists(fo) else 0,
                "page": os.path.getsize(page) if os.path.exists(page) else 0,
            }
        }

    # ----------------------------------------------------------------------
    # Stage 1: List Videos
    # ----------------------------------------------------------------------
    def stage_list(self, target_url, on_line=None, stop_event=None):
        """Fetch the flat playlist and write data/channel.jsonl."""
        tmp = os.path.join(self.data_dir, "channel.jsonl.part")
        if os.path.exists(tmp):
            os.remove(tmp)
        cmd = ytdlp_cmd(
            "--flat-playlist", "--dump-json", "--no-warnings",
            "--extractor-args", "youtube:lang=ar",
            "--retries", "3", "--socket-timeout", "20", target_url
        )
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            def on(l):
                if l.startswith("{"):
                    fh.write(l + "\n")
                elif l.strip() and on_line:
                    on_line(l)
            run_stream(cmd, on, stop_event)

        if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            if stop_event and stop_event.is_set():
                return 0
            raise RuntimeError("لم نتمكن من جلب قائمة الفيديوهات من الرابط.")

        n = sum(1 for _ in open(tmp, encoding="utf-8"))
        os.replace(tmp, self.channel_json)
        return n

    # ----------------------------------------------------------------------
    # Stage 2: Parallel Caption Fetching
    # ----------------------------------------------------------------------
    def fetch_one(self, vid, stop_event=None):
        """Download Arabic caption for one video. Returns True if file exists."""
        if self.caption_path(vid):
            return True
        for langs in ("ar-orig", "ar"):
            if stop_event is not None and stop_event.is_set():
                return False
            cmd = ytdlp_cmd(
                "--skip-download", "--write-auto-subs", "--sub-langs", langs,
                "--sub-format", "json3", "--no-warnings", "--retries", "2",
                "--socket-timeout", "20", "--sleep-requests", "0.2",
                "-o", os.path.join(self.cap_dir, "%(id)s.%(ext)s"), watch_url(vid)
            )
            run_stream(cmd, None, stop_event)
            if self.caption_path(vid):
                return True
        return False

    def fetch_captions_parallel(self, on_progress=None, on_log=None,
                                stop_event=None, max_workers=4):
        """Download missing captions in parallel with progress updates."""
        vids = self.load_videos()
        if not vids:
            raise RuntimeError("قائمة الفيديوهات فارغة — شغّل المرحلة الأولى أولاً.")

        todo = [v for v in vids if not self.caption_path(v[0])]
        total = len(vids)
        already_have = total - len(todo)

        if not todo:
            return already_have, 0

        failed = []
        done_count = already_have
        t0 = time.time()
        lock = threading.Lock()

        def worker(v_item):
            nonlocal done_count
            if stop_event and stop_event.is_set():
                return v_item[0], False
            vid, title, dur, _u = v_item
            ok = self.fetch_one(vid, stop_event)
            with lock:
                done_count += 1
                spent = time.time() - t0
                completed_in_run = done_count - already_have
                eta = (spent / completed_in_run) * (len(todo) - completed_in_run) if completed_in_run else 0
                if not ok:
                    failed.append(vid)
                    if on_log:
                        on_log("تعذّر تفريغ: %s — %s" % (vid, title[:50]))
                if on_progress:
                    on_progress(done_count, total, eta, title)
            return vid, ok

        # Run with ThreadPoolExecutor
        workers = max(1, min(max_workers, 8))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(worker, v) for v in todo]
            for f in concurrent.futures.as_completed(futures):
                if stop_event and stop_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                try:
                    f.result()
                except Exception:
                    pass

        # Write failed IDs to failed.tsv
        if failed:
            with open(self.failed_path, "a", encoding="utf-8") as fh:
                for v in failed:
                    fh.write("%s\t%s\n" % (v, time.strftime("%Y-%m-%d %H:%M")))

        current_have = sum(1 for v in vids if self.caption_path(v[0]))
        return current_have, len(failed)

    # ----------------------------------------------------------------------
    # Stage 3: Words & Timestamp Extraction
    # ----------------------------------------------------------------------
    def build_video(self, vid, title, duration):
        """Write words/<id>.tsv and formatted/<id>.txt. Returns (words_count, lines_count)."""
        cap = self.caption_path(vid)
        if not cap:
            return 0, 0
        if cap.endswith(".json3"):
            toks = read_json3(cap)
        else:
            toks = read_vtt_words(cap)
        toks = strip_annotations(toks)
        if not toks:
            return 0, 0

        with open(self.words_path(vid), "w", encoding="utf-8", newline="\n") as fh:
            for ms, w in toks:
                fh.write("%d\t%s\n" % (ms, w))

        lines = split_minutes(toks)
        fmt = [title, watch_url(vid), "", "التفريغ:"]
        for start, words in lines:
            fmt.append("(%s) %s" % (hms(start), " ".join(words)))
        with open(self.formatted_path(vid), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(fmt) + "\n")
        return len(toks), len(lines)

    def build_all_words_parallel(self, on_progress=None, on_log=None,
                                 stop_event=None, max_workers=8):
        """Processes all captions into word-level timestamps in parallel."""
        vids = self.load_videos()
        if not vids:
            raise RuntimeError("لا توجد فيديوهات مسجلة.")
        todo = [v for v in vids if self.caption_path(v[0]) and not os.path.exists(self.words_path(v[0]))]
        total = len(vids)
        already_have = sum(1 for v in vids if os.path.exists(self.words_path(v[0])))

        if not todo:
            return already_have, 0

        done_count = already_have
        empty_count = 0
        lock = threading.Lock()
        t0 = time.time()

        def worker(v_item):
            nonlocal done_count, empty_count
            if stop_event and stop_event.is_set():
                return
            vid, title, dur, _u = v_item
            words, minutes = self.build_video(vid, title, dur)
            with lock:
                done_count += 1
                if not words:
                    empty_count += 1
                spent = time.time() - t0
                completed = done_count - already_have
                eta = (spent / completed) * (len(todo) - completed) if completed else 0
                if on_progress:
                    on_progress(done_count, total, eta, title)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(worker, v) for v in todo]
            for f in concurrent.futures.as_completed(futures):
                if stop_event and stop_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                try:
                    f.result()
                except Exception:
                    pass

        current_have = sum(1 for v in vids if os.path.exists(self.words_path(v[0])))
        return current_have, empty_count

    # ----------------------------------------------------------------------
    # Stage 4: Merge Outputs
    # ----------------------------------------------------------------------
    def build_machine(self, lines_by_video):
        out = []
        for vid, title, duration, toks in lines_by_video:
            out.append("@%s\t%s\t%d" % (vid, title.replace("\t", " "), duration))
            groups, cur, curmin = [], [], None
            for ms, w in toks:
                m = ms // 60000
                if curmin is None:
                    curmin = m
                if m != curmin:
                    if cur:
                        groups.append((curmin * 60000, cur))
                    cur, curmin = [], m
                cur.append((ms, w))
            if cur:
                groups.append((curmin * 60000, cur))
            for mstart, items in groups:
                words = [w for _, w in items]
                secs = [str(min(59, (ms - mstart) // 1000)) for ms, _ in items]
                out.append("%d\t%s\t%s" % (mstart // 1000, " ".join(words), " ".join(secs)))
        return out

    def merge_outputs(self):
        """Build both consolidated files inside output/."""
        name = self.output_name()
        videos = self.load_videos()
        chunks = []
        for vid, title, duration, _url in videos:
            toks = self.load_words(vid)
            if toks:
                chunks.append((vid, title, duration, toks))

        if not chunks:
            raise RuntimeError("لا توجد كلمات مجهزة للدمج — شغّل المرحلة الثالثة أولاً.")

        un_path = os.path.join(self.out_dir, name + "_unformatted.txt")
        fo_path = os.path.join(self.out_dir, name + "_formatted.txt")

        with open(un_path, "w", encoding="utf-8", newline="\n") as fh:
            for line in self.build_machine(chunks):
                fh.write(line + "\n")

        with open(fo_path, "w", encoding="utf-8", newline="\n") as fh:
            first = True
            for vid, title, duration, toks in chunks:
                if not first:
                    fh.write("\n    \n")
                first = False
                fh.write("%s\n%s\n\nالتفريغ:\n" % (title, watch_url(vid)))
                for start, words in split_minutes(toks):
                    fh.write("(%s) %s\n" % (hms(start), " ".join(words)))

        total_words = sum(len(t) for *_x, t in chunks)
        return un_path, fo_path, {"videos": len(chunks), "words": total_words}

    # ----------------------------------------------------------------------
    # Stage 5: Build Search Application
    # ----------------------------------------------------------------------
    def build_search_page(self, title=None, sub=None, compress=True, zopfli=False):
        import build_search
        name = self.output_name()
        src = os.path.join(self.out_dir, name + "_unformatted.txt")
        if not os.path.exists(src):
            raise RuntimeError("الملف الخام غير موجود — شغّل المرحلة الرابعة أولاً.")
        meta = self.load_meta()
        page_title = title or ("بحث تفريغ — " + (meta.get("title") or name))
        sub_title = sub or "التفريغ الآلي والبحث المتقدم"
        out_page = os.path.join(self.out_dir, "search.html")
        return build_search.build(src, out_page, compress, page_title, sub_title, zopfli=zopfli)


# --------------------------------------------------------------------------
# Multi-Run Workspace Management (No Overlapping)
# --------------------------------------------------------------------------
ACTIVE_FILE = os.path.join(RUNS_DIR, ".active_run")


def create_run(target_text, custom_name=None, copy_captions_from=None):
    """Creates a new unique run directory inside runs/ ensuring zero overlap."""
    kind, url, base_name = parse_target(target_text)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    name_slug = safe_name(custom_name) if custom_name else safe_name(base_name)
    run_id = "%s_%s" % (name_slug, timestamp)
    run_path = os.path.join(RUNS_DIR, run_id)

    ws = Workspace(run_path)
    meta = {
        "id": run_id,
        "target": target_text,
        "kind": kind,
        "url": url,
        "name": name_slug,
        "title": name_slug,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "created"
    }

    # Option to reuse captions from another run of the same channel
    if copy_captions_from:
        donor_ws = Workspace(os.path.join(RUNS_DIR, copy_captions_from))
        if os.path.exists(donor_ws.cap_dir):
            for f in os.listdir(donor_ws.cap_dir):
                if f.endswith(".json3"):
                    src = os.path.join(donor_ws.cap_dir, f)
                    dst = os.path.join(ws.cap_dir, f)
                    if not os.path.exists(dst):
                        shutil.copy2(src, dst)

    ws.save_meta(meta)
    set_active_run(run_id)
    return ws


def list_runs():
    """Lists all available runs with their stats and metadata."""
    runs = []
    if not os.path.exists(RUNS_DIR):
        return runs

    active_id = get_active_run_id()
    for item in os.listdir(RUNS_DIR):
        item_path = os.path.join(RUNS_DIR, item)
        if not os.path.isdir(item_path) or item.startswith("."):
            continue
        ws = Workspace(item_path)
        meta = ws.load_meta()
        stats = ws.get_stats()

        # Calculate folder size
        total_size = 0
        try:
            for root, dirs, files in os.walk(item_path):
                total_size += sum(os.path.getsize(os.path.join(root, f)) for f in files)
        except OSError:
            pass

        runs.append({
            "id": item,
            "path": item_path,
            "name": meta.get("name") or item,
            "title": meta.get("title") or meta.get("name") or item,
            "target": meta.get("target") or "",
            "kind": meta.get("kind") or "channel",
            "created_at": meta.get("created_at") or time.strftime("%Y-%m-%d", time.localtime(os.path.getctime(item_path))),
            "videos": stats["videos"],
            "hours": stats["hours"],
            "captions": stats["captions"],
            "words": stats["words"],
            "page_exists": stats["page_exists"],
            "page_path": stats["page_path"],
            "unformatted_path": stats["unformatted_path"],
            "formatted_path": stats["formatted_path"],
            "total_size": total_size,
            "is_active": (item == active_id)
        })

    runs.sort(key=lambda x: x["created_at"], reverse=True)
    return runs


def get_active_run_id():
    if os.path.exists(ACTIVE_FILE):
        try:
            with open(ACTIVE_FILE, encoding="utf-8") as fh:
                run_id = fh.read().strip()
                if os.path.isdir(os.path.join(RUNS_DIR, run_id)):
                    return run_id
        except OSError:
            pass
    # Default to newest run
    runs = [d for d in os.listdir(RUNS_DIR)
            if os.path.isdir(os.path.join(RUNS_DIR, d)) and not d.startswith(".")]
    if runs:
        runs.sort(key=lambda d: os.path.getmtime(os.path.join(RUNS_DIR, d)), reverse=True)
        set_active_run(runs[0])
        return runs[0]
    return ""


def set_active_run(run_id):
    try:
        with open(ACTIVE_FILE, "w", encoding="utf-8") as fh:
            fh.write(run_id)
    except OSError:
        pass


def get_active_workspace():
    run_id = get_active_run_id()
    if run_id:
        return Workspace(os.path.join(RUNS_DIR, run_id))
    # If no runs exist, create a default one
    return create_run("https://www.youtube.com/@channel", "default")


def delete_run(run_id):
    run_path = os.path.join(RUNS_DIR, run_id)
    if os.path.isdir(run_path):
        shutil.rmtree(run_path, ignore_errors=True)
    if get_active_run_id() == run_id:
        runs = [d for d in os.listdir(RUNS_DIR)
                if os.path.isdir(os.path.join(RUNS_DIR, d)) and not d.startswith(".")]
        if runs:
            set_active_run(runs[0])
        elif os.path.exists(ACTIVE_FILE):
            os.remove(ACTIVE_FILE)
    return True
