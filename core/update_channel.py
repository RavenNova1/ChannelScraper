# -*- coding: utf-8 -*-
"""Smart Incremental Channel Updater (Comprehensive: Videos + Streams + Shorts + Playlists + Trim Detection).

Features:
1. Checks /videos, /streams, /shorts, and /playlists (including unlisted videos).
2. Precision Trim Detection: catches any duration change of >= 1 second.
3. Automatically wipes stale cache and downloads fresh transcripts for trimmed videos.
4. Fast incremental check: skips permanently silent videos unless --verify is passed.
5. Rebuilds ultra-compressed search.html and updates all master transcript files seamlessly.
"""

import json
import os
import shutil
import sys
import time
import pipeline

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_channel_base_url(target_url):
    """Strip /videos, /streams, /shorts to get the base channel URL."""
    u = target_url.rstrip("/")
    for sub in ("/videos", "/streams", "/shorts", "/featured", "/playlists"):
        if u.endswith(sub):
            u = u[:-len(sub)]
    return u


def main():
    deep_verify = "--verify" in sys.argv
    run_id = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            run_id = arg
            break

    if not run_id:
        run_id = pipeline.get_active_run_id()

    # If still no run_id, check if there's any run directory in runs/
    if not run_id and os.path.exists(pipeline.RUNS_DIR):
        cands = [d for d in os.listdir(pipeline.RUNS_DIR)
                 if os.path.isdir(os.path.join(pipeline.RUNS_DIR, d)) and not d.startswith(".")]
        if cands:
            run_id = max(cands, key=lambda d: os.path.getmtime(os.path.join(pipeline.RUNS_DIR, d)))

    if not run_id:
        print("[!] Error: No active run or scraped channel found in runs/ directory.")
        print("    Please run the tool first via 'run.bat' to scrape a channel.")
        return

    run_path = os.path.join(pipeline.RUNS_DIR, run_id)
    if not os.path.exists(run_path):
        print(f"[!] Error: Run folder not found: {run_path}")
        return

    ws = pipeline.Workspace(run_path)
    meta = ws.load_meta()
    raw_target = meta.get("url") or meta.get("target")

    if not raw_target:
        print(f"[!] Error: Channel URL is missing from metadata in workspace: {ws.id}")
        return

    base_channel = get_channel_base_url(raw_target)
    channel_title = meta.get("title") or ws.output_name()

    print("=" * 70)
    print(f"🔄 ChannelScraper - Smart Incremental Updater")
    print(f"📁 Channel: {channel_title}")
    print(f"🔗 URL: {base_channel}")
    print(f"💾 Workspace: {ws.id}")
    if deep_verify:
        print("🔍 Deep Verification Mode: ON (Full YouTube captions re-check)")
    print("=" * 70)

    # 1. Existing videos map: vid -> (vid, title, duration, url)
    existing_vids = {v[0]: v for v in ws.load_videos()}
    print(f"[*] Local indexed videos: {len(existing_vids):,}")

    # 2. Query YouTube tabs: /videos, /streams, /shorts
    tabs_to_check = [
        ("Videos", base_channel + "/videos"),
        ("Streams", base_channel + "/streams"),
        ("Shorts", base_channel + "/shorts"),
    ]

    new_videos = []
    trimmed_videos = {}
    print("\n[*] Scanning channel tabs on YouTube (/videos, /streams, /shorts)...")
    print("    Precision duration verification (1-second threshold)...")

    for tab_name, tab_url in tabs_to_check:
        tmp_list = os.path.join(ws.data_dir, "tab_update.jsonl")
        if os.path.exists(tmp_list):
            os.remove(tmp_list)

        cmd = pipeline.ytdlp_cmd(
            "--flat-playlist", "--dump-json", "--no-warnings",
            "--extractor-args", "youtube:lang=ar",
            "--retries", "3", "--socket-timeout", "20", tab_url
        )

        with open(tmp_list, "w", encoding="utf-8", newline="\n") as fh:
            def on_line(line):
                line = line.strip()
                if not line:
                    return
                fh.write(line + "\n")
                try:
                    o = json.loads(line)
                    vid = o.get("id")
                    if not vid:
                        return
                    raw_dur = o.get("duration")
                    try:
                        dur = int(raw_dur) if (raw_dur is not None and int(raw_dur) > 0) else 0
                    except (ValueError, TypeError):
                        dur = 0
                    title = (o.get("title") or "Untitled").strip()
                    url = o.get("webpage_url") or pipeline.watch_url(vid)

                    if vid not in existing_vids:
                        new_videos.append((vid, title, dur, url))
                        existing_vids[vid] = (vid, title, dur, url)
                    else:
                        local_dur = existing_vids[vid][2]
                        if dur > 0 and local_dur and local_dur > 0:
                            diff = dur - local_dur
                            # Precision: catch ANY trim of >= 1 second
                            if abs(diff) >= 1 and vid not in trimmed_videos:
                                trimmed_videos[vid] = {
                                    "id": vid,
                                    "title": title,
                                    "old_dur": local_dur,
                                    "new_dur": dur,
                                    "diff": diff,
                                    "url": url,
                                    "tab": tab_name
                                }
                except Exception:
                    pass

            pipeline.run_stream(cmd, on_line)

        if os.path.exists(tmp_list):
            os.remove(tmp_list)

    # 3. Check playlists for any unlisted videos with duration differences
    print("\n[*] Checking playlists for unlisted or newly organized videos...")
    cmd_p = pipeline.ytdlp_cmd(
        "--flat-playlist", "--dump-json", "--no-warnings",
        base_channel + "/playlists"
    )
    p_urls = []
    def on_pl(line):
        line = line.strip()
        if not line: return
        try:
            o = json.loads(line)
            pid = o.get("id")
            if pid: p_urls.append(f"https://www.youtube.com/playlist?list={pid}")
        except Exception: pass
    pipeline.run_stream(cmd_p, on_pl)

    for p_url in p_urls:
        cmd_pv = pipeline.ytdlp_cmd(
            "--flat-playlist", "--dump-json", "--no-warnings", p_url
        )
        def on_pv(line):
            line = line.strip()
            if not line: return
            try:
                o = json.loads(line)
                vid = o.get("id")
                dur = o.get("duration")
                if not vid or not dur: return
                dur = int(dur)
                if vid not in existing_vids:
                    title = (o.get("title") or "Untitled").strip()
                    new_videos.append((vid, title, dur, pipeline.watch_url(vid)))
                    existing_vids[vid] = (vid, title, dur, pipeline.watch_url(vid))
                else:
                    ldur = existing_vids[vid][2]
                    if dur > 0 and ldur and ldur > 0:
                        diff = dur - ldur
                        if abs(diff) >= 1 and vid not in trimmed_videos:
                            trimmed_videos[vid] = {
                                "id": vid,
                                "title": (o.get("title") or existing_vids[vid][1]).strip(),
                                "old_dur": ldur,
                                "new_dur": dur,
                                "diff": diff,
                                "url": pipeline.watch_url(vid),
                                "tab": "playlists"
                            }
            except Exception: pass
        pipeline.run_stream(cmd_pv, on_pv)

    # Handle Trimmed / Duration-Changed Videos
    if trimmed_videos:
        print(f"\n✂️ Detected {len(trimmed_videos)} trimmed/edited video(s) on YouTube:")
        for idx, (vid, info) in enumerate(trimmed_videos.items(), 1):
            diff_str = f"{info['diff']:+d}s" if info['diff'] < 0 else f"+{info['diff']}s"
            print(f"  {idx}. [{pipeline.hms(info['old_dur'])} -> {pipeline.hms(info['new_dur'])} | {diff_str}] {info['title']} ({vid})")

        # 1. Clear stale caption and words files so fresh captions are fetched
        for vid in trimmed_videos:
            if os.path.exists(ws.cap_dir):
                for fn in os.listdir(ws.cap_dir):
                    if fn.startswith(vid + "."):
                        try:
                            os.remove(os.path.join(ws.cap_dir, fn))
                        except Exception:
                            pass

            w_path = ws.words_path(vid)
            if w_path and os.path.exists(w_path):
                try:
                    os.remove(w_path)
                except Exception:
                    pass

        # 2. Update channel.jsonl with new durations and titles
        all_lines = []
        if os.path.exists(ws.channel_json):
            with open(ws.channel_json, "r", encoding="utf-8") as fh:
                for l in fh:
                    l = l.strip()
                    if not l:
                        continue
                    try:
                        entry = json.loads(l)
                        v_id = entry.get("id")
                        if v_id in trimmed_videos:
                            entry["duration"] = trimmed_videos[v_id]["new_dur"]
                            entry["title"] = trimmed_videos[v_id]["title"]
                        all_lines.append(entry)
                    except Exception:
                        pass

            tmp_chan = ws.channel_json + ".tmp"
            with open(tmp_chan, "w", encoding="utf-8", newline="\n") as fh:
                for entry in all_lines:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            shutil.move(tmp_chan, ws.channel_json)
            print(f"[+] Updated duration records in {ws.channel_json}.")

    # Append any brand-new videos to channel.jsonl
    if new_videos:
        print(f"\n🎉 Found {len(new_videos)} new video(s) on YouTube:")
        for idx, (vid, title, dur, url) in enumerate(new_videos, 1):
            print(f"  {idx}. [{pipeline.hms(dur)}] {title} ({vid})")

        with open(ws.channel_json, "a", encoding="utf-8") as fh:
            for vid, title, dur, url in new_videos:
                entry = {"id": vid, "title": title, "duration": dur, "url": url}
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # 4. Check for videos that need captions
    all_current_vids = ws.load_videos()
    known_failed = ws.load_failed()

    # Any new video or trimmed video MUST have its caption fetched
    priority_vids = set(v[0] for v in new_videos) | set(trimmed_videos.keys())

    # All videos currently missing captions
    missing_caps = [v for v in all_current_vids if not ws.caption_path(v[0])]

    if deep_verify:
        to_fetch_caps = missing_caps
    else:
        # Don't waste time on permanently silent/failed videos in failed.tsv unless priority or --verify
        to_fetch_caps = [v for v in missing_caps if v[0] in priority_vids or v[0] not in known_failed]

    if not to_fetch_caps and not new_videos and not trimmed_videos:
        unprocessed_words = [v for v in all_current_vids if ws.caption_path(v[0]) and not os.path.exists(ws.words_path(v[0]))]
        if not unprocessed_words:
            print("\n✨ Up to date! All videos and transcripts are 100% synchronized.")
            print(f"🌐 Search page: {os.path.join(ws.out_dir, 'search.html')}")
            return

    # 5. Fetch captions (for new + pending + trimmed videos)
    if to_fetch_caps:
        print(f"\n[*] Downloading fresh transcripts for {len(to_fetch_caps)} video(s)...")
        def on_prog_cap(done, total, eta, title):
            print(f"   [{done}/{total}] {title[:50]}...")

        have_caps, failed_caps = ws.fetch_captions_parallel(on_progress=on_prog_cap, max_workers=4)
        print(f"[+] Transcript downloads complete. Total available captions: {have_caps}")

    # 6. Extract words for newly acquired/updated captions
    unprocessed_words = [v for v in all_current_vids if ws.caption_path(v[0]) and not os.path.exists(ws.words_path(v[0]))]
    if unprocessed_words:
        print(f"\n[*] Extracting words & timestamps for {len(unprocessed_words)} video(s)...")
        def on_prog_words(done, total, eta, title):
            print(f"   [{done}/{total}] {title[:50]}...")

        have_words, empty_words = ws.build_all_words_parallel(on_progress=on_prog_words, max_workers=4)
        print(f"[+] Word timestamp processing complete: {have_words} video(s) ready.")

    # Clean up successfully downloaded IDs from failed.tsv
    if os.path.exists(ws.failed_path):
        with open(ws.failed_path, "r", encoding="utf-8") as f:
            failed_lines = [l for l in f if not ws.caption_path(l.split("\t")[0])]
        with open(ws.failed_path, "w", encoding="utf-8") as f:
            f.writelines(failed_lines)

    # 7. Merge outputs
    print("\n[*] Merging into master transcript files...")
    un_path, fo_path, stats = ws.merge_outputs()
    print(f"[+] Merged: {stats['videos']} videos · {stats['words']:,} words.")

    # 8. Rebuild search.html
    print("\n[*] Building ultra-compressed search.html...")
    v, lines, size = ws.build_search_page(compress=True)
    size_mb = size / 1048576.0
    print(f"[+] Search page ready: {v} videos · {lines:,} lines · {size_mb:.1f} MB")

    # 9. Mirror to root output/
    try:
        root_out = os.path.join(pipeline.ROOT, "output")
        os.makedirs(root_out, exist_ok=True)
        shutil.copy2(os.path.join(ws.out_dir, "search.html"), os.path.join(root_out, "search.html"))
        shutil.copy2(un_path, os.path.join(root_out, os.path.basename(un_path)))
        shutil.copy2(fo_path, os.path.join(root_out, os.path.basename(fo_path)))
        print("[+] Synchronized all output files to root output/ directory.")
    except Exception as e:
        print("[!] Note: Could not copy to root output/ folder:", e)

    # 10. Update meta.json
    meta["video_count"] = len(ws.load_videos())
    meta["captions_count"] = sum(1 for v in all_current_vids if ws.caption_path(v[0]))
    meta["words_count"] = sum(1 for v in all_current_vids if os.path.exists(ws.words_path(v[0])))
    meta["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    ws.save_meta(meta)

    # 11. Success summary
    page_path = os.path.join(ws.out_dir, "search.html")
    print(f"\n🌐 Live Search Page: {page_path}")
    print("\n✨ Update completed successfully!")


if __name__ == "__main__":
    main()
