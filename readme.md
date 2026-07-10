<h1 align="center">🎵 Spotify to 320kbps MP3 Extended DJ Mix Downloader 🎵</h1>

<p align="center">
  <strong>A tool that generates local `.m3u8` playlists and Rekordbox XML databases from Spotify playlists. It downloads tracks as high-quality 320kbps MP3 files (transcoded locally from FLAC/lossless sources), prioritizing extended / club / original mixes by default. Drag the playlist files directly into your DJ software (Serato, Rekordbox, Traktor) and begin mixing.
  </strong>
</p>

<p align="center">
  This script doesn't rely on YouTube Music or web scrapers. It queries the Soulseek P2P network directly via the `sockseek` binary.
</p>

<p align="center">
  <a href="#features">Features</a> -
  <a href="#installation-and-setup">Installation & Setup</a> -
  <a href="#usage">Usage</a> -
  <a href="#how-it-works">How It Works</a> -
  <a href="#faq">FAQ</a> -
  <a href="#acknowledgements">Acknowledgements</a> -
  <a href="#contributing">Contributing</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.x-yellow?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.x">
  <img src="https://img.shields.io/badge/Audio-320kbps%20MP3-blue?style=for-the-badge" alt="320kbps MP3">
  <img src="https://img.shields.io/badge/Spotify-Integration-1DB954?style=for-the-badge&logo=spotify&logoColor=white" alt="Spotify">
</p>

---

## What is SpotDLextended?

**SpotDLextended** is a playlist utility that takes a Spotify playlist URL, extracts the track data, and resolves individual tracks to high-fidelity download sources on the Soulseek P2P network. Its primary function is to generate local `.m3u8` playlists and a `rekordbox.xml` database—preserving your original playlist order—for seamless import into DJ software (Serato, Rekordbox, Traktor). It automates candidate searching, metadata comparison, spectral quality analysis, and transcoding.
 
> [!NOTE]
> **Designed primarily for DJs and audiophiles:** the matching engine prioritizes **Extended Mixes**, **Original Mixes**, and **Club Mixes** over standard radio mixes or direct track matches. Unless overridden (via arguments or settings.json file), it will always attempt to download an extended mix if it is available.

