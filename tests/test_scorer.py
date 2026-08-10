# -*- coding: utf-8 -*-
"""
Unit tests for Downloader.heuristic_filter_and_score -- the pure candidate
ranking engine that decides which Soulseek result to download.

These are offline and deterministic: they feed a mock sockseek result bundle in
and assert the ranking reflects what a correct decision engine *should* do:
the genuine extended mix must outrank DJ-set excerpts and wrong tracks.
"""
import pytest

from spotdlextended.downloader import Downloader
from track_fixtures import ALL_TRACKS, build_results, role_for


@pytest.fixture(scope="session")
def engine():
    return Downloader(debug=False)


@pytest.mark.parametrize("track", ALL_TRACKS, ids=lambda t: t["title"])
def test_correct_extended_ranked_first(engine, track):
    """The known-correct extended mix must be the #1 candidate."""
    results = build_results(track)
    ranked = engine.heuristic_filter_and_score(
        results, track["title"], track["artist"], track["duration_secs"], get_extended=True
    )
    assert ranked, f"{track['title']}: no candidates survived filtering"
    top = ranked[0]
    assert role_for(track, top["filename"]) == "correct_extended", (
        f"{track['title']}: top candidate is '{top['filename']}' "
        f"(score={top['score']}, mix_type={top['mix_type']}); "
        f"expected correct extended '{track['correct']}'"
    )


@pytest.mark.parametrize("track", ALL_TRACKS, ids=lambda t: t["title"])
def test_set_excerpt_never_beats_correct_extended(engine, track):
    """A long set rip must never outrank the genuine extended mix."""
    results = build_results(track)
    ranked = engine.heuristic_filter_and_score(
        results, track["title"], track["artist"], track["duration_secs"], get_extended=True
    )
    if not ranked:
        pytest.skip(f"{track['title']}: no candidates (nothing to rank)")

    correct_pos = None
    for i, c in enumerate(ranked):
        role = role_for(track, c["filename"])
        if role == "correct_extended":
            correct_pos = i
        elif role == "set_excerpt":
            assert i > correct_pos if correct_pos is not None else False, (
                f"{track['title']}: set excerpt {c['filename']} ranked above the "
                f"correct extended mix (correct at #{correct_pos}, excerpt at #{i})"
            )


@pytest.mark.parametrize("track", ALL_TRACKS, ids=lambda t: t["title"])
def test_set_excerpt_is_not_flagged_as_extended_mix(engine, track):
    """A DJ-set rip must not be classified by the engine as an 'Extended Mix'."""
    results = build_results(track)
    ranked = engine.heuristic_filter_and_score(
        results, track["title"], track["artist"], track["duration_secs"], get_extended=True
    )
    for c in ranked:
        if role_for(track, c["filename"]) == "set_excerpt":
            assert c["mix_type"] != "Extended Mix", (
                f"{track['title']}: set excerpt '{c['filename']}' wrongly labelled "
                f"'{c['mix_type']}' (score={c['score']})"
            )


@pytest.mark.parametrize("track", ALL_TRACKS, ids=lambda t: t["title"])
def test_standard_edit_is_not_ranked_above_correct_extended(engine, track):
    """The main/radio edit must not beat the genuine extended mix."""
    results = build_results(track)
    ranked = engine.heuristic_filter_and_score(
        results, track["title"], track["artist"], track["duration_secs"], get_extended=True
    )
    if not ranked:
        pytest.skip(f"{track['title']}: no candidates (nothing to rank)")

    correct_pos = None
    for i, c in enumerate(ranked):
        role = role_for(track, c["filename"])
        if role == "correct_extended":
            correct_pos = i
        elif role == "standard":
            assert i > correct_pos if correct_pos is not None else False, (
                f"{track['title']}: standard edit ranked above correct extended "
                f"(correct at #{correct_pos}, standard at #{i})"
            )


@pytest.mark.parametrize("track", ALL_TRACKS, ids=lambda t: t["title"])
def test_wrong_track_is_filtered_out_or_ranked_last(engine, track):
    """Tracks with a mismatched artist/title must not be a top pick."""
    results = build_results(track)
    ranked = engine.heuristic_filter_and_score(
        results, track["title"], track["artist"], track["duration_secs"], get_extended=True
    )
    if not ranked:
        return

    correct_pos = next(
        (i for i, c in enumerate(ranked) if role_for(track, c["filename"]) == "correct_extended"),
        None,
    )
    if correct_pos is None:
        return  # nothing to anchor a wrong-track comparison against

    wrong_before_correct = [
        c["filename"]
        for i, c in enumerate(ranked)
        if role_for(track, c["filename"]) == "wrong" and i < correct_pos
    ]
    assert not wrong_before_correct, (
        f"{track['title']}: wrong track(s) ranked above the correct extended mix: "
        f"{wrong_before_correct}"
    )
