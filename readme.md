<h1 align="center">🎵 Spotify to FLAC Extended DJ Mix Downloader 🎵</h1>

<p align="center">
  <strong>A tool that generates local `.m3u8` playlists from Spotify playlists. It can also download tracks as Lossless FLAC files, prioritizing extended / club / original mixes by default. Drag the m3u8 file into Serato, Rekordbox, Traktor etc and you're good to go.
  </strong>
</p>

<p align="center">
  This script doesn't rely on YouTube Music or any other sources except Tidal, nor does it upsample/convert any files.
</p>

<p align="center">
  <a href="#features">Features</a> -
  <a href="#installation">Installation</a> -
  <a href="#usage">Usage</a> -
  <a href="#how-it-works">How It Works</a> -
  <a href="#faq">FAQ</a> -
  <a href="#acknowledgements">Acknowledgements</a> -
  <a href="#contributing">Contributing</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.x-yellow?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.x">
  <img src="https://img.shields.io/badge/FLAC-Lossless-blue?style=for-the-badge" alt="FLAC Lossless">
  <img src="https://img.shields.io/badge/Spotify-Integration-1DB954?style=for-the-badge&logo=spotify&logoColor=white" alt="Spotify">
</p>

---

## What is SpotDLextended?

**SpotDLextended** is a playlist utility that takes a Spotify playlist URL, extracts the track data and resolves individual tracks to high-fidelity download links. Its primary function is to generate local `.m3u8` playlists - preserving your original playlist order - that can then be used in DJ software (Serato, Rekordbox, Traktor). It can also download all the tracks as high-quality Lossless FLAC files.
 
> [!NOTE]
> **Designed primarily for DJs and audiophiles:** the matching engine prioritizes **Extended Mixes**, **Original Mixes**, and **Club Mixes** over standard radio mixes or direct track matches. Unless overridden (via arguments or settings.json file), it will always attempt to download an extended mix if it is available.