> [!IMPORTANT]
> **Read Before Use**: SpotDLextended features a persistent configuration system. On your first run, the tool will guide you through a quick setup to define your music library path and Soulseek credentials. Default paths are OS-aware (e.g., `~/Music/` on Linux/macOS or `%USERPROFILE%\Music\` on Windows).
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
- **Resiliency:** Automatically blacklists slow, country-restricted, or over-queued peers for the session to maintain maximum transfer speeds. Handles fallback searches seamlessly.

### Audio Quality & Verification
- **Spectral MP3 Verification:** Actively validates downloaded MP3 files using a dynamic spectral FFT algorithm. Detects and skips upscale fakes (e.g., 128kbps or 192kbps upsampled to 320kbps) by checking for brickwall cutoffs at 16kHz and 18.5kHz.
- **Lossless Transcoding:** Downloads high-quality FLAC/lossless files and transcodes them locally to 320kbps MP3 (via FFmpeg) to enforce a uniform DJ library format.
- **High-Res Metadata Injection:** Automatically tags downloaded MP3s with `Title`, `Artist`, `Album`, `BPM` (if available), `Key` (Initial Key), `Duration`, and `1280x1280 Cover Art`.

### DJ Integration & Workflows
- **Rekordbox XML Integration:** Automatically generates or merges tracks into a `rekordbox.xml` file at the root of your library. Import playlists directly into Rekordbox with tracks, tags, ISRC, and structures fully prepared.
- **`.m3u8` Playlist Generation:** Auto-generates local playlist files with relative/absolute pathing for seamless import into DJ software. 
- **Smart Pathing for WSL:** Built-in WSL-to-Windows filesystem translation mapping `/mnt/c/` style paths automatically to Windows-native formats for Rekordbox and M3U8 compatibility.
- **Fail-Safe Processing:** Skips existing local downloads by name checking and fuzzy validation.
- **Persistent Settings:** Your preferences (output directory, overwrite behavior, path mappings, etc.) are saved in `settings.json` at the project root.
- **Extended Mix Toggle:** Prefer the original radio edit? Use `--no-extended` to disable the hunt for club versions.
- **Upgrade to Extended:** Already have a library of standard mixes? Use `--upgrade-extended` (or `-e`) to re-scan existing tracks and automatically replace standard mixes with extended/club/original mixes when found on Soulseek. The old file is only removed after a confirmed successful download.
- **Playlist Only Mode:** Need to generate local playlist files (`.m3u8` / `rekordbox.xml`) for files you already have? Use `--playlist-only`.
- **Playlist Regeneration:** Need to fix or recreate playlist files for an existing folder? Use `--regenerate "/complete/path/to/Folder Name"` to rebuild them while preserving the original track order.


> [!CAUTION]
> **SpotDLextended does not require Spotify login/API keys**, nor does it store any personal information. Because it uses public endpoints and scrapers, there is **virtually zero risk** of your personal accounts being affected.
> 
> The only theoretical risk is IP-based rate limiting from public API endpoints if used excessively. The script’s built-in endpoint rotation and fallback logic are designed to minimize this.

---

## Installation

### Prerequisites
- **FFmpeg**: Required for audio transcoding and spectral analysis. Ensure it is accessible in your system PATH.
- **Python 3.x**
- **Git**

### Linux & macOS

1. **Clone the repository:**
   ```bash
   git clone https://github.com/alexeyrrr/spotDLextended.git && cd spotDLextended
   ```

2. **Run the installation script:**
   This downloads the latest `sockseek` binary into `~/.local/bin` and creates a default config template:
   ```bash
   ./install.sh
   ```

3. **Configure Soulseek Credentials:**
   Open the generated config file in a text editor:
   ```bash
   nano ~/.config/sockseek/sockseek.conf
   ```
   Enter your Soulseek username and password, then save.

4. **Install Python dependencies & package:**
   ```bash
   python3 -m venv .venv && source .venv/bin/activate  
   pip install -e .
   ```

### Windows & Non-Developers

1. **Download the latest release:** Get the packaged `SpotDLextended.exe` from the **Releases** page.
2. **First Run:** Run `SpotDLextended.exe`. This initializes the default directory structure.
3. **Configure Soulseek Credentials:**
   - Open `%APPDATA%\sockseek\sockseek.conf` in a text editor (e.g. Notepad).
   - Enter your Soulseek `username` and `password`.
   - Update `output-dir` if you wish to change the default music directory.
4. **Run the tool:** Execute the binary again and provide your Spotify playlist URL.

---

## Usage

### Interactive Mode

Simply run the `spotdlextended` command and follow the prompt:
```bash
spotdlextended
```

### CLI Mode

You can supply arguments directly via the command line:

```bash
# Basic download from URL
spotdlextended -u "https://open.spotify.com/playlist/YOUR_PLAYLIST_ID"

# Force overwrite (overrides settings.json)
spotdlextended -f -u "https://open.spotify.com/playlist/YOUR_PLAYLIST_ID"

# Upgrade all existing standard mixes to extended mixes
spotdlextended -e -u "https://open.spotify.com/playlist/YOUR_PLAYLIST_ID"

# Disable Extended Mix hunting
spotdlextended --no-extended -u "https://open.spotify.com/playlist/YOUR_PLAYLIST_ID"

# Generate playlist ONLY without downloading
spotdlextended -p -u "https://open.spotify.com/playlist/YOUR_PLAYLIST_ID"
```

### Options

| Flag | Name | Description |
|------|------|-------------|
| `-u`, `--url` | URL | Spotify Playlist URL to process. |
| `-f`, `--force` | Force | FULL OVERWRITE: Replace existing files. |
| `-e`, `--upgrade-extended` | Upgrade Extended | Re-scan existing tracks and replace standard mixes with extended/club/original mixes if found. Files already identified as a mix are skipped; old file deleted only after confirmed success. |
| `-o`, `--output` / `--dir` | Output Dir | SET OUTPUT FOLDER: Root directory for your music. |
| `-p`, `--playlist-only` | Playlist Only | Generate `.m3u8` and `rekordbox.xml` without downloading audio. |
| `--no-extended` | No Extended | Skip searching for Extended/Club mixes. |
| `-d`, `--debug` | Debug | Enable verbose debugging output (also passed to `sockseek`). |
| `-r`, `--regenerate` | Regenerate | Rebuild playlist files for an existing folder. |

### Configuration (`settings.json`)

Located at the project root, this file stores your defaults:
- `download_dir`: Your default download path.
- `full_overwrite`: Default `true`/`false` for overwriting.
- `get_extended_mixes`: Set to `false` to always prefer direct matches.
- `playlist_only`: Set to `true` to only generate playlists by default.
- `rekordbox_path_mapping`: Optional prefix mappings (e.g. `{"/mnt/d/": "D:/"}`) to translate directory structures for Rekordbox import.

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  1. PLAYLIST PREPARATION (Spotify)                              │
│     Save tracks to a Spotify playlist and copy the URL          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. HEADLESS SCRAPING                                           │
│     Extract metadata (Title, Artist, Duration, ISRC, Cover Art)  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. SOULSEEK P2P SEARCH (via sockseek)                          │
│     Queries Soulseek, prioritizing Extended, Original, & Club   │
│     mixes while skipping banned or over-queued peers.           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. HEURISTIC VALIDATION & SCORING                              │
│     Filters candidates by duration, format, and fuzzy match.    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. TEMPORARY DOWNLOAD & METADATA VERIFICATION                  │
│     Downloads candidate to verify embedded tags/ISRC.           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  6. SPECTRAL QUALITY ANALYSIS & TRANSCODING                     │
│     Validates true 320kbps MP3 via FFT or transcodes lossless   │
│     formats (FLAC/WAV) to verified 320kbps MP3.                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  7. METADATA TAGGING & PLAYLIST EXPORT                          │
│     Writes metadata and artwork, builds local .m3u8 playlist,   │
│     and exports rekordbox.xml file for direct DJ import.        │
└─────────────────────────────────────────────────────────────────┘
```

---

## FAQ

### Why wasn't my track downloaded correctly or not found?
There can be several factors at play if a track is missed or fails to download:
- **P2P Availability**: A track might be published on Spotify but not shared by active peers on the Soulseek network. 
- **Connection & Queue Rejections**: Peers might have full queue slots or country blocks. The script automatically handles these cases by blacklisting uncooperative peers for the current session.
- **Upscaled Cutoff Rejections**: If a candidate is downloaded but the spectral check detects it is a fake 320kbps MP3 (upscaled from 128kbps or 192kbps), it is rejected to keep your library clean.
- **Strict Matching Thresholds**: To prevent incorrect downloads, the matching engine uses strict fuzzy-logic thresholds. If a high-confidence match isn't found, the script skips the track.

---

## Acknowledgements

SpotDLextended is built upon the foundation of several incredible open-source projects:

- **[sockseek](https://github.com/fiso64/sockseek)**: Providing the fast, headless Soulseek client binary interface.
- **[SpotifyScraper](https://github.com/AliAkhtari78/SpotifyScraper)**: Providing the core logic for headless playlist data extraction.

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
