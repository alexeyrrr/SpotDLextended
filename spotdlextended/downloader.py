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

    def heuristic_filter_and_score(self, results, spotify_title, spotify_artist, spotify_duration_secs, get_extended):
        """
        In-Memory Pre-Download Heuristic Engine
        Filters and scores results based on duration, keywords, formatting, and matches.
        """
        AUDIO_EXTS = {".mp3", ".flac", ".wav", ".aiff", ".aif", ".m4a"}
        extended_kw = ["extended", "original mix", "club mix", "12\"", "12inch", "maxi",
                       "extended mix", "dj mix", "lp version", "vip"]
        
        is_remix_target = bool(re.search(r'\bremix\b', spotify_title, flags=re.IGNORECASE))
        core_spot_title = self.normalize_string(
            re.sub(r'(?i)\b(extended|original|club|mix|edit|remix|remixed|vip)\b', '', 
            re.sub(r'(?i)\b(?:feat\.?|ft\.?|featuring)\b[^()\-]*', '', spotify_title))
        )
        norm_spot_artist = self.get_primary_artist(spotify_artist)
        
        candidates = []

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

                if size > 0 and size < 1_000_000:
                    continue
                    
                # Hard Quality Filter
                if ext == ".mp3" and bitrate < 320 and bitrate > 0:
                    continue

                # Hard Remix Filter
                has_remix_in_file = bool(re.search(r'\bremix\b', filename, flags=re.IGNORECASE))
                if not is_remix_target and has_remix_in_file:
                    continue
                if is_remix_target and not has_remix_in_file:
                    continue
                
                score = 0
                
                # Fuzzy match title and artist (Bonus)
                base = os.path.splitext(os.path.basename(filename))[0]
                norm_full_path = self.normalize_string(base.replace('-', ' '))
                artist_score = fuzz.token_set_ratio(norm_spot_artist, norm_full_path)
                title_score = fuzz.token_set_ratio(core_spot_title, norm_full_path)
                
                if artist_score > 80 and title_score > 80:
                    score += 100
                elif artist_score > 70 and title_score > 70:
                    score += 50
                    
                diff = length - spotify_duration_secs
                
                # Extended mix keywords check
                filename_lower = filename.lower()
                has_extended_kw = any(kw in filename_lower for kw in extended_kw)
                
                # Penalize "Clean" versions
                if re.search(r'\([^)]*\bclean\b[^)]*\)|\[[^\]]*\bclean\b[^\]]*\]', filename_lower):
                    score -= 500
                elif re.search(r'\bclean\b', filename_lower):
                    score -= 100
                
                mix_type = "Standard"
                if get_extended:
                    if diff >= 30:
                        score += 1000
                        mix_type = "Extended Mix"
                    
                    if has_extended_kw:
                        score += 500
                
                if abs(diff) <= 5:
                    score += 50

                # Format & Bitrate
                if ext == ".mp3" and bitrate >= 320:
                    score += 20
                elif ext in {".flac", ".wav", ".aiff", ".aif"}:
                    score += 10
                    
                if has_free_slot:
                    score += 5
                
                candidates.append({
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
                    'score': score,
                    'mix_type': mix_type
                })
                
        def sort_key(c):
            return (c['score'], c['upload_speed'])
        
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

    def read_embedded_isrc(self, file_path):
        """Attempts to extract ISRC tag from file."""
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".mp3":
                audio = MP3(file_path, ID3=ID3)
                if audio.tags:
                    isrc_tag = audio.tags.get("TSRC")
                    if isrc_tag:
                        return isrc_tag.text[0]
            elif ext == ".flac":
                audio = FLAC(file_path)
                return audio.get("isrc", [None])[0]
        except Exception:
            pass
        return None

    @staticmethod
    def is_already_extended_mix(file_path):
        """
        Returns True if the file already appears to be an extended, original, club, or remix version.
        Checks both the filename and the embedded title tag so that re-tagged files are also caught.
        """
        extended_kw = ["extended", "original", "club mix", "remix"]

        filename_lower = os.path.basename(file_path).lower()
        if any(kw in filename_lower for kw in extended_kw):
            return True

        # Also check embedded title tag
        ext = os.path.splitext(file_path)[1].lower()
        try:
            title = None
            if ext == ".mp3":
                audio = MP3(file_path, ID3=ID3)
                if audio.tags:
                    tit2 = audio.tags.get("TIT2")
                    title = tit2.text[0] if tit2 else None
            elif ext == ".flac":
                audio = FLAC(file_path)
                title = audio.get("title", [None])[0]
            if title and any(kw in title.lower() for kw in extended_kw):
                return True
        except Exception:
            pass

        return False

    def find_existing_track_in_library(self, track_data, library_dir):
        """
        Scans library_dir for matching tracks.
        Checks filename for primary artist and fuzzy match of title, then verifies via tags.
        """
        if not library_dir or not os.path.isdir(library_dir):
            return None
            
        spotify_title = track_data['title']
        spotify_artist = track_data['artist']
        target_isrc = track_data.get('isrc')
        
        norm_spot_artist = self.get_primary_artist(spotify_artist)
        core_spot_title = self.normalize_string(
            re.sub(r'(?i)\b(extended|original|club|mix|edit|remix|remixed|vip)\b', '', 
            re.sub(r'(?i)\b(?:feat\.?|ft\.?|featuring)\b[^()\-]*', '', spotify_title))
        )
        
        valid_exts = {'.mp3', '.flac'}
        
        for root_dir, dirs, files in os.walk(library_dir):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext not in valid_exts:
                    continue
                    
                abs_path = os.path.join(root_dir, f)
                
                # Quick check: filename primary artist match
                base = os.path.splitext(f)[0]
                norm_full_path = self.normalize_string(base.replace('-', ' '))
                artist_score = fuzz.token_set_ratio(norm_spot_artist, norm_full_path)
                if artist_score < 70:
                    continue
                    
                # Quick check: filename title match
                title_score = fuzz.token_set_ratio(core_spot_title, norm_full_path)
                if title_score < 70:
                    continue
                    
                # If ISRC is provided, check it
                if target_isrc:
                    file_isrc = self.read_embedded_isrc(abs_path)
                    if file_isrc and file_isrc.replace('-', '').upper() == target_isrc.replace('-', '').upper():
                        logger.info(f"  [✓] Found existing track in library by ISRC: {abs_path}")
                        return abs_path
                        
                # Fallback to tag checking
                match_ok, match_reason = self.tags_match_spotify(abs_path, spotify_title, spotify_artist)
                if match_ok:
                    logger.info(f"  [✓] Found existing track in library by tags: {abs_path} - {match_reason}")
                    return abs_path
                    
        return None

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
                       playlist_only=False, get_extended=True, library_dir=None,
                       upgrade_extended=False):
        """
        Full pipeline:
          1. Check library dir for existing matching tracks via fuzzy match & tags.
          2. Scrape Soulseek via sockseek CLI (using a cascade of extended/mix queries).
          3. Loose pre-filter by duration + extension (remix filtering included).
          4. Rank (lossless > 320 MP3, free slot, speed)
          5. For each candidate: download → read tags → verify match
          6. If MP3: spectral quality check; if lossless: transcode to 320 MP3
          7. Tag and move to final location

        When upgrade_extended=True the behaviour is similar to overwrite but *only* downloads
        if an extended/club/original mix is found. Files whose filename or title tag already
        contain an extended-mix keyword are skipped. The old standard-mix file is removed
        only after a confirmed successful replacement download.
        """
        spotify_title = track_data['title']
        spotify_artist = track_data['artist']
        spotify_duration_ms = track_data.get('duration_ms', 0)
        spotify_uri = track_data.get('uri')
        spotify_secs = spotify_duration_ms / 1000.0

        safe_base = self.sanitize_filename(f"{spotify_title} - {spotify_artist}")
        mp3_path = os.path.join(folder, f"{safe_base}.mp3")
        flac_path = os.path.join(folder, f"{safe_base}.flac")

        # Track the pre-existing file in the playlist folder so we can delete it on success
        existing_in_playlist = None

        # ── Upgrade-extended mode ─────────────────────────────────────────
        if upgrade_extended:
            for ext_check in [".mp3", ".flac"]:
                candidate_path = os.path.join(folder, f"{safe_base}{ext_check}")
                if os.path.exists(candidate_path) and os.path.getsize(candidate_path) > 0:
                    existing_in_playlist = candidate_path
                    break

            if existing_in_playlist and self.is_already_extended_mix(existing_in_playlist):
                logger.info(
                    f"  [-] Already an extended/mix version, skipping upgrade: "
                    f"{os.path.basename(existing_in_playlist)}"
                )
                return os.path.basename(existing_in_playlist), "Skipped"

            # Force extended searching regardless of the caller's get_extended value
            get_extended = True
            logger.info(
                f"  [🔍] Upgrade mode: searching for extended mix "
                f"(existing: {os.path.basename(existing_in_playlist) if existing_in_playlist else 'none'})"
            )

        # ── Standard intelligent skip (unchanged when not upgrading) ──────
        elif not overwrite:
            if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0:
                logger.info(f"  [-] Already exists in playlist (MP3): {safe_base}.mp3")
                return f"{safe_base}.mp3", "Skipped"
            if os.path.exists(flac_path) and os.path.getsize(flac_path) > 0:
                logger.info(f"  [-] Already exists in playlist (FLAC): {safe_base}.flac")
                return f"{safe_base}.flac", "Skipped"

        logger.info(f"\n🎵 {spotify_title} — {spotify_artist}")
        
        # ── Global Library Search (skipped in upgrade mode — always download fresh) ──
        if library_dir and not overwrite and not upgrade_extended:
            existing_track = self.find_existing_track_in_library(track_data, library_dir)
            if existing_track:
                # Return the absolute path so playlist generator can link it directly
                return existing_track, "Library Match"

        # ── Detect if track is already a mix ─────────────────────────────
        has_inherent_mix = bool(re.search(
            r'\b(extended|club mix|remix|remixed|vip)\b',
            spotify_title, flags=re.IGNORECASE
        ))

        # ── Build single broad search query ──────────────────────────────
        # Strip parentheticals (...) and [...] from both artist and title before
        # searching, EXCEPT for remix-containing groups — Soulseek filenames
        # rarely include "feat.", remaster years, or radio-edit qualifiers, but
        # they DO carry remix credits which are needed to find the right version.
        primary_artist = self.get_primary_artist(spotify_artist)
        clean_title = re.sub(
            r'\s*[\(\[][^\)\]]*[\)\]]',
            lambda m: m.group(0) if re.search(r'\bremix\b', m.group(0), re.IGNORECASE) else '',
            spotify_title
        ).strip()
        clean_artist = re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', '', primary_artist).strip()
        logger.info(f"  [🔍] Clean search terms — artist: '{clean_artist}', title: '{clean_title}'")
        raw_query = f"{clean_artist} {clean_title}".replace("-", " ")
        search_query = raw_query
        for word in self.search_blacklist:
            search_query = re.sub(rf'\b{re.escape(word)}\b', '', search_query, flags=re.IGNORECASE)
        search_query = " ".join(search_query.split())

        temp_dir = os.path.join(folder, ".tmp_download")
        downloaded_filepath = None
        success_candidate = None
        success_mix_type = None

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
            results = []

        ranked_candidates = self.heuristic_filter_and_score(
            results, spotify_title, spotify_artist, spotify_secs, get_extended and not has_inherent_mix
        )

        if not ranked_candidates:
            logger.debug(f"  [!] No candidates passed heuristic filter for query: '{search_query}'")

        attempts = [(c, c['mix_type']) for c in ranked_candidates][:MAX_DOWNLOAD_ATTEMPTS]
        
        for c, mix_type in attempts:
            logger.info(
                f"  [⬇] {c['username']} → {os.path.basename(c['filename'])} "
                f"(Score: {c['score']}, {c['length']}s, {c['bitrate'] or '?'}kbps, {c['ext']})"
            )

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
            logger.warning(f"  [!] All queries and candidates failed for: {spotify_title}")
            if upgrade_extended and existing_in_playlist:
                logger.info(f"  [-] No extended mix found — keeping existing file unchanged.")
                return os.path.basename(existing_in_playlist), "Skipped"
            self._write_nfo(folder, safe_base, spotify_title, spotify_artist,
                            "All download candidates failed metadata/quality checks.")
            return f"{safe_base} - DOWNLOAD FAILED.nfo", "Error"

        # ── Remove old standard-mix file after confirmed successful upgrade ─
        if upgrade_extended and existing_in_playlist and existing_in_playlist != downloaded_filepath:
            try:
                os.remove(existing_in_playlist)
                logger.info(f"  [🗑] Removed standard mix: {existing_in_playlist}")
            except Exception as e:
                logger.warning(f"  [⚠] Could not remove old file: {e}")

        # ── Tag ────────────────────────────────────────────────────────────
        self.tag_mp3(
            downloaded_filepath, spotify_title, spotify_artist,
            spotify_uri, os.path.basename(success_candidate['filename'])
        )

        # Mark as Upgraded when a pre-existing standard mix was replaced
        final_mix_type = success_mix_type
        if upgrade_extended and existing_in_playlist:
            final_mix_type = "Upgraded"

        return f"{safe_base}.mp3", final_mix_type

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
