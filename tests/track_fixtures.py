# -*- coding: utf-8 -*-
"""
Fixtures for the Soulseek decision-engine tests.

Each track encodes the metadata a Spotify playlist row provides (title,
artist, duration) and a *bundle* of mock Soulseek search results. Every
candidate has a `role` that marks what the CORRECT decision should be:

    correct_extended - a genuine extended / original / club / remix edit that
        is known to exist on Soulseek and SHOULD be selected for download.
    set_excerpt      - a track ripped out of a continuous DJ set / radio show.
        It is merely *longer*, not a real mix. Downloading this instead of the
        genuine extended mix is the exact bug we are guarding against.
    standard         - the radio edit / main mix.
    wrong            - a completely different song.

The scorer test asserts the top-ranked candidate is `correct_extended` and
that no `set_excerpt` outranks it.

NOTE on durations: `duration_secs` is a placeholder (~spotify length_ms / 1000)
for the real tracks. Confirm each one and adjust if needed. `length` on a
candidate is the Soulseek file duration in seconds.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Synthetic control cases (always run, no external knowledge needed)
# ─────────────────────────────────────────────────────────────────────────────
SYNTHETIC_TRACKS = []

# ─────────────────────────────────────────────────────────────────────────────
# Real tracks the engine has repeatedly gotten wrong (provided by the user)
# ─────────────────────────────────────────────────────────────────────────────
REAL_TRACKS = [
    {
        "title": "THE FUTURE - Notre Dame Remix - Edit",
        "artist": "Ankhoi, Luch, Notre Dame",
        "duration_secs": 320,
        "remix_target": True,
        "note": "3-artist collab with Notre Dame as remixer; was failing because primary-artist-only query dropped Luch + Notre Dame",
        "correct": "Ankhoi, Luch, Notre Dame - THE FUTURE (Notre Dame Remix Edit).mp3",
        "candidates": [
            {"role": "correct_extended",
             "filename": "Ankhoi, Luch, Notre Dame - THE FUTURE (Notre Dame Remix Edit).mp3",
             "length": 318, "size": 9_000_000, "bitrate": 320},
            {"role": "correct_extended",
             "filename": "Notre Dame - THE FUTURE (Remix).mp3",
             "length": 320, "size": 9_000_000, "bitrate": 320},
            {"role": "wrong",
             "filename": "Skrillex - Bangarang.mp3",
             "length": 230, "size": 8_000_000, "bitrate": 320},
            {"role": "set_excerpt",
             "filename": "DJ Set 2024 - THE FUTURE (Continuous Mixed).mp3",
             "length": 3600, "size": 50_000_000, "bitrate": 320},
        ],
    },
]

ALL_TRACKS = SYNTHETIC_TRACKS + REAL_TRACKS


# ─────────────────────────────────────────────────────────────────────────────
# Builders shared by the scorer and download-flow tests
# ─────────────────────────────────────────────────────────────────────────────
def build_results(track):
    """Convert a track's candidates into the sockseek `--print json-all` shape."""
    items = []
    for i, c in enumerate(track["candidates"]):
        items.append({
            "User": {
                "Username": f"peer{i}",
                "UploadSpeed": 100 * (i + 1),
                "HasFreeUploadSlot": c.get("free_slot", True),
            },
            "Files": [{
                "Filename": c["filename"],
                "Length": c["length"],
                "Size": c.get("size", 8_000_000),
                "Bitrate": c.get("bitrate", 320),
                "SampleRate": 44100,
                "BitDepth": c.get("filenamedepth", 0),
            }],
        })
    return items


def role_for(track, filename):
    for c in track["candidates"]:
        if c["filename"] == filename:
            return c["role"]
    return None


def top_two_roles(track, ranked):
    """Map the first two ranked candidates to their roles (may be shorter)."""
    roles = [role_for(track, c["filename"]) for c in ranked]
    return roles
