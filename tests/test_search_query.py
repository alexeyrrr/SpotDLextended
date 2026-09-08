from spotdlextended.downloader import Downloader


def _dl():
    return Downloader(debug=False)


def test_notre_dame_remix_returns_three_variants_in_order():
    d = _dl()
    variants = d.build_search_queries(
        "THE FUTURE - Notre Dame Remix - Edit",
        "Ankhoi, Luch, Notre Dame",
    )

    assert len(variants) == 3

    # Variant 0 — all artists joined (broadest)
    assert "ankhoi" in variants[0]
    assert "luch" in variants[0]
    assert "notre dame" in variants[0]

    # Mix keywords stripped from query (hard filter enforces them on results)
    assert "remix" not in variants[0].lower()
    assert "edit" not in variants[0].lower()

    # Variant 1 — last ARTIST (not just last token); for "Ankhoi, Luch, Notre Dame"
    # the remixer is Notre Dame, so variant 1 is "Luch Notre Dame + title" —
    # narrower than variant 0 but broader than "dame" alone would have been.
    assert "notre dame" in variants[1]
    assert "ankhoi" not in variants[1]
    assert "luch" in variants[1]

    # Variant 2 — primary artist fallback (still gets title-side tokens like "Notre Dame")
    assert "ankhoi" in variants[2]
    assert "the future" in variants[2]
    # Variant 2 must NOT include the other full artists
    assert "luch" not in variants[2]


def test_variants_strip_parens_and_title_keywords():
    d = _dl()
    variants = d.build_search_queries(
        "Up Down Jumper (Extended Mix)",
        "Boris Brejcha",
    )

    for v in variants:
        # Title's (Extended Mix) parens are stripped; mix keywords gone too
        assert "extended mix" not in v.lower()
        assert "jumper" in v


def test_primary_only_artist_yields_single_token_variants():
    d = _dl()
    variants = d.build_search_queries(
        "Are You The Same",
        "Kyle Watson, Body Ocean",
    )

    # All 3 artists joined — broadest
    assert "kyle watson" in variants[0]
    assert "body ocean" in variants[0]
    # Last token (token-level, not name-level)
    assert variants[1].endswith("are you the same")
    # Primary (first) artist fallback
    assert "kyle watson" in variants[2]
    assert "body ocean" not in variants[2]


def test_single_artist_dedupes_to_one_query():
    """Single artist → all 3 variants identical; must not query sockseek 3×."""
    d = _dl()
    variants = d.build_search_queries(
        "Up Down Jumper",
        "Boris Brejcha",
    )

    assert len(variants) == 1
    assert variants[0] == "boris brejcha up down jumper"


def test_two_artists_keeps_three_variants():
    d = _dl()
    variants = d.build_search_queries(
        "Are You The Same",
        "Kyle Watson, Body Ocean",
    )

    assert len(variants) == 3


def test_find_top_candidates_uses_first_variant_with_results(monkeypatch):
    """First variant with hits wins; results from later variants not consulted."""
    d = _dl()

    fake_results = [{"User": {"Username": "peerA"}, "Files": [
        {"Filename": "Ankhoi Luch Notre Dame - The Future (Remix).mp3",
         "Length": 320, "Size": 9_000_000, "Bitrate": 320, "SampleRate": 44100}
    ]}]

    calls = []

    def fake_fetch(self, query, timeout=60):
        calls.append(query)
        return fake_results

    monkeypatch.setattr(type(d), "fetch_sockseek_results", fake_fetch)
    monkeypatch.setattr(type(d), "heuristic_filter_and_score",
                        lambda self, results, *a, **k: results)

    _, used = d.find_top_candidates(
        "THE FUTURE - Notre Dame Remix - Edit",
        "Ankhoi, Luch, Notre Dame",
        320,
        get_extended=True,
    )

    assert used.startswith("ankhoi luch notre dame")
    assert len(calls) == 1, "second variant should not be tried when first has hits"


def test_find_top_candidates_returns_empty_on_all_misses(monkeypatch):
    d = _dl()

    monkeypatch.setattr(type(d), "fetch_sockseek_results",
                        lambda self, q, timeout=60: [])

    ranked, used = d.find_top_candidates(
        "THE FUTURE - Notre Dame Remix - Edit",
        "Ankhoi, Luch, Notre Dame",
        320,
        get_extended=True,
    )

    assert ranked == []
    assert used.startswith("ankhoi luch notre dame")
