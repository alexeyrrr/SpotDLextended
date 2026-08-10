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
        "correct": "Are You The Same (Extended Mix) - Kyle Watson, Body Ocean.mp3",
        "candidates": [
            {"role": "correct_extended", "filename": "Are You The Same (Extended Mix) - Kyle Watson, Body Ocean.mp3",
             "length": 260, "bitrate": 320, "size": 10_000_000},
            {"role": "set_excerpt", "filename": "Are You The Same - Kyle Watson, Body Ocean (DJ Mix).mp3",
             "length": 420, "bitrate": 320, "size": 16_000_000},
            {"role": "standard", "filename": "Are You The Same - Kyle Watson, Body Ocean.mp3",
             "length": 196, "bitrate": 320, "size": 7_400_000},
            {"role": "wrong", "filename": "Are You The Same? (Demo) - Unknown Artist.mp3",
             "length": 150, "bitrate": 192, "size": 4_000_000},
        ],
    },
    {
        "title": "Don't Fix Me",
        "artist": "April Girl, RYVM",
        "duration_secs": 154, 
        "remix_target": False,
        "note": "nothing downloaded at all, but it's easily downloadable manually",
        "correct": "Don't Fix Me (Extended Mix) - April Girl, RYVM.mp3",
        "candidates": [
            {"role": "correct_extended", "filename": "Don't Fix Me (Extended Mix) - April Girl, RYVM.mp3",
             "length": 270, "bitrate": 320, "size": 10_400_000},
            {"role": "set_excerpt", "filename": "Don't Fix Me - April Girl, RYVM (Club Mix).mp3",
             "length": 390, "bitrate": 320, "size": 15_000_000},
            {"role": "standard", "filename": "Don't Fix Me - April Girl, RYVM.mp3",
             "length": 205, "bitrate": 320, "size": 8_100_000},
        ],
    },
    {
        "title": "What's A Girl To Do (Yuvèe Remix)",
        "artist": "Luvstruck, Yuvèe",
        "duration_secs": 174, 
        "remix_target": True,
        "note": "extended mix not found; correct edition is the 5m56s FLAC (356s)",
        "correct": "What's A Girl To Do (Yuvèe Remix) - Luvstruck, Yuvèe.flac",
        "candidates": [
            {"role": "correct_extended", "filename": "What's A Girl To Do (Yuvèe Remix) - Luvstruck, Yuvèe.flac",
             "length": 356, "bitrate": 0, "size": 42_000_000},
            {"role": "set_excerpt", "filename": "What's A Girl To Do (Yuvèe Remix) - Essential Mix.mp3",
             "length": 420, "bitrate": 320, "size": 16_500_000},
            {"role": "wrong", "filename": "What's A Girl To Do (Radio Edit) - Luvstruck.mp3",
             "length": 200, "bitrate": 192, "size": 7_000_000},
        ],
    },
    {
        "title": "Do Nothing",
        "artist": "trillbot",
        "duration_secs": 147,  
        "remix_target": False,
        "note": "nothing downloaded at all, but it's easily downloadable manually",
        "correct": "Do Nothing (Extended Mix) - trillbot.mp3",
        "candidates": [
            {"role": "correct_extended", "filename": "Do Nothing (Extended Mix) - trillbot.mp3",
             "length": 235, "bitrate": 320, "size": 9_300_000},
            {"role": "set_excerpt", "filename": "Do Nothing - trillbot (DJ Mix).mp3",
             "length": 400, "bitrate": 320, "size": 15_800_000},
            {"role": "standard", "filename": "Do Nothing - trillbot.mp3",
             "length": 175, "bitrate": 320, "size": 6_900_000},
        ],
    },
        {
        "title": "1st Thing",
        "artist": "Tonii Boii, Bigga Rankin",
        "duration_secs": 147,  
        "remix_target": False,
        "note": "nothing downloaded at all, but it's easily downloadable manually",
        "correct": "Do Nothing (Extended Mix) - trillbot.mp3",
        "candidates": [

        ],
    },    
    {
        "title": "My Vibe",
        "artist": "Hutcher, Alyzée",
        "duration_secs": 161,  
        "remix_target": False,
        "note": "correct extended exists on Soulseek credited to a different artist: 'Hutcher, Honey - My Vibe (Extended Mix)'",
        "correct": "Hutcher, Honey - My Vibe (Extended Mix).mp3",
        "candidates": [
            {"role": "correct_extended", "filename": "Hutcher, Honey - My Vibe (Extended Mix).mp3",
             "length": 250, "bitrate": 320, "size": 9_900_000},
            {"role": "set_excerpt", "filename": "My Vibe - Hutcher, Alyzée (Live Mix).mp3",
             "length": 380, "bitrate": 320, "size": 15_000_000},
            {"role": "standard", "filename": "My Vibe - Hutcher, Alyzée.mp3",
             "length": 180, "bitrate": 320, "size": 7_100_000},
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
