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