> [!IMPORTANT]
> **Read Before Use**: SpotDLextended now features a persistent configuration system. On your first run, the tool will guide you through a quick setup to define your music library path. Default paths are OS-aware (e.g., `~/Music/` on Linux/macOS or `%USERPROFILE%\Music\` on Windows).
> **Please use it only for personal use and respect copyright laws.** This is strictly designed for educational purposes with no intention of copyright infringement, implied or otherwise.

---

## 🚀 Quick Start (Non-developers)
If you want to download playlists without installing Python, follow these steps:
1.  **Download the latest version**: Look at the **"Releases"** section on the right-hand side of this page.
2.  **Download `SpotDLextended.exe`**: Click on the latest release and download the `.exe` file from the assets.
3.  **Run it**: And follow the on-screen instructions

---


## Features

### Intelligent Match Engine
Instead of blindly downloading the exact Spotify match, SpotDLextended acts like a DJ crate digger:
- **Extended Mix First:** It intentionally seeks out `Extended`, `Original Mix`, or `Club Mix` versions.
- **Fuzzy Name Validation:** Uses a multi-layered validation engine to evaluate track title and artist similarity, avoiding false positives.
- **Duration Logic Check:** Ensures the retrieved track length makes sense relative to the original Spotify duration and the mix modifier applied.
- **Resiliency:** Handles anti-patterns, rate limits across 13 fallback endpoints, and automatically avoids unwanted bootlegs/remixes/radio edits unless specifically requested.

### Audio Quality & Metadata
- **Lossless Audio:** Downloads lossless FLAC audio files.
- **High-Res Metadata Injection:** Automatically tags downloaded FLACs with `Title`, `Artist`, `Album`, `BPM`, `Key`, `Duration` and `1280x1280 Cover Art`.

### Additional Features
- **`.m3u8` Playlist Generation:** Auto-generates local playist files with relative/absolute pathing for seamless import into DJ software (Serato, Rekordbox, Traktor). 
- **Smart Pathing for WSL:** Built-in WSL-to-Windows filesystem translation mapping `/mnt/c/` style paths automatically.
- **Fail-Safe Processing:** Skips existing local downloads by name checking and fuzzy validation.
- **Persistent Settings:** Your preferences (output directory, overwrite behavior, etc.) are saved in `settings.json` at the project root.
- **Extended Mix Toggle:** Prefer the original radio edit? Use `--no-extended` to disable the hunt for club versions.
- **Playlist Only Mode:** Need to generate just a local playlist file (`.m3u8`)? Use `--playlist-only`.


> [!CAUTION]
> **SpotDLextended does not require Spotify login/API keys or Tidal API keys**, nor does it store any personal information. Because it uses public endpoints and scrapers, there is **virtually zero risk** of your personal accounts being affected.
> 
> The only theoretical risk is IP-based rate limiting from public API endpoints if used excessively. The script’s built-in endpoint rotation and fallback logic are designed to minimize this.

---

## Installation

### Prerequisites

- Python 3.x
- Git

### Option 1: Development Install (Recommended)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/spotdl-ext.git
   cd spotdl-ext
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Linux/macOS
   # OR
   .venv\Scripts\activate     # On Windows
   ```

3. **Install in editable mode:**
   ```bash
   pip install -e .
   ```

### Option 2: Global Installation via pipx

For an isolated, globally accessible installation:

```bash
pipx install git+https://github.com/yourusername/spotdl-ext.git
```

---

## Usage

### Interactive Mode

Simply run the `spotdl-ext` command and follow the prompt:
```bash
spotdl-ext
```

### CLI Mode

You can supply arguments directly via the command line:

```bash
# Basic download from URL
spotdl-ext -u "https://open.spotify.com/playlist/YOUR_PLAYLIST_ID"

# Force overwrite (overrides settings.json)
spotdl-ext -f -u "https://open.spotify.com/playlist/YOUR_PLAYLIST_ID"

# Disable Extended Mix hunting
spotdl-ext --no-extended -u "https://open.spotify.com/playlist/YOUR_PLAYLIST_ID"

# Generate playlist ONLY without downloading
spotdl-ext -p -u "https://open.spotify.com/playlist/YOUR_PLAYLIST_ID"
```

### Options

| Flag | Name | Description |
|------|------|-------------|
| `-u`, `--url` | URL | Spotify Playlist URL to process. |
| `-f`, `--force` | Force | FULL OVERWRITE: Replace existing files. |
| `-o`, `--output` | Output Dir | SET OUTPUT FOLDER: Root directory for your music. |
| `-p`, `--playlist` | Playlist Only | Generate .m3u8 without downloading audio. |
| `--no-extended` | No Extended | Skip searching for Extended/Club mixes. |

### Configuration (`settings.json`)

Located at the project root, this file stores your defaults:
- `music_dir`: Your default download path.
- `full_overwrite`: Default `true`/`false` for overwriting.
- `get_extended_mixes`: Set to `false` to always prefer direct matches.
- `playlist_only`: Set to `true` to only generate playlists by default.

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  1. PLAYLIST PREPARATION (Spotify)                              │
│     Save tracks to a playlist on Spotify in desired order       │
│     Copy playlist URL                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. RUN SpotDLextended & PASTE URL                              │
│     Start the script and paste your Spotify Playlist URL        │
│     Data extraction begins via internal Headless Scraper        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. INTELLIGENT MATCH ENGINE                                    │
│     Finds best version on Monochrome / Tidal                    │
│     Prioritizes Extended, Original, & Club Mixes                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. VALIDATION & SCORING                                        │
│     Verifies identity, length, and audio quality                │
│     Prevents false-positive downloads                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. GENERATION & OUTPUT                                         │
│     Creates local `.m3u8` & optional FLAC downloads             │
│     Folders organized by Spotify Playlist Name                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## FAQ

### Why wasn't my track downloaded correctly or not found?
There can be several factors at play if a track is missed or fails to download:
- **Service Availability**: The primary reason is that a track might be published on Spotify but not available on alternative services like Tidal or the Monochrome API endpoints. 
- **Download Errors**: Occasional API timeouts or network interruptions can cause a download to fail during the streaming phase.
- **Strict Matching Thresholds**: To prevent your library from being filled with incorrect songs, the matching engine uses strict fuzzy-logic thresholds. If a high-confidence match isn't found, the script skips the track rather than risking a "false positive" download.

## Acknowledgements

SpotDLextended is built upon the foundation of several incredible open-source projects:

- **[SpotifyScraper](https://github.com/AliAkhtari78/SpotifyScraper)**: Providing the core logic for headless playlist data extraction.
- **[Hifi-API](https://github.com/binimum/hifi-api)**: For the high-fidelity streaming endpoints and API structure.
- **[Monochrome](https://github.com/monochrome-music/monochrome)**: For the inspiration behind the matching logic and clean API implementation.

---

## Contributing

We welcome contributions from the community! 

- **Got a suggestion?** Feel free to open an issue to discuss new features or improvements.
- **Want to improve something?** If you'd like to see a different implementation or have a better approach in mind, please reach out or submit a PR.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Made with ❤️ in SoCal
</p>
