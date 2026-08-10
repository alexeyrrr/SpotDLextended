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
        "title": "Are You The Same",
        "artist": "Kyle Watson, Body Ocean",
        "duration_secs": 161,  # TODO confirm real spotify duration
        "remix_target": False,
        "note": "script reports no extended mix, but it exists on Soulseek",
        "candidates": [

        ],
    },
    {
        "title": "Don't Fix Me",
        "artist": "April Girl, RYVM",
        "duration_secs": 154, 
        "remix_target": False,
        "note": "nothing downloaded at all, but it's easily downloadable manually",
        "candidates": [
        ],
    },
    {
        "title": "What's A Girl To Do (Yuvèe Remix)",
        "artist": "Luvstruck, Yuvèe",
        "duration_secs": 174, 
        "remix_target": True,
        "note": "extended mix not found; correct edition is the 5m56s FLAC (356s)",
        "candidates": [
        ],
    },
    {
        "title": "Do Nothing",
        "artist": "trillbot",
        "duration_secs": 147,  
        "remix_target": False,
        "note": "nothing downloaded at all, but it's easily downloadable manually",
        "candidates": [
        ],
    },
        {
        "title": "1st Thing",
        "artist": "Tonii Boii, Bigga Rankin",
        "duration_secs": 147,  
        "remix_target": False,
        "note": "nothing downloaded at all, but it's easily downloadable manually",
        "candidates": [

        ],
    },    
    {
        "title": "on my mind v2(vacay mode)",
        "artist": "abelon",
        "duration_secs": 175,  
        "remix_target": False,
        "note": "nothing downloaded at all, but it's easily downloadable manually",
        "candidates": [

        ],
    },   
    {
        "title": "My Vibe",
        "artist": "Hutcher, Alyzée",
        "duration_secs": 161,  
        "remix_target": False,
        "note": "correct extended exists on Soulseek credited to a different artist: 'Hutcher, Honey - My Vibe (Extended Mix)'",
        "candidates": [
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
