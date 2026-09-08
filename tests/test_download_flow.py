# -*- coding: utf-8 -*-
"""
End-to-end decision tests for Downloader.download_track.

The sockseek binary and ffmpeg are replaced with fakes, so these run fully
offline. Metadata verification is stubbed to "always pass" so that the only
thing being measured is the SELECTION decision: which candidate the engine
attempts to download given the real ranking. (Metadata/tag verification is a
separate concern, covered elsewhere.)
"""
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from spotdlextended.downloader import Downloader
from track_fixtures import ALL_TRACKS, build_results, role_for


class _FakePopen:
    """Stand-in for subprocess.Popen used by the search call."""
    returncode = 0

    def __init__(self, payload):
        self._payload = payload

    def communicate(self, timeout=None):
        return self._payload, ""


def _install_subprocess_mocks(monkeypatch, payload, attempted):
    """Mock subprocess.Popen (search) and subprocess.run (download/transcode)."""

    def fake_popen(cmd, *args, **kwargs):
        return _FakePopen(payload)

    def fake_run(args, *a, **kw):
        if not args:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        head = os.path.basename(str(args[0]))

        if head == "sockseek":
            # download call: [sockseek, slsk://peer/filename, -o, tmpdir, ...]
            try:
                oi = args.index("-o")
            except ValueError:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            tmp = Path(args[oi + 1])
            tmp.mkdir(parents=True, exist_ok=True)
            slsk = args[oi - 1]
            fname = os.path.basename(slsk.rsplit("/", 1)[-1])
            (tmp / fname).write_bytes(b"\x00" * 5120)
            attempted.append(fname)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        if head == "mv":
            src, dst = args[1], args[2]
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(src, dst)
            except Exception:
                Path(dst).write_bytes(b"\x00" * 5120)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        if head == "ffmpeg":
            # transcode: [ffmpeg, ..., -y, out.mp3]
            Path(args[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(args[-1]).write_bytes(b"\x00" * 5120)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        # rm -rf and anything else: no-op success
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setattr("subprocess.run", fake_run)


@pytest.fixture
def flow_downloader(monkeypatch):
    d = Downloader(debug=False)
    monkeypatch.setattr(d, "tags_match_spotify", lambda *a, **k: (True, "mock"))
    monkeypatch.setattr(d, "verify_mp3_quality", lambda *a, **k: True)
    monkeypatch.setattr(d, "tag_mp3", lambda *a, **k: None)
    return d


@pytest.mark.parametrize("track", ALL_TRACKS, ids=lambda t: t["title"])
def test_download_track_attempts_correct_mix_first(monkeypatch, tmp_path, flow_downloader, track):
    """The first candidate the engine tries to download must be the correct one."""
    payload = json.dumps(build_results(track))
    attempted = []
    _install_subprocess_mocks(monkeypatch, payload, attempted)

    folder = tmp_path / "Playlist"
    folder.mkdir()
    library = tmp_path / "Library"
    library.mkdir()

    track_data = {
        "title": track["title"],
        "artist": track["artist"],
        "duration_ms": int(track["duration_secs"] * 1000),
        "uri": None,
        "isrc": "",
    }

    flow_downloader.download_track(
        track_data,
        str(folder),
        overwrite=False,
        playlist_only=False,
        get_extended=True,
        library_dir=str(library),
    )

    assert attempted, f"{track['title']}: no download was attempted"
    # Map the first attempted (basename) back to a candidate role.
    first_role = next(
        (role_for(track, c["filename"]) for c in track["candidates"]
         if os.path.basename(c["filename"]) == attempted[0]),
        None,
    )
    assert first_role == "correct_extended", (
        f"{track['title']}: the engine attempted to download "
        f"'{attempted[0]}' (role={first_role}); expected a download of the "
        f"correct extended mix '{os.path.basename(track['correct'])}'"
    )


def _install_failing_sockseek(monkeypatch, attempted):
    """sockseek always exits non-zero (stale transfer); rm/mkdir no-op success."""

    def fake_run(args, *a, **kw):
        if not args:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        head = os.path.basename(str(args[0]))
        if head == "sockseek":
            attempted.append(str(args[1]))
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)


def test_peer_banned_after_two_consecutive_transfer_failures(monkeypatch, tmp_path):
    """Two failed transfers from one peer ban it for the session; later candidates
    from the same peer (even across tracks) are skipped."""
    d = Downloader(debug=False)
    attempted = []
    _install_failing_sockseek(monkeypatch, attempted)

    folder = tmp_path / "P"
    target = tmp_path / "T"
    folder.mkdir(); target.mkdir()

    def cand(user, name, score=500):
        return {"username": user, "filename": name, "mix_type": "Standard",
                "score": score, "length": 300, "bitrate": 320, "ext": ".mp3"}

    # Three candidates from the same peer: after 2 failures the 3rd is skipped.
    d.download_from_candidates(
        [cand("badpeer", "badpeer/a.mp3", 900),
         cand("badpeer", "badpeer/b.mp3", 800),
         cand("badpeer", "badpeer/c.mp3", 700)],
        str(folder), str(target), "Title", "Artist", None, None,
    )
    assert "badpeer" in d.temp_peer_blacklist
    assert len(attempted) == 2, f"expected 2 attempts, got {attempted}"

    # A fresh candidate list (next track) with the same peer is skipped entirely.
    d.download_from_candidates(
        [cand("badpeer", "badpeer/d.mp3", 900)],
        str(folder), str(target), "Title", "Artist", None, None,
    )
    assert len(attempted) == 2, f"banned peer was retried: {attempted}"


def test_peer_fail_count_resets_after_successful_transfer(monkeypatch, tmp_path):
    """A peer that fails once but then delivers bytes is not banned (not consecutive)."""
    d = Downloader(debug=False)
    calls = {"n": 0}
    attempted = []

    def fake_run(args, *a, **kw):
        if not args:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        head = os.path.basename(str(args[0]))
        if head == "sockseek":
            calls["n"] += 1
            attempted.append(str(args[1]))
            if calls["n"] == 1:
                return SimpleNamespace(returncode=1, stdout="", stderr="")
            # second call succeeds: create a file in the -o tmp dir
            oi = args.index("-o")
            tmp = Path(args[oi + 1])
            tmp.mkdir(parents=True, exist_ok=True)
            (tmp / "ok.mp3").write_bytes(b"\x00" * 5120)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    folder = tmp_path / "P"
    target = tmp_path / "T"
    folder.mkdir(); target.mkdir()

    monkeypatch.setattr(d, "tags_match_spotify", lambda *a, **k: (True, "mock"))
    monkeypatch.setattr(d, "verify_mp3_quality", lambda *a, **k: True)
    monkeypatch.setattr(d, "tag_mp3", lambda *a, **k: None)

    def cand(user, name):
        return {"username": user, "filename": name, "mix_type": "Standard",
                "score": 500, "length": 300, "bitrate": 320, "ext": ".mp3"}

    d.download_from_candidates(
        [cand("flaky", "flaky/a.mp3"), cand("flaky", "flaky/b.mp3")],
        str(folder), str(target), "Title", "Artist", None, None,
    )
    assert "flaky" not in d.temp_peer_blacklist
    assert len(attempted) == 2
