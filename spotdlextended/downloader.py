import os
import requests
import re
import logging
import base64
import json
import time
import unicodedata
from rapidfuzz import fuzz
from mutagen.flac import FLAC, Picture

class Downloader:
    def __init__(self, api_endpoints, search_blacklist=None):
        self.api_endpoints = api_endpoints
        self.current_endpoint_idx = 0
        self.search_blacklist = search_blacklist or ["radio edit", "radio mix", "radio version"]

    def make_api_request(self, endpoint, params=None, timeout=30):
        attempts = 0
        max_attempts = len(self.api_endpoints)

        while attempts < max_attempts:
            base_url = self.api_endpoints[self.current_endpoint_idx]
            url = f"{base_url}{endpoint}"
            try:
                response = requests.get(url, params=params, timeout=timeout)
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    logging.warning(f"  [⚠️] 429 Rate Limit from {base_url}. Switching endpoint...")
                else:
                    logging.warning(f"  [⚠️] HTTP {e.response.status_code} Error from {base_url}. Switching endpoint...")
            except requests.exceptions.RequestException as e:
                logging.warning(f"  [⚠️] Request error from {base_url}: {e}. Switching endpoint...")
            
            # Advance to the next endpoint if it failed
            self.current_endpoint_idx = (self.current_endpoint_idx + 1) % len(self.api_endpoints)
            attempts += 1
            
        raise Exception("All alternate API endpoints failed or rate limited.")

    @staticmethod
    def sanitize_filename(name):
        """Removes invalid characters and trims for file saving."""
        clean = re.sub(r'[\\/*?:"<>|]', "", name)
        return clean.strip()

    @staticmethod
    def normalize_string(s):
        """Removes punctuation, special characters, and diacritics, and converts to lowercase."""
        if not s:
            return ""
        # Strip diacritics (e.g., é -> e, ä -> a)
        s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
        # Only strip major punctuation/separators (including dashes), preserve periods
        s = re.sub(r'[(){}\[\]!?,;:\-]', " ", s)
        # The split() and join() automatically removes all double/multiple spaces
        return " ".join(s.lower().split())

    @staticmethod
    def get_primary_artist(artist_str):
        """Extracts the first artist from a string (handles , & feat. ft. and x)."""
        if not artist_str:
            return ""
        # Split by common delimiters
        delimiters = r',|&|\bfeat\b|\bft\b|\band\b|\bx\b|\bfeaturing\b'
        parts = re.split(delimiters, artist_str, flags=re.IGNORECASE)
        return Downloader.normalize_string(parts[0])

    @staticmethod
    def calculate_match_score(spotify_title, spotify_artist, spotify_duration, candidate, current_modifier):
        """
        Calculates a confidence score (0-200+) based on fuzzy matching and context.
        Returns 0 if it fails strict minimum thresholds.
        """
        cand_title = candidate.get("title", "")
        cand_version = candidate.get("version")
        if cand_version and cand_version.lower() not in cand_title.lower():
            cand_title = f"{cand_title} ({cand_version})"
        cand_artist_raw = candidate.get("artist", {}).get("name", "")
        cand_artist = Downloader.get_primary_artist(cand_artist_raw)
        
        cand_duration_str = candidate.get("duration", "0")
        try:
            cand_duration = int(cand_duration_str)
        except ValueError:
            cand_duration = 0

        # 1. Artist Score (Ensure both are normalized and compared as primary tokens)
        norm_spotify_artist = Downloader.normalize_string(spotify_artist)
        set_score = fuzz.token_set_ratio(norm_spotify_artist, cand_artist)
        sort_score = fuzz.token_sort_ratio(norm_spotify_artist, cand_artist)
        artist_score = int((set_score * 0.4) + (sort_score * 0.6))
        
        if artist_score < 80:  # Lowered from 85 slightly to account for the stricter hybrid score
            return 0  # Fail threshold
            
        # 2. Base Title Score (Core Equivalence)
        # Remove "feat." and artists from the title to prevent match dilution
        feat_pattern = r'(?i)\b(?:feat\.?|ft\.?|featuring)\b[^()\-]*'
        cand_title_no_feat = re.sub(feat_pattern, '', cand_title)
        spotify_title_no_feat = re.sub(feat_pattern, '', spotify_title)

        # Expand to include remix and vip to focus on the core song name similarity
        modifier_pattern = r'(?i)\b(extended|original|club|mix|edit|radio|remix|remixed|mixed|v\.?i\.?p)\b'
        clean_cand_title = Downloader.normalize_string(re.sub(modifier_pattern, '', cand_title_no_feat))
        clean_spotify_title = Downloader.normalize_string(re.sub(modifier_pattern, '', spotify_title_no_feat))
        
        # Token sort ratio ensures the cores match accurately without getting tricked by subsets
        title_score = fuzz.token_sort_ratio(clean_spotify_title, clean_cand_title)
        if title_score < 80:
            return 0  # Fail threshold if core names don't match well

        total_score = artist_score + title_score
        
        cand_title_lower = cand_title.lower()
        spotify_title_lower = spotify_title.lower()

        # 3. Modifier Context Checks & Penalties
        # Penalize unwanted remixes and mixed versions (Protect Against False Positives)
        anti_mix_words = ["remix", "rework", "mixed", "remixed", "vip", "flip", "bootleg", "edit"]
        if not any(w in spotify_title_lower for w in anti_mix_words):
            if any(w in cand_title_lower for w in anti_mix_words):
                total_score -= 100  # Severe penalty immediately disqualifies most tracks

        # 4. Duration Logic (Length over Label)
        if cand_duration and spotify_duration:
            spotify_sec = spotify_duration / 1000.0
            diff = cand_duration - spotify_sec
            
            # If the candidate track is significantly longer (>30s)
            if diff >= 30:
                # Reward: Appended modifier OR original is Radio Edit OR cores match perfectly (>=95)
                if current_modifier != "" or "radio" in spotify_title_lower or title_score >= 95:
                    total_score += 60  # Massive bonus for finding the longer/extended version
                else:
                    total_score -= 80  # Penalty: Longer but we lack confidence
            # If lengths are essentially identical (within 3 seconds)
            elif abs(diff) <= 3:
                if current_modifier == "":
                    total_score += 80  # Direct exact search rewarded for exact duration
                else:
                    total_score -= 80  # Penalty: Sought an Extended mix, but got short track
            # If no modifier used, and duration is neither matching nor longer
            elif current_modifier == "":
                total_score -= 100

        return total_score

    @staticmethod
    def tag_track(file_path, data):
        """
        Applies comprehensive metadata to a FLAC file using the data from Monochrome API.
        Handles Title, Artist, Album, BPM, Key, Track #, and High-Res Cover Art.
        """
        try:
            audio = FLAC(file_path)
            
            # 1. Basic Metadata (Vorbis Comments)
            title = data.get("title", "")
            version = data.get("version")
            if version and version.lower() not in title.lower():
                title = f"{title} ({version})"
            audio["TITLE"] = [title]
            audio["ARTIST"] = [data.get("artist", {}).get("name", "")]
            audio["ALBUM"] = [data.get("album", {}).get("title", "")]
            
            # 2. Track Number
            track_num = data.get("trackNumber")
            if track_num:
                audio["TRACKNUMBER"] = [str(track_num)]
                
            # 3. Tempo (BPM)
            bpm = data.get("bpm")
            if bpm:
                audio["BPM"] = [str(int(bpm))]
                
            # 4. Musical Key
            key = data.get("key")
            key_scale_raw = data.get("keyScale") or ""
            scale = key_scale_raw.capitalize()
            
            if key:
                key_clean = key.replace("Sharp", "#")
                key_string = f"{key_clean} {scale}".strip()
                audio["INITIALKEY"] = [key_string]
                
            # 5. High-Resolution Cover Art
            cover_uuid = data.get("album", {}).get("cover")
            if cover_uuid:
                path_uuid = cover_uuid.replace("-", "/")
                cover_url = f"https://resources.tidal.com/images/{path_uuid}/1280x1280.jpg"
                try:
                    img_response = requests.get(cover_url, timeout=10)
                    if img_response.status_code == 200:
                        picture = Picture()
                        picture.data = img_response.content
                        picture.type = 3  # Front Cover
                        picture.mime = "image/jpeg"
                        picture.desc = "Front Cover"
                        audio.add_picture(picture)
                        logging.info("  [🔗] Cover art attached to FLAC (1280x1280)")
                except Exception as e:
                    logging.warning(f"  [⚠️] Could not download cover art: {e}")

            audio.save()
            logging.info(f"  [🔗] Successfully tagged metadata for: {file_path}")
        except Exception as e:
            logging.error(f"  [❌] Error tagging file {file_path}: {e}")

    def download_track(self, track_data, folder, overwrite, playlist_only=False, get_extended=True):
        """
        track_data: Dictionary {'title': str, 'artist': str, 'duration_ms': int}
        Searches for track on Monochrome using multi-attempt fuzzy matching,
        downloads LIMITLESS FLAC, and tags the result.
        """
        spotify_title = track_data['title']
        spotify_artist = track_data['artist']
        spotify_duration = track_data.get('duration_ms', 0)
        
        safe_base_name = self.sanitize_filename(f"{spotify_title} - {spotify_artist}")
        
        # 1. Exact Name Check (Spotify Format)
        final_flac_filename = f"{safe_base_name}.flac"
        flac_path = os.path.join(folder, final_flac_filename)
        
        if not overwrite:
            if os.path.exists(flac_path) and os.path.getsize(flac_path) > 0:
                logging.info(f"  [-] File already exists, skipping: {final_flac_filename}")
                return final_flac_filename, "Skipped"
                
            # 2. Local Monochrome Name Check (Fuzzy)
            spotify_primary = self.get_primary_artist(spotify_artist)
            feat_pattern = r'(?i)\b(?:feat\.?|ft\.?|featuring)\b[^()\-]*'
            spotify_title_no_feat = re.sub(feat_pattern, '', spotify_title)
            modifier_pattern = r'(?i)\b(extended|original|club|mix|edit|radio|radio mix|remix|remixed|mixed|v\.?i\.?p)\b'
            clean_spot_title = self.normalize_string(re.sub(modifier_pattern, '', spotify_title_no_feat))
            clean_spot_artist = self.normalize_string(spotify_primary)
            
            for f in os.listdir(folder):
                if f.endswith(".flac") and os.path.getsize(os.path.join(folder, f)) > 0:
                    name_no_ext = f[:-5]
                    # Safely split by dash from the right to separate Title from Artist
                    if " - " in name_no_ext:
                        cand_title, cand_artist = name_no_ext.rsplit(" - ", 1)
                    else:
                        cand_title, cand_artist = name_no_ext, ""
                        
                    cand_title_no_feat = re.sub(feat_pattern, '', cand_title)
                    clean_cand_title = self.normalize_string(re.sub(modifier_pattern, '', cand_title_no_feat))
                    clean_cand_artist = self.normalize_string(self.get_primary_artist(cand_artist))
                    
                    # Check for tight equivalence mapping
                    t_score = fuzz.token_sort_ratio(clean_spot_title, clean_cand_title)
                    a_score = fuzz.token_sort_ratio(clean_spot_artist, clean_cand_artist)
                    
                    if t_score >= 85 and a_score >= 85:
                        if fuzz.token_set_ratio(clean_spot_title, clean_cand_title) == 100:
                            logging.info(f"  [-] Local match found ({f}), skipping.")
                            return f, "Skipped"

        logging.info(f"\n🎵 Processing: {spotify_title} by {spotify_artist}")

        
        # Extract Primary Artist for more targeted search
        spotify_primary = self.get_primary_artist(spotify_artist)
        
        # If the track is already a specific mix/remix, skip all modifiers to avoid muddying the search
        spotify_title_lower = spotify_title.lower()
        # Omit "radio" variants so we intentionally hunt for longer mixes of radio edits
        inherent_mix_keywords = ["extended", "club mix", "remix", "remixed", "mixed", "mix", "rework", "vip", "flip", "bootleg", "mashup"]
        if not get_extended:
            logging.info(f"  [i] Extended mix hunting disabled. Searching for direct match only.")
            modifiers = [""]
        elif any(keyword in spotify_title_lower for keyword in inherent_mix_keywords):
            logging.info(f"  [i] Inherent mix detected in title. Bypassing modifier loop.")
            modifiers = [""]
        else:
            modifiers = ["Extended", "Original Mix", "Club Mix", ""]

        best_candidate = None
        best_score = 0
        chosen_modifier = ""
        
        for mod in modifiers:
            search_query = f"{spotify_title} {mod} {spotify_primary}".strip()
            
            # Remove dashes which can sometimes confuse the search engine
            search_query = search_query.replace("-", " ")
            
            # Apply blacklist
            for word in self.search_blacklist:
                search_query = re.sub(rf'\b{word}\b', '', search_query, flags=re.IGNORECASE)
            search_query = " ".join(search_query.split()).strip()

            logging.info(f"  [?] Search Attempt: '{mod}' | Query: {search_query}")

            params = {'s': search_query, 'type': 'track', 'limit': 25}
            
            try:
                response = self.make_api_request('/search', params=params, timeout=30)
                results = response.json().get("data", {}).get("items", [])
                
                for item in results:
                    score = self.calculate_match_score(spotify_title, spotify_primary, spotify_duration, item, mod)
                    # We require a passing grade (e.g., base of 150+ to consider valid)
                    if score > best_score and score >= 150:
                        best_score = score
                        best_candidate = item
                        chosen_modifier = mod
                        
                if best_candidate:
                    break  # Stop trying lesser modifiers if we found a valid match

            except Exception as e:
                logging.error(f"  [❌] Search error on modifier '{mod}': {e}")
                continue

        try:
            if not best_candidate:
                logging.warning(f"  [!] No valid match for: {spotify_title} - {spotify_artist}")
                error_filename = f"{safe_base_name} - NOT FOUND.nfo"
                error_file = os.path.join(folder, error_filename)
                with open(error_file, "w", encoding='utf-8') as f:
                    f.write(f"Track: {spotify_title}\nArtist: {spotify_artist}\nPrimary Artist: {spotify_primary}\nError: Track did not pass fuzzy validation thresholds across all attempts.")
                return error_filename, "Error"

            track_id = best_candidate["id"]
            cand_title = best_candidate.get('title', 'Unknown')
            cand_version = best_candidate.get('version')
            if cand_version and cand_version.lower() not in cand_title.lower():
                cand_title = f"{cand_title} ({cand_version})"
            cand_artist_name = best_candidate.get('artist', {}).get('name', 'Unknown')
            
            logging.info(f"  [✔ ] Match Found on '{chosen_modifier}' (Score: {best_score}) => {cand_title} by {cand_artist_name} [ID {track_id}]")

            # Use Monochrome (Tidal) title for the final filename
            monochrome_base_name = self.sanitize_filename(f"{cand_title} - {cand_artist_name}")
            final_filename = f"{monochrome_base_name}.flac"
            file_path = os.path.join(folder, final_filename)

            # Re-check existence with the new name to be safe
            if not overwrite and os.path.exists(file_path):
                logging.info(f"  [-] Monochrome file already exists, skipping: {final_filename}")
                return final_filename, "Skipped"

            if playlist_only:
                logging.info(f"  [⏭️] Playlist Only mode: Skipping stream downlaod for {final_filename}")
                
                cand_duration_str = best_candidate.get("duration", "0")
                try:
                    cand_duration = int(cand_duration_str)
                except ValueError:
                    cand_duration = 0
                    
                mix_type = "Extended Mix" if chosen_modifier in ["Extended Mix", "Original Mix"] else "Direct Match"
                if cand_duration and spotify_duration:
                    duration_diff = cand_duration - (spotify_duration / 1000.0)
                    if duration_diff >= 10 and mix_type != "Direct Match":
                        mix_type += " (Longer)"
                        
                return final_filename, mix_type

            # 3. Request LOSSLESS Stream Info
            track_params = {'id': track_id, 'quality': 'LOSSLESS'}
            
            stream_response = self.make_api_request('/track/', params=track_params, timeout=15)

            stream_data = stream_response.json().get("data", {})
            
            manifest_b64 = stream_data.get("manifest")
            if not manifest_b64:
                raise ValueError(f"No audio manifest returned for ID {track_id}")

            manifest = json.loads(base64.b64decode(manifest_b64))
            audio_urls = manifest.get("urls", [])
            if not audio_urls:
                raise ValueError(f"No audio tracks found in manifest for ID {track_id}")

            audio_url = audio_urls[0]
            
            logging.info(f"  [⌛] Downloading FLAC Lossless to: {file_path}")

            download_success_flag = False
            max_download_attempts = 3
            for attempt in range(1, max_download_attempts + 1):
                try:
                    audio_stream = requests.get(audio_url, stream=True, timeout=30)
                    audio_stream.raise_for_status() 
                    
                    # Retrieve expected content length from headers
                    expected_size = audio_stream.headers.get('Content-Length')
                    if expected_size is not None:
                        expected_size = int(expected_size)
                    
                    with open(file_path, 'wb') as f:
                        downloaded_size = 0
                        for chunk in audio_stream.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)
                    
                    if downloaded_size == 0:
                        raise ValueError("Download returned 0 bytes")
                        
                    # The Golden Rule Check
                    if expected_size is not None and downloaded_size < expected_size:
                        raise ValueError(f"Incomplete download: Received {downloaded_size} bytes, expected {expected_size} bytes")
                        
                    download_success_flag = True
                    break  # Successful download, exit the loop
                except Exception as e:
                    logging.warning(f"  [⚠️] Download interrupted on attempt {attempt}/{max_download_attempts}: {e}")
                    if os.path.exists(file_path):
                        os.remove(file_path) # Clean up partial file
                    if attempt == max_download_attempts:
                        raise ValueError(f"Failed to download {final_filename} after {max_download_attempts} attempts: {e}")
                    time.sleep(2)  # Small backoff before retry

            # Use double check for Extended/Special matches to make them pop
            download_success = "✨Extended Mix Downloaded" if chosen_modifier != "" else "Direct Match Downloaded"
            logging.info(f"  [✅] {download_success} (HTTP {audio_stream.status_code}) | Size: {downloaded_size / (1024*1024):.2f} MB")

            # 5. Metadata Injection
            self.tag_track(file_path, best_candidate)
            
            cand_duration_str = best_candidate.get("duration", "0")
            try:
                cand_duration = int(cand_duration_str)
            except ValueError:
                cand_duration = 0
                
            mix_type = "Extended Mix" if chosen_modifier in ["Extended Mix", "Original Mix"] else "Direct Match"
            if cand_duration and spotify_duration:
                duration_diff = cand_duration - (spotify_duration / 1000.0)
                if duration_diff >= 10 and mix_type != "Direct Match":
                    mix_type += " (Longer)"
                    
            return final_filename, mix_type

        # Fatal error logging
        except Exception as e:
            logging.error(f"  [❌] Fatal error processing {track_data['title']}: {e}")
            raise
