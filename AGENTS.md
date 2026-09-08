# SpotDLextended — agent instructions

## Project
Downloads Spotify playlist tracks as 320kbps MP3 via Soulseek P2P (`sockseek`). Generates `.m3u8` playlists and `rekordbox.xml`. Entrypoint: `spotdlextended/__main__.py:main()`.

## Commands
- `python3 -m venv .venv && source .venv/bin/activate && pip install -e .` — dev install (use `.venv`, never install globally)
- `pytest` — run tests (use `.venv/bin/pytest`)
- `spotdlextended -u <URL>` — download a playlist
- `spotdlextended -u <URL> --debug` — verbose mode (also passed to sockseek)
- `spotdlextended -p -u <URL>` — playlist-only (no downloads)
- `spotdlextended -e -u <URL>` — upgrade existing standard mixes to extended
- `spotdlextended -r "/path/to/Folder"` — regenerate m3u8/xml for an existing folder
- `spotdlextended -f -u <URL>` — force re-download

## Key architecture
- `settings.json` at project root (generated on first run). Path config via `download_dir`, `get_extended_mixes`, `full_overwrite`, `playlist_only`, `rekordbox_path_mapping`
- `sockseek` binary at `~/.local/bin/sockseek` (Linux/macOS) or bundled in PyInstaller exe; config at `~/.config/sockseek/sockseek.conf`
- `spotify_scraper` (headless, no API key) fetches playlist metadata
- Soulseek credentials required — script prompts on first run if missing

## Library search behavior
When a track exists elsewhere in the library, `find_existing_track_in_library` (downloader.py:898-915) walks the entire `library_dir` and:
- Returns the **absolute path** to the existing file — no download, no copy, no move
- The m3u8 playlist links to the original location via absolute path only
- Matching uses: filename-based fuzzy (artist >= 70, title >= 70), ISRC check, then tag-based fallback

### Known duplicate issue
Tracks can end up duplicated across playlist folders because:
1. The library search was added on **2026-07-08** — most duplicates precede this
2. The original implementation used `get_primary_artist` (first artist only) instead of `normalize_all_artists` — this was fixed on July 11
3. The `playlist_only` flag was dead code (passed to `download_track` but never checked) until it was fixed in the current session — it now correctly skips downloads in playlist-only mode

After `git pull`, run `source .venv/bin/activate && pip install -e .` to pick up library search improvements.

## Tests
- Run with `source .venv/bin/activate && pytest`
- `tests/` contains scorer + download-flow + search-query decision tests seeded with real tracks (`tests/track_fixtures.py`) the engine got wrong:
  - `build_search_queries` (downloader.py:1096-1124) returns 3 variants: full-artists, last-artist, primary-only. `find_top_candidates` tries them in order; first with hits wins.
  - `heuristic_filter_and_score` labels any candidate ≥30s longer than the spotify duration as "Extended Mix" (+1000) and treats `dj mix`/`club mix` as extended keywords (+500)
  - Hard-disqualify keywords (downloader.py:209) are a one-line tuple: `("mixed", "live")`. Add new ones there.
  - `tags_match_spotify` accepts partial-artist matches (tag artists are a subset of spotify artists) — confirmed by user as acceptable

## Important details
- `settings.json` is gitignored — don't commit it
- Sync history: `.sync_history.json` in each playlist folder tracks previous downloads; standard mixes get a 14-day cooldown before retry
- Peer blacklist: peers that reject transfers (queue full, country block) are blacklisted per session via `self.temp_peer_blacklist`
- WSL path translation: `C:/...` → `/mnt/c/...` for native Linux sockseek; reverse for m3u8/XML
- `archive_orphaned_files()` moves files removed from the Spotify playlist into an `Archived/` subfolder
- MP3 spectral verification checks for 16kHz/18.5kHz brickwall cutoffs to reject fake 320kbps