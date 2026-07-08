import os
import re
import logging
from pathlib import Path
from spotify_scraper import SpotifyClient
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from spotdlextended.settings import get_settings, FALLBACK_DEFAULT_DIR
from spotdlextended.cli import parse_args
from spotdlextended.downloader import Downloader

# --- CONFIGURATION ---
DEFAULT_PLAYLIST_URL = "https://open.spotify.com/playlist/5wr9DG59AWCoXMfUqd4KFW"

# --- DOWNLOAD DIRECTORY SETUP ---

def translate_path_to_os(path_str):
    """
    Translates a Windows-style path (e.g., 'C:/Music/' or '%USERPROFILE%/Music/')
    to a valid OS-specific path, safely mapping into basic WSL/Linux paths.
    """
    if not path_str:
        return path_str
        
    path_str = path_str.replace('\\', '/')
    
    # Translate %USERPROFILE% -> ~
    if "%USERPROFILE%" in path_str.upper():
        path_str = re.sub(r'(?i)%USERPROFILE%', '~', path_str)
        
    path_str = os.path.expanduser(path_str)
    
    if os.name == 'nt':
        return os.path.expandvars(path_str)
        
    # Translate Windows Drive letters C:/... -> /mnt/c/... for WSL users
    match = re.match(r'^([a-zA-Z]):/(.*)', path_str)
    if match:
        drive_letter = match.group(1).lower()
        rest_of_path = match.group(2)
        
        # Verify if running in WSL by validating the mount exists
        if os.path.exists(f"/mnt/{drive_letter}"):
            path_str = f"/mnt/{drive_letter}/{rest_of_path}"
        else:
            # Fallback to relative path if not mounted
            path_str = str(Path(__file__).resolve().parent.parent)
            
    return path_str


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def create_m3u8_playlist(base_dir, playlist_folder_name, track_filenames):
    """
    Creates an M3U8 playlist file in the base directory.
    The tracks inside will be prepended with the playlist folder name.
    """
    playlist_path = os.path.join(base_dir, f"{playlist_folder_name}.m3u8")
    
    # Smarter Path Output for WSL <=> Windows Interoperability
    if base_dir.startswith("/mnt/"):
        # Automatically translate /mnt/c/ to C:/
        parts = base_dir.split('/')
        if len(parts) >= 3 and len(parts[2]) == 1:
            drive_letter = parts[2].upper()
            m3u_base = f"{drive_letter}:/" + "/".join(parts[3:])
        else:
            m3u_base = base_dir
    else:
        m3u_base = base_dir

    try:
        with open(playlist_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for filename in track_filenames:
                file_path = os.path.join(base_dir, playlist_folder_name, filename)
                ext = os.path.splitext(filename)[1].lower()
                try:
                    if ext == ".flac":
                        audio = FLAC(file_path)
                        duration = int(audio.info.length)
                        title = audio.get("TITLE", [""])[0] or filename
                        artist = audio.get("ARTIST", [""])[0] or "Unknown Artist"
                        bpm = audio.get("BPM", [""])[0]
                        key = audio.get("INITIALKEY", [""])[0]
                    elif ext == ".mp3":
                        audio = MP3(file_path, ID3=ID3)
                        duration = int(audio.info.length)
                        title = audio.tags.get("TIT2").text[0] if audio.tags and audio.tags.get("TIT2") else filename
                        artist = audio.tags.get("TPE1").text[0] if audio.tags and audio.tags.get("TPE1") else "Unknown Artist"
                        bpm = audio.tags.get("TBPM").text[0] if audio.tags and audio.tags.get("TBPM") else ""
                        key = audio.tags.get("TKEY").text[0] if audio.tags and audio.tags.get("TKEY") else ""
                    else:
                        duration = -1
                        title = filename
                        artist = "Unknown Artist"
                        bpm = ""
                        key = ""
                    
                    ext_info = f"#EXTINF:{duration},{artist} - {title}"
                    if bpm or key:
                        tags = []
                        if bpm: tags.append(f"bpm={bpm}")
                        if key: tags.append(f"key={key}")
                        ext_info += f" | {' | '.join(tags)}"
                        
                    f.write(ext_info + "\n")
                except Exception:
                    # Fallback if parsing fails
                    f.write(f"#EXTINF:-1,{filename}\n")

                # 2. Add the track path location
                abs_track_path = os.path.join(m3u_base, playlist_folder_name, filename)
                abs_track_path = abs_track_path.replace("\\\\", "/")
                f.write(f"{abs_track_path}\n")
                
        logging.info(f"  [✓] Created metadata-rich playlist: {playlist_path}")
    except Exception as e:
        logging.error(f"  [❌] Error creating playlist: {e}")


def regenerate_playlist(base_dir, playlist_folder_name):
    """
    Regenerates the .m3u8 playlist for an existing folder by scanning it for audio tracks.
    """
    playlist_folder = os.path.join(base_dir, playlist_folder_name)
    if not os.path.exists(playlist_folder):
        logging.error(f"  [❌] Folder not found: {playlist_folder}")
        return

    logging.info(f"Scanning folder '{playlist_folder_name}' for audio tracks...")
    valid_extensions = {".flac", ".m4a", ".mp3", ".wav", ".ogg"}
    track_filenames = []
    
    try:
        for f in os.listdir(playlist_folder):
            if os.path.isfile(os.path.join(playlist_folder, f)) and os.path.splitext(f)[1].lower() in valid_extensions:
                track_filenames.append(f)
                
        if not track_filenames:
            logging.warning(f"  [⚠️] No valid audio files found in {playlist_folder}")
            return
            
        # Sort files by modification time to preserve original download order
        track_filenames.sort(key=lambda f: os.path.getmtime(os.path.join(playlist_folder, f)))
        
        logging.info(f"  [ℹ️] Found {len(track_filenames)} tracks. Generating playlist...")
        create_m3u8_playlist(base_dir, playlist_folder_name, track_filenames)
        
    except Exception as e:
        logging.error(f"  [❌] Error scanning directory: {e}")


def main():
    parser, args = parse_args()
    
    # Load settings and handle onboarding if it's the first run
    settings = get_settings()
    if not args.dir:
        args.dir = settings.get("download_dir", FALLBACK_DEFAULT_DIR)
        
    # Merge settings with CLI arguments (Settings take effect if True)
    if settings.get("full_overwrite", False):
        args.force = True
        
    if settings.get("playlist_only", False):
        args.playlist_only = True
        
    # Extended Mix logic
    get_ext = settings.get("get_extended_mixes", True)
    if args.no_extended:
        get_ext = False
    
    # Convert whatever path is provided into its OS-correct equivalent
    args.dir = translate_path_to_os(args.dir)

    if args.regenerate:
        regen_path = translate_path_to_os(args.regenerate)
        regen_path = os.path.abspath(regen_path)
        regen_base_dir = os.path.dirname(regen_path)
        regen_folder_name = os.path.basename(regen_path)
        
        logging.info(f"Regenerating playlist for: {regen_path}")
        regenerate_playlist(regen_base_dir, regen_folder_name)
        return

    # We will loop infinitely to allow multiple downloads without the window closing
    is_first_prompt = True
    current_url = args.url

    while True:
        # Prompt for URL if not provided via CLI
        if not current_url:
            print(f"\n🎵 \033[1mSpotify Playlist (+Extended Mix) Downloader\033[0m: 🎵")
            if is_first_prompt:
                print(f"\n   \033[3m--help for more information\033[0m")
                is_first_prompt = False
                
            print(f"\nEnter Spotify Playlist URL (or 'q' to quit):")
            user_input = input("> ").strip()
            
            if user_input.lower() in ["help", "--help"]:
                parser.print_help()
                continue
            if user_input.lower() in ['q', 'quit', 'exit']:
                break
                
            current_url = user_input if user_input else DEFAULT_PLAYLIST_URL

        # Setup Spotify Scraper
        # Using 'selenium' forces the scraper to load the page in a headless browser,
        # giving the JavaScript time to render the full playlist instead of just the initial chunk.
        client = SpotifyClient()
        logging.info(f"Connecting to Spotify Playlist: {current_url}")
        try:
            playlist = client.get_playlist_info(current_url)
        except Exception as e:
            logging.error(f"Failed to fetch playlist: {e}")
            current_url = None
            continue
        
        playlist_name = Downloader.sanitize_filename(playlist.get('name', 'My_Playlist'))
        
        raw_tracks = playlist.get('tracks', [])
        logging.info(f"  [ℹ️] Found {len(raw_tracks)} tracks in playlist: '{playlist.get('name', 'Unknown')}'")

        # Extract Title, Artist, and Duration into a structured list
        tracks = []
        for t in playlist.get('tracks', []):
            artist_name = t['artists'][0]['name'] if t.get('artists') else "Unknown"
            track_name = t.get('name', 'Unknown')
            duration_ms = t.get('duration_ms', t.get('durationMs', 0))
            tracks.append({
                'title': track_name, 
                'artist': artist_name,
                'duration_ms': duration_ms,
                'uri': t.get('uri')
            })


        # Build folder structure
        playlist_folder = os.path.join(args.dir, playlist_name)
        
        for path in [args.dir, playlist_folder]:
            if not os.path.exists(path):
                os.makedirs(path)
                logging.info(f"Created directory: {path}")

        # Remove all existing .nfo error logs in the playlist folder for a clean run
        for f in os.listdir(playlist_folder):
            if f.endswith(".nfo"):
                try:
                    os.remove(os.path.join(playlist_folder, f))
                except Exception:
                    pass


        # Start Batch Process
        logging.info(f"Starting download of {len(tracks)} tracks...")
        
        # Initialize our Downloader class
        downloader = Downloader(spotify_client=client)
        
        downloaded_filenames = []
        summary_stats = {}
        
        for track_data in tracks:
            filename, mix_category = downloader.download_track(
                track_data, 
                playlist_folder, 
                args.force, 
                args.playlist_only,
                get_extended=get_ext
            )
            
            # Only add valid FLACs to playlist, ignoring the text error files
            if filename and mix_category != "Error":
                downloaded_filenames.append(filename)
                
            summary_stats[mix_category] = summary_stats.get(mix_category, 0) + 1
        
        # Final Step: Create M3U8 Playlist
        if downloaded_filenames:
            create_m3u8_playlist(args.dir, playlist_name, downloaded_filenames)
            
        # Calculate Summary
        total_tracks = len(tracks)
        skipped_count = summary_stats.get("Skipped", 0)
        error_count = summary_stats.get("Error", 0)
        downloaded_total = total_tracks - skipped_count - error_count
        
        logging.info("--- DOWNLOAD SUMMARY ---")
        logging.info(f"  Playlist Total: {total_tracks} tracks")
        logging.info(f"  Already On Disk: {skipped_count}")
        logging.info(f"  Downloaded: {downloaded_total}")
        for mix, count in sorted(summary_stats.items()):
            if mix not in ["Skipped", "Error"]:
                logging.info(f"    - {mix}: {count}")
        logging.info(f"  Not Matched / Error: {error_count}")
        logging.info("Batch processing complete.")
        
        # Reset current_url so it prompts again on the next loop!
        current_url = None

if __name__ == "__main__":
    main()