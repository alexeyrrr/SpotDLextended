import os
import subprocess
import re
import logging
import json
import unicodedata
import requests
import numpy as np
from rapidfuzz import fuzz
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, error as ID3Error

logger = logging.getLogger(__name__)

# Maximum candidates to attempt downloading per track (keeps things moving)
MAX_DOWNLOAD_ATTEMPTS = 6

# Loose duration tolerance (seconds) for initial pre-filtering
DURATION_TOLERANCE_SECS = 60


class Downloader:
    def __init__(self, api_endpoints=None, search_blacklist=None, spotify_client=None):
        self.search_blacklist = search_blacklist or ["radio edit", "radio mix", "radio version"]
        self.spotify_client = spotify_client
        self.sockseek_path = self.get_sockseek_path()

    # ─────────────────────────────────────────────
    # Static helpers
    # ─────────────────────────────────────────────

    @staticmethod
    def get_sockseek_path():
        local_path = os.path.expanduser("~/.local/bin/sockseek")
        if os.path.exists(local_path):
            return local_path
        return "sockseek"

    @staticmethod
    def sanitize_filename(name):
        """Removes filesystem-unsafe characters."""
        clean = re.sub(r'[\\/*?:"<>|]', "", name)
        return clean.strip()

    @staticmethod
    def normalize_string(s):
        """ASCII-folds, lowercases and collapses whitespace for fuzzy comparison."""
        if not s:
            return ""
        s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
        s = re.sub(r'[(){}\[\]!?,;:\-]', " ", s)
        return " ".join(s.lower().split())

    @staticmethod
    def get_primary_artist(artist_str):
        """Returns the first credited artist, stripping feat./ft./& etc."""
        if not artist_str:
            return ""
        parts = re.split(r',|&|\bfeat\.?\b|\bft\.?\b|\band\b|\bx\b|\bfeaturing\b',
                         artist_str, flags=re.IGNORECASE)
        return Downloader.normalize_string(parts[0])

    # ─────────────────────────────────────────────
    # Stage 1: Loose pre-filter from sockseek results
    # ─────────────────────────────────────────────

    def prefilter_candidates(self, results, spotify_duration_secs, get_extended,
                              has_inherent_mix):
        """
        Quickly filters the raw sockseek result list to plausible candidates using
        only the data available without downloading:
          - File extension must be a supported audio format
          - Duration pre-filter:
              Extended mode: accept anything >= (spotify_secs - 30) with NO upper cap.
                             Extended candidates are anything >= (spotify_secs + 30).
                             Standard fallback candidates are within ±30s of Spotify.
              Standard mode: must be within ±60s of Spotify duration.

        Returns two ranked lists: (extended_candidates, standard_candidates).
        Extended candidates are sorted longest-first (longer = better DJ mix).
        """
        AUDIO_EXTS = {".mp3", ".flac", ".wav", ".aiff", ".aif", ".m4a"}
        extended_kw = ["extended", "original mix", "club mix", "12\"", "12inch", "maxi",
                       "extended mix", "dj mix", "lp version"]

        extended = []
        standard = []

        for item in results:
            username = item.get("User", {}).get("Username")
            upload_speed = item.get("User", {}).get("UploadSpeed", 0)
            has_free_slot = item.get("User", {}).get("HasFreeUploadSlot", False)

            for f in item.get("Files", []):
                filename = f.get("Filename", "")
                length = f.get("Length", 0)     # seconds
                size = f.get("Size", 0)
                bitrate = f.get("Bitrate", 0)
                sample_rate = f.get("SampleRate", 0)
                bit_depth = f.get("BitDepth", 0)

                ext = os.path.splitext(filename)[1].lower()
                if ext not in AUDIO_EXTS:
                    continue

                # Skip suspiciously tiny files (< 1 MB — almost certainly previews)
                if size > 0 and size < 1_000_000:
                    continue

                diff = length - spotify_duration_secs

                # Duration pre-filter
                if length > 0 and spotify_duration_secs > 0:
                    if get_extended and not has_inherent_mix:
                        # Extended mode:
                        # - Accept anything NOT shorter than Spotify by more than 30s
                        # - No upper cap: a mix can be many minutes longer
                        if diff < -30:
                            continue
                    else:
                        # Standard mode: must be within ±60s
                        if abs(diff) > DURATION_TOLERANCE_SECS:
                            continue

                candidate = {
                    'username': username,
                    'filename': filename,
                    'length': length,
                    'size': size,
                    'bitrate': bitrate,
                    'sample_rate': sample_rate,
                    'bit_depth': bit_depth,
                    'upload_speed': upload_speed,
                    'has_free_slot': has_free_slot,
                    'ext': ext,
                }

                # Classify into extended vs standard fallback
                filename_lower = filename.lower()
                has_extended_kw = any(kw in filename_lower for kw in extended_kw)
                is_extended = (
                    get_extended
                    and not has_inherent_mix
                    and (diff >= 30 or (has_extended_kw and diff > 5))
                )

                if is_extended:
                    extended.append(candidate)
                else:
                    standard.append(candidate)

        # Rank: extended sorted longest-first, standard sorted by quality
        return self._rank_extended(extended), self._rank(standard)

    def _rank_extended(self, candidates):
        """
        Rank extended mix candidates by:
          1. Quality — lossless (FLAC/WAV) > reported 320kbps MP3 > other MP3
          2. Length  — longer is better (extended / original mixes are longer)
          3. Free upload slot, then upload speed
        """
        def sort_key(c):
            is_lossless = 1 if c['ext'] in {'.flac', '.wav', '.aiff', '.aif'} else 0
            is_mp3_320  = 1 if (c['ext'] == '.mp3' and c['bitrate'] >= 320) else 0
            is_mp3_ok   = 1 if (c['ext'] == '.mp3' and 0 < c['bitrate'] < 320) else 0
            free_slot   = 1 if c['has_free_slot'] else 0
            return (is_lossless, is_mp3_320, is_mp3_ok, c['length'], free_slot, c['upload_speed'])
        return sorted(candidates, key=sort_key, reverse=True)

    def _rank(self, candidates):
        """Rank standard fallback candidates: quality > free slot > upload speed."""
        def sort_key(c):
            is_lossless = 1 if c['ext'] in {'.flac', '.wav', '.aiff', '.aif'} else 0
            is_mp3_320  = 1 if (c['ext'] == '.mp3' and c['bitrate'] >= 320) else 0
            is_mp3_ok   = 1 if (c['ext'] == '.mp3' and 0 < c['bitrate'] < 320) else 0
            free_slot   = 1 if c['has_free_slot'] else 0
            return (is_lossless, is_mp3_320, is_mp3_ok, free_slot, c['upload_speed'])
        return sorted(candidates, key=sort_key, reverse=True)

    # ─────────────────────────────────────────────
    # Stage 2: Post-download metadata verification
    # ─────────────────────────────────────────────

    def read_embedded_tags(self, file_path):
        """
        Reads artist and title from embedded tags using mutagen.
        Returns (artist, title) strings or (None, None) if unavailable.
        Supports MP3 (ID3), FLAC, and M4A/AAC.
        """
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".mp3":
                audio = MP3(file_path, ID3=ID3)
                tags = audio.tags
                if tags is None:
                    return None, None
                artist = tags.get("TPE1")
                title = tags.get("TIT2")
                artist = artist.text[0] if artist else None
                title = title.text[0] if title else None
                return artist, title

            elif ext == ".flac":
                audio = FLAC(file_path)
                artist = audio.get("artist", [None])[0]
                title = audio.get("title", [None])[0]
                return artist, title

            elif ext in {".m4a", ".aac", ".mp4"}:
                audio = MP4(file_path)
                artist = audio.tags.get("\xa9ART", [None])[0] if audio.tags else None
                title = audio.tags.get("\xa9nam", [None])[0] if audio.tags else None
                return artist, title

            else:
                return None, None

        except Exception as e:
            logger.debug(f"Could not read embedded tags from {file_path}: {e}")
            return None, None

    def tags_match_spotify(self, file_path, spotify_title, spotify_artist):
        """
        Reads embedded tags from a downloaded file and checks whether they
        plausibly match the Spotify artist and title.

        Strategy:
        - If tags are present: use fuzzy matching (token_set_ratio >= 75).
        - If tags are missing: fall back to filename-based matching (less reliable).

        Returns (match: bool, reason: str).
        """
        tag_artist, tag_title = self.read_embedded_tags(file_path)

        norm_spot_artist = self.get_primary_artist(spotify_artist)
        norm_spot_title = self.normalize_string(spotify_title)

        # Strip mix/remix modifiers for a core title comparison
        mix_pattern = r'(?i)\b(extended|original|club|mix|edit|remix|remixed|vip)\b'
        feat_pattern = r'(?i)\b(?:feat\.?|ft\.?|featuring)\b[^()\-]*'
        core_spot_title = self.normalize_string(
            re.sub(mix_pattern, '', re.sub(feat_pattern, '', spotify_title))
        )

        if tag_artist and tag_title:
            norm_tag_artist = self.normalize_string(self.get_primary_artist(tag_artist))
            core_tag_title = self.normalize_string(
                re.sub(mix_pattern, '', re.sub(feat_pattern, '', tag_title))
            )

            artist_score = fuzz.token_set_ratio(norm_spot_artist, norm_tag_artist)
            title_score = fuzz.token_sort_ratio(core_spot_title, core_tag_title)

            logger.debug(
                f"    Tag check: artist='{tag_artist}' ({artist_score}), "
                f"title='{tag_title}' ({title_score})"
            )

            if artist_score >= 75 and title_score >= 70:
                return True, f"Tag match (artist={artist_score}, title={title_score})"
            else:
                return False, f"Tag mismatch (artist={artist_score}, title={title_score})"

        else:
            # No embedded tags — fall back to filename/path check
            base = os.path.splitext(os.path.basename(file_path))[0]
            # Strip leading track numbers (e.g. '19 - ', '08. ')
            base = re.sub(r'^\d+[\s.\-]+', '', base)
            norm_full_path = self.normalize_string(
                file_path.replace('\\', ' ').replace('/', ' ')
            )

            # Use token_set_ratio for both: handles artist/title as substrings of longer strings
            artist_score = fuzz.token_set_ratio(norm_spot_artist, norm_full_path)
            title_score = fuzz.token_set_ratio(core_spot_title, norm_full_path)

            logger.debug(
                f"    Filename fallback: artist_score={artist_score}, title_score={title_score}"
            )

            if artist_score >= 70 and title_score >= 70:
                return True, f"Filename fallback match (artist={artist_score}, title={title_score})"
            else:
                return False, f"Filename fallback mismatch (artist={artist_score}, title={title_score})"

    # ─────────────────────────────────────────────
    # Stage 3: Spectral MP3 quality verification
    # ─────────────────────────────────────────────

    def verify_mp3_quality(self, file_path):
        """
        Spectral FFT check: returns False if the MP3 is a fake/upscaled 320 kbps.
        True 320 kbps files retain energy above 18.5 kHz.
        """
        try:
            for seek in ("60", "10"):
                cmd = [
                    "ffmpeg", "-ss", seek, "-t", "30",
                    "-i", file_path,
                    "-f", "s16le", "-ac", "1", "-ar", "44100",
                    "-y", "-"
                ]
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout_data, _ = proc.communicate()
                if proc.returncode == 0 and stdout_data:
                    break
            else:
                logger.warning("FFmpeg could not extract samples for quality check.")
                return False

            samples = np.frombuffer(stdout_data, dtype=np.int16)
            if len(samples) == 0:
                return False

            window_size = 2048
            hop_size = 1024
            num_windows = (len(samples) - window_size) // hop_size
            if num_windows <= 0:
                return False

            fft_spectra = [
                np.abs(np.fft.rfft(
                    samples[i * hop_size: i * hop_size + window_size] * np.hanning(window_size)
                ))
                for i in range(num_windows)
            ]

            avg_spectrum = np.mean(fft_spectra, axis=0)
            power_db = 20 * np.log10(avg_spectrum + 1e-8)
            power_db_norm = power_db - np.max(power_db)

            freqs = np.fft.rfftfreq(window_size, d=1 / 44100)
            idx = lambda hz: int(np.searchsorted(freqs, hz))

            max_10_15 = np.max(power_db_norm[idx(10000):idx(15000)])
            max_18_20 = np.max(power_db_norm[idx(18500):idx(20000)])

            # If music energy exists in 10–15 kHz but is gone by 18.5 kHz → fake 320k
            if max_10_15 >= -50.0 and max_18_20 < -50.0:
                logger.warning(
                    f"    Spectral cutoff detected: 10–15k={max_10_15:.1f}dB, "
                    f"18.5–20k={max_18_20:.1f}dB → fake 320 kbps"
                )
                return False

            logger.info(
                f"    Spectral OK: 10–15k={max_10_15:.1f}dB, 18.5–20k={max_18_20:.1f}dB"
            )
            return True

        except Exception as e:
            logger.warning(f"Error during MP3 quality verification: {e}")
            return False

    # ─────────────────────────────────────────────
    # Stage 4: ID3 tagging
    # ─────────────────────────────────────────────

    def tag_mp3(self, file_path, spotify_title, spotify_artist, spotify_uri, chosen_filename):
        """Strips all existing tags and writes clean Spotify-sourced metadata."""
        try:
            # Load existing tags (written by ffmpeg during transcode) or create fresh
            try:
                tags = ID3(file_path)
                tags.delete()  # Wipe all existing frames cleanly
            except ID3Error:
                tags = ID3()

            # Reflect the mix type found in the chosen filename
            title = spotify_title
            chosen_lower = chosen_filename.lower()
            if "extended" in chosen_lower and "extended" not in title.lower():
                title = f"{title} (Extended Mix)"
            elif "club" in chosen_lower and "club" not in title.lower():
                title = f"{title} (Club Mix)"
            elif "original mix" in chosen_lower and "original" not in title.lower():
                title = f"{title} (Original Mix)"

            tags.add(TIT2(encoding=3, text=title))
            tags.add(TPE1(encoding=3, text=spotify_artist))
            tags.add(TALB(encoding=3, text=f"{spotify_title} Single"))

            # Cover art from Spotify embed API
            cover_data = None
            if spotify_uri and self.spotify_client:
                try:
                    track_id = spotify_uri.split(":")[-1]
                    track_url = f"https://open.spotify.com/track/{track_id}"
                    track_info = self.spotify_client.get_track_info(track_url)
                    images = track_info.get("album", {}).get("images", [])
                    if images:
                        cover_url = sorted(images, key=lambda x: x.get("width", 0), reverse=True)[0].get("url")
                        if cover_url:
                            resp = requests.get(cover_url, timeout=10)
                            if resp.status_code == 200:
                                cover_data = resp.content
                except Exception as e:
                    logger.debug(f"Cover art fetch failed: {e}")

            if cover_data:
                tags.add(APIC(
                    encoding=3, mime='image/jpeg',
                    type=3, desc='Front Cover', data=cover_data
                ))

            tags.save(file_path, v2_version=3)
            logger.info(f"  [🔗] Tagged: {file_path}")

        except Exception as e:
            logger.error(f"  [❌] Tagging error for {file_path}: {e}")

    # ─────────────────────────────────────────────
    # Main entry point
    # ─────────────────────────────────────────────

    def download_track(self, track_data, folder, overwrite=False,
                       playlist_only=False, get_extended=True):
        """
        Full pipeline:
          1. Scrape Soulseek via sockseek CLI
          2. Loose pre-filter by duration + extension
          3. Rank (lossless > 320 MP3, free slot, speed)
          4. For each candidate: download → read tags → verify match
          5. If MP3: spectral quality check; if lossless: transcode to 320 MP3
          6. Tag and move to final location
        """
        spotify_title = track_data['title']
        spotify_artist = track_data['artist']
        spotify_duration_ms = track_data.get('duration_ms', 0)
        spotify_uri = track_data.get('uri')
        spotify_secs = spotify_duration_ms / 1000.0

        safe_base = self.sanitize_filename(f"{spotify_title} - {spotify_artist}")
        mp3_path = os.path.join(folder, f"{safe_base}.mp3")
        flac_path = os.path.join(folder, f"{safe_base}.flac")

        # ── Intelligent skip ──────────────────────────────────────────────
        if not overwrite:
            if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0:
                logger.info(f"  [-] Already exists (MP3): {safe_base}.mp3")
                return f"{safe_base}.mp3", "Skipped"
            if os.path.exists(flac_path) and os.path.getsize(flac_path) > 0:
                logger.info(f"  [-] Already exists (FLAC): {safe_base}.flac")
                return f"{safe_base}.flac", "Skipped"

        logger.info(f"\n🎵 {spotify_title} — {spotify_artist}")

        # ── Build search query ────────────────────────────────────────────
        search_query = f"{spotify_artist} {spotify_title}".replace("-", " ")
        for word in self.search_blacklist:
            search_query = re.sub(rf'\b{re.escape(word)}\b', '', search_query, flags=re.IGNORECASE)
        search_query = " ".join(search_query.split())

        logger.info(f"  [🔍] Query: '{search_query}'")

        # ── Sockseek search ───────────────────────────────────────────────
        try:
            proc = subprocess.Popen(
                [self.sockseek_path, search_query, "--print", "json-all"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            stdout, stderr = proc.communicate()
            if proc.returncode != 0:
                raise ValueError(f"sockseek error: {stderr.strip()}")
            results = json.loads(stdout.strip())
        except Exception as e:
            logger.error(f"  [❌] Search failed: {e}")
            return None, "Error"

        # ── Detect if track is already a mix ─────────────────────────────
        has_inherent_mix = bool(re.search(
            r'\b(extended|club mix|remix|remixed|vip)\b',
            spotify_title, flags=re.IGNORECASE
        ))

        extended_ranked, standard_ranked = self.prefilter_candidates(
            results, spotify_secs, get_extended, has_inherent_mix
        )

        if not extended_ranked and not standard_ranked:
            logger.warning(f"  [!] No candidates after pre-filter for: {spotify_title}")
            self._write_nfo(folder, safe_base, spotify_title, spotify_artist,
                            "No candidates passed duration/extension pre-filter.")
            return f"{safe_base} - NOT FOUND.nfo", "Error"

        # ── Try extended mixes first, then standard ───────────────────────
        if extended_ranked:
            logger.info(f"  [⭐] {len(extended_ranked)} extended mix candidate(s) found — trying first.")

        attempts = (
            [(c, "Extended Mix") for c in extended_ranked] +
            [(c, "Direct Match") for c in standard_ranked]
        )[:MAX_DOWNLOAD_ATTEMPTS]

        temp_dir = os.path.join(folder, ".tmp_download")
        downloaded_filepath = None
        success_candidate = None
        success_mix_type = None

        for c, mix_type in attempts:
            logger.info(
                f"  [⬇] {c['username']} → {os.path.basename(c['filename'])} "
                f"({c['length']}s, {c['bitrate'] or '?'}kbps, {c['ext']})"
            )

            # Clean temp dir
            if os.path.exists(temp_dir):
                subprocess.run(["rm", "-rf", temp_dir], check=False)
            os.makedirs(temp_dir, exist_ok=True)

            slsk_uri = f"slsk://{c['username']}/{c['filename']}"
            try:
                subprocess.run(
                    [self.sockseek_path, slsk_uri, "-o", temp_dir],
                    check=True, timeout=300
                )
            except Exception as e:
                logger.warning(f"  [⚠] Download failed: {e}")
                continue

            dl_files = [
                f for f in os.listdir(temp_dir)
                if os.path.isfile(os.path.join(temp_dir, f))
            ]
            if not dl_files:
                logger.warning("  [⚠] No file in temp dir after download.")
                continue

            dl_file = os.path.join(temp_dir, dl_files[0])
            ext = os.path.splitext(dl_file)[1].lower()

            # ── Metadata verification (primary check) ─────────────────────
            match_ok, match_reason = self.tags_match_spotify(dl_file, spotify_title, spotify_artist)
            if not match_ok:
                logger.warning(f"  [✗] Metadata mismatch — {match_reason}. Skipping.")
                continue
            logger.info(f"  [✓] Metadata verified — {match_reason}")

            # ── Quality check / transcode ──────────────────────────────────
            if ext == ".mp3":
                logger.info("  [🔬] Checking MP3 spectral quality...")
                if not self.verify_mp3_quality(dl_file):
                    logger.warning("  [⚠] Fake 320 kbps detected. Skipping.")
                    os.remove(dl_file)
                    continue
                logger.info("  [✓] True 320 kbps confirmed.")
                subprocess.run(["mv", dl_file, mp3_path], check=True)
                downloaded_filepath = mp3_path

            else:
                logger.info(f"  [🔄] Transcoding {ext.upper()} → 320 kbps MP3...")
                try:
                    subprocess.run(
                        ["ffmpeg", "-i", dl_file,
                         "-vn",           # strip embedded cover art / video streams
                         "-ab", "320k",
                         "-map_metadata", "-1",
                         "-y", mp3_path],
                        check=True
                    )
                    downloaded_filepath = mp3_path
                except Exception as e:
                    logger.error(f"  [❌] Transcode failed: {e}")
                    continue

            success_candidate = c
            success_mix_type = mix_type
            break

        # ── Cleanup ───────────────────────────────────────────────────────
        if os.path.exists(temp_dir):
            subprocess.run(["rm", "-rf", temp_dir], check=False)

        if not downloaded_filepath:
            logger.warning(f"  [!] All candidates failed for: {spotify_title}")
            self._write_nfo(folder, safe_base, spotify_title, spotify_artist,
                            "All download candidates failed metadata/quality checks.")
            return f"{safe_base} - DOWNLOAD FAILED.nfo", "Error"

        # ── Tag ────────────────────────────────────────────────────────────
        self.tag_mp3(
            downloaded_filepath, spotify_title, spotify_artist,
            spotify_uri, os.path.basename(success_candidate['filename'])
        )

        return f"{safe_base}.mp3", success_mix_type

    # ─────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────

    @staticmethod
    def _write_nfo(folder, safe_base, title, artist, error_msg):
        path = os.path.join(folder, f"{safe_base} - NOT FOUND.nfo")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"Track: {title}\nArtist: {artist}\nError: {error_msg}\n")
        except Exception:
            pass
