# -*- coding: utf-8 -*-
"""
Capture live Soulseek search results for the tracks in track_fixtures.py.

For each track it runs the SAME query the engine would build (via
Downloader.build_search_query) through sockseek, saves the raw results to
tests/fixtures/<slug>.json, and prints the heuristic's ranking so the scorer
can be inspected and refined against real data.

Usage:
    python tests/capture_search.py                 # all tracks
    python tests/capture_search.py --index 0       # just one track
    python tests/capture_search.py --name "My Vibe"
    python tests/capture_search.py --outdir /tmp/captures
    python tests/capture_search.py --timeout 60

The script runs live searches and requires sockseek credentials/network.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from spotdlextended.downloader import Downloader
from track_fixtures import ALL_TRACKS


def slugify(title, artist):
    raw = f"{artist} - {title}"
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", raw).strip("_").lower()
    return slug or "track"


def flatten_files(results):
    """Yield (username, file_dict) pairs from a raw sockseek json-all payload."""
    for item in results:
        username = item.get("User", {}).get("Username", "?")
        for f in item.get("Files", []):
            yield username, f


def fmt_size(size):
    return f"{size / 1_000_000:.1f}MB" if size else "-"


def role_hint(filename, track):
    """Best-effort hint for which candidate this is, for quick eyeballing."""
    base = filename.lower()
    correct = track.get("correct")
    if correct and os.path.basename(correct).lower() == filename.lower():
        return "MATCHES-correct"
    if any(k in base for k in ("dj mix", "club mix", "radio 1 mix", "essential mix",
                               "live mix", "full set", "continuous mix", "mixed")):
        return "?set-excerpt"
    if "extended" in base or "original mix" in base or "club mix" in base or "12\"" in base:
        return "?extended"
    if "remix" in base:
        return "?remix"
    if any(k in base for k in ("radio edit", "radio version", "clean")):
        return "?standard"
    return "?"


def capture_one(downloader, track, outdir, timeout):
    title, artist = track["title"], track["artist"]
    duration_secs = track.get("duration_secs", 0)

    query = downloader.build_search_query(title, artist)
    print(f"\n{'=' * 70}")
    print(f"[{title}] — {artist}  (dur ~{duration_secs}s)")
    print(f"  query: '{query}'")

    results = downloader.fetch_sockseek_results(query, timeout=timeout)

    if not results:
        print("  [!] no results returned (search failed or nothing found)")
        return None

    n_files = sum(1 for _ in flatten_files(results))
    print(f"  raw results: {len(results)} users / {n_files} files")

    # What the heuristic keeps and how it ranks it.
    ranked = downloader.heuristic_filter_and_score(
        results, title, artist, duration_secs, get_extended=True
    )
    print(f"  heuristic kept: {len(ranked)} / {n_files}")

    payload = {
        "track": {"title": title, "artist": artist, "duration_secs": duration_secs},
        "query": query,
        "results": results,
    }
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / f"{slugify(title, artist)}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"  saved: {path}")

    if ranked:
        print("  top ranked candidates:")
        for c in ranked[:15]:
            print(
                f"    score={c['score']:<5} {c['mix_type']:<12} "
                f"{fmt_size(c['size']):<9} {c['length']}s "
                f"{(c['bitrate'] or '?')}kbps {c['ext']:<5} "
                f"{role_hint(c['filename'], track):<18} "
                f"{os.path.basename(c['filename'])[:70]}"
            )
    else:
        print("  [!] heuristic filtered everything out — inspect raw results")
        for username, f in flatten_files(results):
            print(
                f"    (dropped) {os.path.basename(f.get('Filename',''))[:70]} "
                f"| {f.get('Length')}s | {f.get('Bitrate')}kbps"
            )

    return payload


def main():
    parser = argparse.ArgumentParser(description="Capture live sockseek search results.")
    parser.add_argument("--index", type=int, default=None, help="Capture only this track index.")
    parser.add_argument("--name", type=str, default=None, help="Capture only this track title.")
    parser.add_argument("--outdir", type=str, default="tests/fixtures", help="Where to save JSON.")
    parser.add_argument("--timeout", type=int, default=60, help="Search timeout in seconds.")
    args = parser.parse_args()

    tracks = ALL_TRACKS
    if args.index is not None:
        tracks = [tracks[args.index]]
    elif args.name:
        tracks = [t for t in tracks if args.name.lower() in t["title"].lower()]
        if not tracks:
            print(f"No track found with title containing '{args.name}'")
            sys.exit(1)

    if not tracks:
        print("No tracks to capture (ALL_TRACKS is empty).")
        sys.exit(0)

    downloader = Downloader(debug=False)
    outdir = Path(args.outdir) if args.outdir else None

    for track in tracks:
        capture_one(downloader, track, outdir, args.timeout)

    print(f"\nDone. Raw results saved under: {outdir}")


if __name__ == "__main__":
    main()
