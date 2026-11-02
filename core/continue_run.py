# -*- coding: utf-8 -*-
"""Standalone script to continue processing without restarting from scratch.

Usage:
    python continue_run.py [optional_run_id]

It automatically picks up exactly where the run left off:
1. Skips already downloaded captions
2. Processes any unprocessed words
3. Merges outputs
4. Builds search.html
5. Opens search.html in your browser!
"""

import os
import sys
import webbrowser
import pipeline

def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    run_id = sys.argv[1] if len(sys.argv) > 1 else pipeline.get_active_run_id()
    if not run_id:
        print("[ERROR] No active run found.")
        return

    ws = pipeline.Workspace(os.path.join(pipeline.RUNS_DIR, run_id))
    print("=" * 60)
    print(" Continuing run: %s" % ws.id)
    print("=" * 60)

    stats = ws.get_stats()
    print("Videos in list:     %d (%.1f hours)" % (stats["videos"], stats["hours"]))
    print("Captions available: %d / %d" % (stats["captions"], stats["videos"]))
    print("Words processed:    %d / %d" % (stats["words"], stats["videos"]))

    # Step A: Missing words
    unprocessed_words = [v for v in ws.load_videos() if ws.caption_path(v[0]) and not os.path.exists(ws.words_path(v[0]))]
    if unprocessed_words:
        print("\n[Stage 3] Processing %d remaining word files..." % len(unprocessed_words))
        have, _ = ws.build_all_words_parallel()
        print("Done. Words ready: %d" % have)

    # Step B: Merge
    print("\n[Stage 4] Merging consolidated files...")
    un, fo, m_stats = ws.merge_outputs()
    print("Merged %d videos (%s words)" % (m_stats["videos"], f"{m_stats['words']:,}"))

    # Step C: Build search page
    print("\n[Stage 5] Building offline search.html...")
    v, lines, size = ws.build_search_page(compress=True)
    size_mb = size / 1048576.0
    print("search.html compiled successfully: %d videos | %d lines | %.1f MB" % (v, lines, size_mb))

    # Mirror to root output folder
    try:
        import shutil
        os.makedirs(pipeline.OUT, exist_ok=True)
        shutil.copy2(os.path.join(ws.out_dir, "search.html"), os.path.join(pipeline.OUT, "search.html"))
        shutil.copy2(un, os.path.join(pipeline.OUT, os.path.basename(un)))
        shutil.copy2(fo, os.path.join(pipeline.OUT, os.path.basename(fo)))
    except Exception:
        pass

    page_path = os.path.join(ws.out_dir, "search.html")
    print("\nOpening search page: %s" % page_path)
    webbrowser.open("file:///" + page_path.replace("\\", "/"))
    print("\nAll done! Nothing was restarted or lost.")

if __name__ == "__main__":
    main()
