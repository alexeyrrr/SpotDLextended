# Refactor SpotDLextended downloader for testability

## Context
Project: **SpotDLextended** — a Python CLI that downloads Spotify playlist tracks as
320 kbps MP3 via Soulseek (`sockseek`). Working file: `spotdlextended/downloader.py`
(~1186 lines). The method `Downloader.download_track` (lines ~732-1173) currently does
everything inline: sync-history checks, library search, query construction, the sockseek
search, candidate scoring, per-candidate download, metadata verification, spectral
320 kbps check, transcode, tagging, and fallback/NFO writing.

`Downloader.heuristic_filter_and_score` (lines ~138-263) is already a pure, offline
ranking function. **Do not change its logic** (its DJ-set-excerpt scoring bug is out of
scope).

## Goal
Split `download_track` into three methods so each component is independently testable
offline. Structure the code so a multi-query retry loop (re-search with a different
query when a download fails) can be added later, **but do not implement that loop now**.

## Deliverables

### 1. Extract `fetch_sockseek_results(...)` + `find_top_candidates(...)`
Extract the query construction (lines ~928-952) + the sockseek search execution
(lines ~954-975) + the `heuristic_filter_and_score` call (lines ~973-975) out of
`download_track`. Split the search I/O into its own smallest unit so tests can
inspect raw results independently of ranking.

```python
def fetch_sockseek_results(self, query, timeout=None):
    """Run `sockseek <query> --print json-all`; return the raw results list.
    On failure (nonzero exit / JSON parse error) returns []. timeout bounds the
    search so live callers (tests) cannot hang the process; None = current
    unbounded behavior."""
```

```python
def find_top_candidates(self, spotify_title, spotify_artist, spotify_duration_secs,
                        get_extended, query_variant=None, timeout=None):
    """Build a query, fetch sockseek results, score via heuristic_filter_and_score.

    Returns (ranked_candidates, query_used). query_variant exists so the
    orchestrator can later retry with different query strings; for now it is
    ignored (single default query). On search failure returns ([], query_used).
    timeout is passed through to fetch_sockseek_results."""
```

- Preserve today's behavior exactly: debug flag passthrough, `json.loads` error
  handling → empty list, blacklist-word stripping.
- `query_variant` is required to exist in the signature but must NOT trigger any
  multi-query behavior.
- `fetch_sockseek_results` must pass `timeout` to `proc.communicate(timeout=...)`.
- **Flag nuance:** the orchestrator computes `has_inherent_mix` (line ~923) and
  currently calls the scorer with `get_extended and not has_inherent_mix` (line ~974).
  `find_top_candidates` must receive and pass through the **already-combined** flag —
  do NOT combine it inside `find_top_candidates`, or scoring behavior changes.

### Live-test seam
`fetch_sockseek_results` and `find_top_candidates` are the intended targets for
live tests: tests call them with a real track's title/artist/duration, no download
is involved, and assertions are made on real Soulseek results. Keep them as
standalone callable methods; do not inline their bodies into `download_track`.
`fetch_sockseek_results` gives tests access to the raw results so they can verify
filtering decisions (what `heuristic_filter_and_score` kept vs. dropped), while
`find_top_candidates` verifies the final ranking.

### 2. Extract `download_from_candidates(...)`
Extract the candidate-attempt loop (lines ~980-1079): download via `slsk://` URI,
peer-blacklist handling for "Too many files" / country-blocked (lines ~1010-1020),
metadata match check, MP3 spectral 320 check, transcode via ffmpeg, move into place,
and the success `break`.

Note: `mix_type` already lives on each candidate dict (set by
`heuristic_filter_and_score`), so it is read per-candidate — no separate mix_type
argument needed. `folder` is required alongside `target_download_folder` because
the temp dir is created under `folder` (line ~947) while the final file is moved
to `target_download_folder` — these differ in `upgrade_extended` mode.

```python
@dataclass
class DownloadAttemptResult:
    status: str            # "success" | "failed"
    filepath: str | None   # final mp3 path on success
    candidate: dict | None # the winning candidate
    mix_type: str | None   # from the winning candidate

def download_from_candidates(self, candidates, folder, target_download_folder,
                             spotify_title, spotify_artist, spotify_uri,
                             spotify_isrc) -> DownloadAttemptResult:
    """Try each candidate in order; return the first that passes all checks.
    Never raises on per-candidate failure — record and move to the next."""
```

- **Per-query attempt cap (in `download_from_candidates`):** `download_from_candidates`
  owns the `MAX_DOWNLOAD_ATTEMPTS` cap (line ~22, value 6) and applies it to whatever
  candidate list it receives. Because the orchestrator calls it once per query, the
  cap is naturally **per query** — each query's candidates get up to 6 download
  attempts, independent of other queries. This preserves today's single-query behavior
  exactly (one query → top 6 attempted) and makes the future multi-query loop correct
  without extra work. `find_top_candidates` returns the **full** ranked list (uncapped).
- **Critical:** the session peer blacklist (`self.temp_peer_blacklist`) must persist
  across calls — a peer rejected in one attempt stays blacklisted on later calls
  (needed for the future retry loop). Keep blacklisting on `self` or pass it through.

### 3. Slim `download_track(...)` into an orchestrator
KEEP unchanged in the orchestrator:
- Sync-history skip / standard-mix cooldown (lines ~761-813)
- `upgrade_extended` handling incl. existing-file detection (lines ~818-855)
- Existing-file MP3/FLAC skips (lines ~860-893)
- Global library search (lines ~897-915) and `playlist_only` mode (~917-920)
- Inherent-mix detection (lines ~922-926)
- Temp-dir cleanup (~1081-1083), failure fallback + NFO + history (~1085-1114)
- Upgrade file removal + m3u8 playlist rewrite (~1116-1141)
- Tagging + success sync-history (~1143-1167)

REPLACE the inline search+download body with a single sequential path:
1. `candidates, query_used = self.find_top_candidates(...)` (pass
   `get_extended and not has_inherent_mix` as the get_extended arg)
2. `result = self.download_from_candidates(candidates, folder, ...)` (the
   `MAX_DOWNLOAD_ATTEMPTS` cap is applied inside, per query)
3. Existing fallback/finalize logic driven by `result.status`.

To make the future retry loop obvious, define a module-level tuple
`QUERY_VARIANTS = ("default",)` and iterate it with a `for query in QUERY_VARIANTS:`
skeleton — but only if it does not change current single-query behavior. If the loop
skeleton adds any risk, use the plain sequential call and leave a one-line comment
noting where the retry loop will go. Correctness beats elegance here.

## Scope boundaries (do NOT do)
- No multiple queries, no query cascade, no retry-on-failure. Structure only.
- No changes to `heuristic_filter_and_score` logic.
- No behavioral change to `download_track`'s return values (`(filename, mix_type)` /
  skip / error paths) beyond refactoring-induced equivalence.
- No changes to settings, cli, __main__, xml_exporter, or spotify_scraper.
- No test rework in this refactor — live-test strategy is a separate follow-up
  that will target `fetch_sockseek_results` / `find_top_candidates`.


## Definition of done
1. `download_track` / `find_top_candidates` / `fetch_sockseek_results` /
   `download_from_candidates` exist with clear, single responsibilities.
2. Download outcomes for the single-query path are unchanged from before the refactor.
