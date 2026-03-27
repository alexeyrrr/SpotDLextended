import argparse

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "🎵 SpotDLextended: Spotify to FLAC Extended DJ Mix Downloader\n\n"
            "This tool finds equivalent tracks from your Spotify playlist and downloads them in Lossless FLAC quality.\n"
            "Matching Logic:\n"
            "  1. It first attempts to find an 'Extended Mix' or 'Original Mix' using multi-attempt fuzzy searching.\n"
            "  2. If a specialized mix isn't found, it defaults to the closest direct match available.\n"
            "  3. It validates duration and metadata to ensure the highest quality match.\n\n"
            "Features:\n"
            "  - Automatic high-res metadata and cover art tagging.\n"
            "  - Customizable output directories.\n"
            "  - Smart update logic (skips existing files unless forced)."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Examples:\n  spotdlextended -u [URL]\n  spotdlextended --force --dir /mnt/d/Music\n  spotdlextended --help"
    )

    parser.add_argument(
        "-u", "--url", 
        default=None,
        help="Spotify Playlist URL to process."
    )
    
    parser.add_argument(
        "-f", "--force", 
        action="store_true", 
        help="FULL OVERWRITE: Replace existing files. (Default: UPDATE ONLY - skips existing tracks)."
    )

    parser.add_argument(
        "-o", "--output", "--dir",
        dest="dir",
        default=None,
        help="SET OUTPUT FOLDER: Root directory for your music. (Defaults to your saved settings)"
    )

    parser.add_argument(
        "-p", "--playlist-only", 
        action="store_true", 
        help="PLAYLIST ONLY: Generates the .m3u8 playlist file by resolving valid tracks, without downloading audio files."
    )

    parser.add_argument(
        "--no-extended", 
        action="store_true", 
        help="DIRECT MATCH ONLY: Disables hunting for 'Extended/Club' mixes and strictly searches for the exact track."
    )

    return parser, parser.parse_args()
