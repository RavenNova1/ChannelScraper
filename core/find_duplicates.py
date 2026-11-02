# -*- coding: utf-8 -*-
"""Find duplicated videos and clips uploaded to the same YouTube channel.

Detects:
1. Exact / Near-exact re-uploads (same video with different titles).
2. Clips & Excerpts (short videos extracted from long streams/lectures).
3. Major content overlaps (substantial shared discussions/segments).

Outputs terminal summary, an interactive HTML dashboard, CSV, and JSON.
"""

import argparse
import csv
import glob
import json
import os
import re
import sys
import time
from collections import defaultdict

# Force UTF-8 on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CORE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CORE_DIR) if os.path.basename(CORE_DIR) == "core" else CORE_DIR


def normalize_ar(w):
    w = w.strip()
    w = w.replace("آ", "ا").replace("أ", "ا").replace("إ", "ا")
    w = w.replace("ى", "ي").replace("ة", "ه")
    return w


def format_duration(sec):
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return "%d س و %d د" % (h, m)
    if m > 0:
        return "%d د و %d ث" % (m, s)
    return "%d ث" % s


def load_channel_metadata(run_dir):
    """Load video metadata {vid: {title, duration, url}}."""
    meta = {}
    # Try unformatted.txt in output/
    unf = os.path.join(run_dir, "output")
    cands = glob.glob(os.path.join(unf, "*_unformatted.txt"))
    if not cands:
        cands = glob.glob(os.path.join(ROOT, "output", "*_unformatted.txt"))

    if cands:
        with open(cands[0], "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("@"):
                    parts = line.rstrip("\n").split("\t")
                    vid = parts[0][1:]
                    title = parts[1] if len(parts) > 1 else vid
                    try:
                        dur = int(parts[2]) if len(parts) > 2 else 0
                    except ValueError:
                        dur = 0
                    meta[vid] = {
                        "id": vid,
                        "title": title,
                        "duration": dur,
                        "url": "https://www.youtube.com/watch?v=" + vid
                    }

    # Fallback to data/channel.jsonl if any videos missing
    chan_json = os.path.join(run_dir, "data", "channel.jsonl")
    if os.path.exists(chan_json):
        with open(chan_json, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                    vid = o.get("id")
                    if vid and vid not in meta:
                        meta[vid] = {
                            "id": vid,
                            "title": (o.get("title") or vid).strip(),
                            "duration": int(o.get("duration") or 0),
                            "url": o.get("webpage_url") or ("https://www.youtube.com/watch?v=" + vid)
                        }
                except Exception:
                    pass

    return meta


def analyze_duplicates(words_dir, video_meta, min_sim=0.35, shingle_n=7, sample_mod=3):
    """Scan all TSVs, build shingle fingerprints, and find duplicated video content."""
    tsv_files = glob.glob(os.path.join(words_dir, "*.tsv"))
    if not tsv_files:
        raise RuntimeError("لم يتم العثور على ملفات كلمات في مجلد words: " + words_dir)

    print(f"[*] جارٍ تحميل وفهرسة تفريغ {len(tsv_files):,} فيديو...")
    t0 = time.time()

    doc_shingles = {}
    doc_lengths = {}
    doc_words = {}

    for p in tsv_files:
        vid = os.path.basename(p)[:-4]
        words = []
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split("\t")
                if len(parts) > 1:
                    w = normalize_ar(parts[1])
                    if w and any(c.isalnum() for c in w):
                        words.append(w)

        doc_lengths[vid] = len(words)
        doc_words[vid] = words
        if len(words) < shingle_n:
            continue

        # Fast 0-mod sampled shingling (winnowing) for high speed and compact memory
        sh_set = set()
        for i in range(len(words) - shingle_n + 1):
            h = hash(tuple(words[i:i + shingle_n]))
            if sample_mod <= 1 or (h % sample_mod == 0):
                sh_set.add(h)
        doc_shingles[vid] = sh_set

    load_time = time.time() - t0
    print(f"[+] تم تحميل {len(doc_shingles):,} فيديو في {load_time:.2f} ثانية.")

    # Inverted index
    t1 = time.time()
    inv_index = defaultdict(list)
    for vid, sh_set in doc_shingles.items():
        for sh in sh_set:
            inv_index[sh].append(vid)

    # Candidate pairs
    pair_counts = defaultdict(int)
    for sh, vids in inv_index.items():
        # Exclude phrases shared across more than 40 videos (standard intros/clichés)
        if 1 < len(vids) <= 40:
            for i in range(len(vids)):
                v1 = vids[i]
                for j in range(i + 1, len(vids)):
                    v2 = vids[j]
                    if v1 < v2:
                        pair_counts[(v1, v2)] += 1
                    else:
                        pair_counts[(v2, v1)] += 1

    # Classify matches
    results = []
    for (v1, v2), shared in pair_counts.items():
        len1 = len(doc_shingles.get(v1, []))
        len2 = len(doc_shingles.get(v2, []))
        if not len1 or not len2:
            continue

        jaccard = shared / (len1 + len2 - shared)
        c1_in_2 = shared / len1  # fraction of v1 found in v2
        c2_in_1 = shared / len2  # fraction of v2 found in v1

        max_score = max(jaccard, c1_in_2, c2_in_1)
        if max_score < min_sim:
            continue

        m1 = video_meta.get(v1, {"title": v1, "duration": 0, "url": "https://www.youtube.com/watch?v=" + v1})
        m2 = video_meta.get(v2, {"title": v2, "duration": 0, "url": "https://www.youtube.com/watch?v=" + v2})

        dur1 = m1["duration"]
        dur2 = m2["duration"]
        wcount1 = doc_lengths.get(v1, 0)
        wcount2 = doc_lengths.get(v2, 0)

        # Classify relation type
        # 1. Exact re-upload: high Jaccard OR both containments >= 75%
        if jaccard >= 0.65 or (c1_in_2 >= 0.75 and c2_in_1 >= 0.75):
            kind = "exact"
            kind_ar = "إعادة رفع كاملة / شبه كاملة"
            badge_color = "red"
            shorter, longer = (v1, v2) if wcount1 <= wcount2 else (v2, v1)
            detail = "الفيديوهان متطابقان تقريباً مع اختلاف طفيف في العنوان أو البداية"
        # 2. Excerpt / Clip: one video is largely inside the other, with significant duration difference
        elif c1_in_2 >= 0.60 and (wcount2 >= wcount1 * 1.35 or dur2 >= dur1 * 1.35):
            kind = "clip"
            kind_ar = "مقطع مجتزأ من فيديو أطول"
            badge_color = "amber"
            shorter, longer = v1, v2
            detail = f"الفيديو الأول مجتزأ بنسبة {c1_in_2*100:.1f}% من الفيديو الثاني الأطول"
        elif c2_in_1 >= 0.60 and (wcount1 >= wcount2 * 1.35 or dur1 >= dur2 * 1.35):
            kind = "clip"
            kind_ar = "مقطع مجتزأ من فيديو أطول"
            badge_color = "amber"
            shorter, longer = v2, v1
            detail = f"الفيديو الثاني مجتزأ بنسبة {c2_in_1*100:.1f}% من الفيديو الأول الأطول"
        # 3. Major overlap
        else:
            kind = "overlap"
            kind_ar = "تطابق جزئي كبير"
            badge_color = "blue"
            shorter, longer = (v1, v2) if wcount1 <= wcount2 else (v2, v1)
            detail = f"يحتويان على أجزاء مشتركة كبيرة بنسبة {max(c1_in_2, c2_in_1)*100:.1f}%"

        # Estimated shared words
        shared_words = int(min(wcount1, wcount2) * max(jaccard, c1_in_2, c2_in_1))

        results.append({
            "v1": v1,
            "v2": v2,
            "title1": m1["title"],
            "title2": m2["title"],
            "duration1": dur1,
            "duration2": dur2,
            "duration_fmt1": format_duration(dur1),
            "duration_fmt2": format_duration(dur2),
            "words1": wcount1,
            "words2": wcount2,
            "url1": m1["url"],
            "url2": m2["url"],
            "kind": kind,
            "kind_ar": kind_ar,
            "badge_color": badge_color,
            "score": round(max_score * 100, 1),
            "jaccard": round(jaccard * 100, 1),
            "contain_1_in_2": round(c1_in_2 * 100, 1),
            "contain_2_in_1": round(c2_in_1 * 100, 1),
            "shared_words": shared_words,
            "detail": detail
        })

    # Sort by score descending
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def export_csv(results, path):
    """Export findings to CSV."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "النوع", "نسبة التطابق %", "عنوان الفيديو 1", "مدة الفيديو 1", "معرف 1", "رابط 1",
            "عنوان الفيديو 2", "مدة الفيديو 2", "معرف 2", "رابط 2", "الكلمات المشتركة التقديرية", "التفاصيل"
        ])
        for r in results:
            writer.writerow([
                r["kind_ar"], r["score"], r["title1"], r["duration_fmt1"], r["v1"], r["url1"],
                r["title2"], r["duration_fmt2"], r["v2"], r["url2"], r["shared_words"], r["detail"]
            ])


def export_json(results, path):
    """Export findings to JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


HTML_TEMPLATE = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>كاشف الفيديوهات المكررة والمجتزأة في القناة</title>
<style>
  :root {
    --bg: #0e1319; --card: #151d26; --head: #1c2633; --line: #243242;
    --txt: #e6edf5; --dim: #8fa0b3; --acc: #4aa3ff; --acc-bg: rgba(74,163,255,0.12);
    --red: #f85149; --red-bg: rgba(248,81,73,0.14);
    --amber: #e3b341; --amber-bg: rgba(227,179,65,0.14);
    --blue: #58a6ff; --blue-bg: rgba(88,166,255,0.14);
  }
  body.light {
    --bg: #f6f8fa; --card: #ffffff; --head: #f0f3f6; --line: #d8dee4;
    --txt: #1f2328; --dim: #656d76; --acc: #0969da; --acc-bg: #ddf4ff;
    --red: #cf222e; --red-bg: #ffebe9;
    --amber: #9a6700; --amber-bg: #fff8c5;
    --blue: #0969da; --blue-bg: #ddf4ff;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--txt);
    font: 14.5px/1.6 "Segoe UI", "Noto Naskh Arabic", Tahoma, Arial, sans-serif;
  }
  .wrap { max-width: 1200px; margin: 0 auto; padding: 20px 16px 80px; }
  header { margin-bottom: 24px; border-bottom: 1px solid var(--line); padding-bottom: 18px; }
  .top-row { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
  h1 { margin: 0; font-size: 23px; font-weight: 700; }
  .sub { margin: 6px 0 0; color: var(--dim); font-size: 14px; }
  .actions { display: flex; gap: 8px; align-items: center; }
  button, .btn {
    background: var(--head); color: var(--txt); border: 1px solid var(--line);
    border-radius: 8px; padding: 7px 14px; font: 600 13px inherit; cursor: pointer;
    text-decoration: none; display: inline-flex; align-items: center; gap: 6px;
  }
  button:hover, .btn:hover { border-color: var(--acc); color: var(--acc); }

  /* KPI cards */
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin-bottom: 20px; }
  .kpi { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; }
  .kpi .num { font-size: 26px; font-weight: 700; line-height: 1.2; }
  .kpi .lbl { font-size: 13px; color: var(--dim); margin-top: 4px; }
  .kpi.red .num { color: var(--red); }
  .kpi.amber .num { color: var(--amber); }
  .kpi.blue .num { color: var(--blue); }

  /* Controls */
  .controls {
    background: var(--card); border: 1px solid var(--line); border-radius: 12px;
    padding: 12px 16px; margin-bottom: 20px; display: flex; gap: 14px; align-items: center; flex-wrap: wrap;
  }
  .tabs { display: flex; gap: 6px; }
  .tab {
    background: transparent; border: 1px solid transparent; color: var(--dim);
    padding: 6px 12px; border-radius: 7px; font-weight: 600; cursor: pointer;
  }
  .tab.active { background: var(--acc-bg); color: var(--acc); border-color: var(--acc); }
  .search-box { flex: 1; min-width: 200px; }
  .search-box input {
    width: 100%; background: var(--head); border: 1px solid var(--line); color: var(--txt);
    padding: 8px 12px; border-radius: 8px; font: inherit; outline: none;
  }
  .search-box input:focus { border-color: var(--acc); }

  /* Pairs list */
  .pair-card {
    background: var(--card); border: 1px solid var(--line); border-radius: 14px;
    margin-bottom: 14px; overflow: hidden; transition: transform 0.1s, border-color 0.1s;
  }
  .pair-card:hover { border-color: var(--acc); }
  .p-head {
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;
    padding: 10px 16px; background: var(--head); border-bottom: 1px solid var(--line);
  }
  .badge {
    display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;
    border-radius: 20px; font-size: 12px; font-weight: 700;
  }
  .badge.red { background: var(--red-bg); color: var(--red); }
  .badge.amber { background: var(--amber-bg); color: var(--amber); }
  .badge.blue { background: var(--blue-bg); color: var(--blue); }

  .score-box { display: flex; align-items: center; gap: 8px; }
  .score-val { font-size: 18px; font-weight: 800; }
  .p-body { padding: 14px 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 768px) { .p-body { grid-template-columns: 1fr; } }
  
  .v-col { background: var(--head); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; }
  .v-role { font-size: 11px; text-transform: uppercase; color: var(--dim); font-weight: 700; letter-spacing: 0.5px; }
  .v-title { font-size: 14.5px; font-weight: 600; margin: 4px 0 8px; line-height: 1.45; }
  .v-meta { display: flex; gap: 10px; font-size: 12px; color: var(--dim); margin-bottom: 10px; flex-wrap: wrap; }
  .v-yt {
    background: #c4302b; color: #fff; border: 0; border-radius: 6px;
    padding: 5px 12px; font-size: 12px; text-decoration: none; font-weight: 600;
    display: inline-flex; align-items: center; gap: 5px;
  }
  .v-yt:hover { background: #e62117; color: #fff; }

  .p-foot {
    padding: 8px 16px; background: rgba(0,0,0,0.1); border-top: 1px solid var(--line);
    font-size: 12px; color: var(--dim); display: flex; justify-content: space-between; align-items: center;
  }
  .empty { text-align: center; padding: 60px 20px; color: var(--dim); }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="top-row">
      <div>
        <h1>🔍 كاشف الفيديوهات المكررة والمجتزأة في القناة</h1>
        <div class="sub">تم فحص <b>__TOTAL_VIDEOS__</b> فيديو عبر مقارنة بصمات التفريغ النصي الدقيقة (7-grams).</div>
      </div>
      <div class="actions">
        <a class="btn" href="duplicates.csv" download>📥 تحميل CSV</a>
        <a class="btn" href="duplicates.json" download>📄 تحميل JSON</a>
        <button id="themeBtn" type="button">🌓 المظهر</button>
      </div>
    </div>
  </header>

  <div class="kpis">
    <div class="kpi">
      <div class="num">__TOTAL_PAIRS__</div>
      <div class="lbl">إجمالي حالات التطابق</div>
    </div>
    <div class="kpi red">
      <div class="num">__EXACT_COUNT__</div>
      <div class="lbl">إعادة رفع كاملة (عناوين مختلفة)</div>
    </div>
    <div class="kpi amber">
      <div class="num">__CLIP_COUNT__</div>
      <div class="lbl">مقاطع مجتزأة من فيديوهات أخرى</div>
    </div>
    <div class="kpi blue">
      <div class="num">__OVERLAP_COUNT__</div>
      <div class="lbl">تطابق جزئي كبير</div>
    </div>
  </div>

  <div class="controls">
    <div class="tabs">
      <button class="tab active" data-type="all">الكل (__TOTAL_PAIRS__)</button>
      <button class="tab" data-type="exact">إعادة رفع (__EXACT_COUNT__)</button>
      <button class="tab" data-type="clip">مقاطع مجتزأة (__CLIP_COUNT__)</button>
      <button class="tab" data-type="overlap">تطابق جزئي (__OVERLAP_COUNT__)</button>
    </div>
    <div class="search-box">
      <input id="q" type="text" placeholder="ابحث في عناوين الفيديوهات المكررة أو المعرفات...">
    </div>
  </div>

  <div id="list"></div>
</div>

<script>
const DATA = __DATA_JSON__;

let activeType = "all";
let filterQuery = "";

function render() {
  const container = document.getElementById("list");
  const q = filterQuery.toLowerCase().trim();
  
  const filtered = DATA.filter(r => {
    if (activeType !== "all" && r.kind !== activeType) return false;
    if (q) {
      const t1 = (r.title1 || "").toLowerCase();
      const t2 = (r.title2 || "").toLowerCase();
      const v1 = (r.v1 || "").toLowerCase();
      const v2 = (r.v2 || "").toLowerCase();
      if (!t1.includes(q) && !t2.includes(q) && !v1.includes(q) && !v2.includes(q)) return false;
    }
    return true;
  });

  if (!filtered.length) {
    container.innerHTML = '<div class="empty">لا توجد نتائج مطابقة للتصفية.</div>';
    return;
  }

  let html = "";
  for (const r of filtered) {
    html += `
    <div class="pair-card">
      <div class="p-head">
        <span class="badge ${r.badge_color}">● ${r.kind_ar}</span>
        <div class="score-box">
          <span style="font-size:12px; color:var(--dim)">نسبة التطابق:</span>
          <span class="score-val" style="color:var(--${r.badge_color})">${r.score}%</span>
        </div>
      </div>
      <div class="p-body">
        <div class="v-col">
          <div class="v-role">الفيديو الأول (${r.duration_fmt1})</div>
          <div class="v-title">${escapeHtml(r.title1)}</div>
          <div class="v-meta">
            <span>⏱ ${r.duration_fmt1}</span>
            <span>📝 ${r.words1.toLocaleString()} كلمة</span>
            <span>🆔 ${r.v1}</span>
          </div>
          <a class="v-yt" href="${r.url1}" target="_blank" rel="noopener">▶ فتح على يوتيوب</a>
        </div>
        <div class="v-col">
          <div class="v-role">الفيديو الثاني (${r.duration_fmt2})</div>
          <div class="v-title">${escapeHtml(r.title2)}</div>
          <div class="v-meta">
            <span>⏱ ${r.duration_fmt2}</span>
            <span>📝 ${r.words2.toLocaleString()} كلمة</span>
            <span>🆔 ${r.v2}</span>
          </div>
          <a class="v-yt" href="${r.url2}" target="_blank" rel="noopener">▶ فتح على يوتيوب</a>
        </div>
      </div>
      <div class="p-foot">
        <span>💡 ${escapeHtml(r.detail)}</span>
        <span>الكلمات المشتركة التقديرية: ~${r.shared_words.toLocaleString()} كلمة</span>
      </div>
    </div>`;
  }
  container.innerHTML = html;
}

function escapeHtml(s) {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

document.querySelectorAll(".tab").forEach(tab => {
  tab.onclick = () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    activeType = tab.dataset.type;
    render();
  };
});

document.getElementById("q").oninput = (e) => {
  filterQuery = e.target.value;
  render();
};

document.getElementById("themeBtn").onclick = () => {
  document.body.classList.toggle("light");
};

render();
</script>
</body>
</html>
"""


def generate_html_report(results, total_videos, out_path):
    """Generate standalone interactive HTML report."""
    exact_count = sum(1 for r in results if r["kind"] == "exact")
    clip_count = sum(1 for r in results if r["kind"] == "clip")
    overlap_count = sum(1 for r in results if r["kind"] == "overlap")

    json_str = json.dumps(results, ensure_ascii=False)

    html = (HTML_TEMPLATE
            .replace("__TOTAL_VIDEOS__", str(total_videos))
            .replace("__TOTAL_PAIRS__", str(len(results)))
            .replace("__EXACT_COUNT__", str(exact_count))
            .replace("__CLIP_COUNT__", str(clip_count))
            .replace("__OVERLAP_COUNT__", str(overlap_count))
            .replace("__DATA_JSON__", json_str))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    parser = argparse.ArgumentParser(description="Find duplicated videos and clips in channel transcripts.")
    parser.add_argument("--run", default=None, help="Run directory (defaults to active run in runs/)")
    parser.add_argument("--min-sim", type=float, default=0.40, help="Minimum similarity threshold (0.0 to 1.0, default 0.40)")
    parser.add_argument("--csv", action="store_true", default=True, help="Export to duplicates.csv")
    parser.add_argument("--json", action="store_true", default=True, help="Export to duplicates.json")
    parser.add_argument("--html", action="store_true", default=True, help="Generate duplicates_report.html")
    args = parser.parse_args()

    # Determine run directory
    run_dir = args.run
    if not run_dir:
        active_p = os.path.join(ROOT, "runs", ".active_run")
        if os.path.exists(active_p):
            with open(active_p, "r", encoding="utf-8") as f:
                rid = f.read().strip()
                if rid:
                    run_dir = os.path.join(ROOT, "runs", rid)

    if not run_dir or not os.path.exists(run_dir):
        # Fallback to the latest run in runs/
        runs = sorted(glob.glob(os.path.join(ROOT, "runs", "*")), key=os.path.getmtime, reverse=True)
        if runs:
            run_dir = runs[0]
        else:
            sys.exit("لم يتم العثور على أي مجلد تشغيل داخل runs/")

    print(f"[*] فحص مجلد التشغيل: {run_dir}")
    words_dir = os.path.join(run_dir, "words")
    meta = load_channel_metadata(run_dir)

    results = analyze_duplicates(words_dir, meta, min_sim=args.min_sim)

    # Console summary
    print("\n" + "=" * 80)
    print(f"📊 نتائج فحص الفيديوهات المكررة والمجتزأة ({len(results)} حالة تطابق):")
    print("=" * 80)

    exact = [r for r in results if r["kind"] == "exact"]
    clips = [r for r in results if r["kind"] == "clip"]
    overlaps = [r for r in results if r["kind"] == "overlap"]

    print(f"🔴 فيديوهات مكررة بالكامل (إعادة رفع): {len(exact)}")
    print(f"🟡 مقاطع مجتزأة من فيديوهات أخرى: {len(clips)}")
    print(f"🔵 تطابق جزئي كبير: {len(overlaps)}")
    print("-" * 80)

    # Print top 15 in console
    for i, r in enumerate(results[:15], 1):
        print(f"\n{i}. [{r['kind_ar']}] بنسبة تطابق: {r['score']}%")
        print(f"   الفيديو 1 ({r['duration_fmt1']}): {r['title1']}")
        print(f"   رابط 1: {r['url1']}")
        print(f"   الفيديو 2 ({r['duration_fmt2']}): {r['title2']}")
        print(f"   رابط 2: {r['url2']}")
        print(f"   💡 {r['detail']}")

    # Output exports
    out_dir = os.path.join(run_dir, "output")
    root_out = os.path.join(ROOT, "output")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(root_out, exist_ok=True)

    if args.csv:
        csv_path = os.path.join(out_dir, "duplicates.csv")
        export_csv(results, csv_path)
        export_csv(results, os.path.join(root_out, "duplicates.csv"))
        print(f"\n[+] تم حفظ التقرير المجدول: {csv_path}")

    if args.json:
        json_path = os.path.join(out_dir, "duplicates.json")
        export_json(results, json_path)
        export_json(results, os.path.join(root_out, "duplicates.json"))
        print(f"[+] تم حفظ بيانات JSON: {json_path}")

    if args.html:
        html_path = os.path.join(out_dir, "duplicates_report.html")
        generate_html_report(results, len(meta), html_path)
        generate_html_report(results, len(meta), os.path.join(root_out, "duplicates_report.html"))
        print(f"[+] تم توليد لوحة التحكم التفاعلية: {html_path}")


if __name__ == "__main__":
    main()
