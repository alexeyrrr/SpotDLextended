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
        "duration_secs": 319,
        "remix_target": True,
        "note": "3-artist collab with Notre Dame as remixer; was failing because primary-artist-only query dropped Luch + Notre Dame. Real-name capture: tests/fixtures/ankhoi_luch_notre_dame_the_future_notre_dame_remix.json",
        "candidates": [
            {"role": "correct_extended",
             "filename": "Ankhoi & LUCH - THE FUTURE (Notre Dame Remix) (Extended Mix).mp3",
             "length": 319, "size": 12_955_171, "bitrate": 320},
            {"role": "correct_extended",
             "filename": "Notre Dame, Ankhoi, LUCH - THE FUTURE (Notre Dame Remix) [Ninja Tune].mp3",
             "length": 319, "size": 13_072_137, "bitrate": 320},
            {"role": "wrong",
             "filename": "Skrillex - Bangarang.mp3",
             "length": 230, "size": 8_000_000, "bitrate": 320},
            {"role": "set_excerpt",
             "filename": "DJ Mix - THE FUTURE (Continuous Mixed).mp3",
             "length": 2400, "size": 45_000_000, "bitrate": 320},
        ],
    },
    {
        "title": "Up Down Jumper",
        "artist": "Boris Brejcha",
        "duration_secs": 432,
        "remix_target": False,
        "note": "Spotify 432s = full original mix already on Soulseek. Engine used to pick 'Keep Rollin' (track 02 of the same EP) because folder/EP-name inflation and length bonus beat the genuine file. Capture: tests/fixtures/boris_brejcha_up_down_jumper.json",
        "correct": "Boris Brejcha - Up Down Jumper (Original Mix).mp3",
        "candidates": [
            {"role": "correct_extended",
             "filename": "Boris Brejcha - Up Down Jumper (Original Mix).mp3",
             "length": 432, "size": 17_581_855, "bitrate": 320},
            {"role": "standard",
             "filename": "Boris Brejcha - Up Down Jumper.mp3",
             "length": 432, "size": 17_401_350, "bitrate": 320},
            {"role": "wrong",
             "filename": "02 - Keep Rollin (Original Mix).flac",
             "length": 480, "size": 58_806_091, "bitrate": 0},
            {"role": "wrong",
             "filename": "Boris Brejcha - Up Down Jumper - 02 - Keep Rollin (original mix).flac",
             "length": 480, "size": 58_870_342, "bitrate": 0},
            {"role": "set_excerpt",
             "filename": "DJ Set - Boris Brejcha Live @ Fusion (Mixed).mp3",
             "length": 5400, "size": 60_000_000, "bitrate": 320},
            {"role": "set_excerpt",
             "filename": "Boris Brejcha - Up Down Jumper (Live).mp3",
             "length": 440, "size": 18_000_000, "bitrate": 320},
        ],
    },
    {
        "title": "This & That",
        "artist": "Beachcrimes",
        "duration_secs": 119,
        "remix_target": False,
        "note": "Spotify radio edit is 119s (unusably short) — must fetch the ~177s Intro/club mix. Capture: tests/fixtures/beachcrimes_this_that.json",
        "correct": "Beachcrimes - This & That (Intro Dirty).mp3",
        "candidates": [
            {"role": "correct_extended",
             "filename": "Beachcrimes - This & That (Intro Dirty).mp3",
             "length": 177, "size": 7_307_080, "bitrate": 320},
            {"role": "standard",
             "filename": "Beachcrimes - This & That (Dirty Radio).mp3",
             "length": 119, "size": 4_966_578, "bitrate": 320},
            {"role": "wrong",
             "filename": "Beachcrimes - This That Bass.mp3",
             "length": 177, "size": 7_278_770, "bitrate": 320},
            {"role": "set_excerpt",
             "filename": "DJ Mix 2026 - Beachcrimes (Continuous Mixed).mp3",
             "length": 3600, "size": 45_000_000, "bitrate": 320},
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
