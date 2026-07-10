import os
import sys
import json
import platform
from pathlib import Path

if getattr(sys, 'frozen', False):
    # PyInstaller creates a temp folder and stores path in _MEIPASS, returning __file__ in that folder.
    # To save settings right next to the .exe we use sys.executable
    SETTINGS_DIR = Path(sys.executable).resolve().parent
else:
    SETTINGS_DIR = Path(__file__).resolve().parent.parent

SETTINGS_FILE = SETTINGS_DIR / "settings.json"

if os.name == 'nt':
    FALLBACK_DEFAULT_DIR = "%USERPROFILE%/Music/"
else:
    FALLBACK_DEFAULT_DIR = "~/Music/"
DEFAULT_API_ENDPOINTS = [
    "https://api.monochrome.tf",
    "https://monochrome-api.samidy.com",
    "https://hifi.geeked.wtf",
    "https://arran.monochrome.tf",
    "https://triton.squid.wtf",
    "https://wolf.qqdl.site",
    "https://maus.qqdl.site",
    "https://vogel.qqdl.site",
    "https://katze.qqdl.site",
    "https://hund.qqdl.site",
    "https://hifi-one.spotisaver.net",
    "https://hifi-two.spotisaver.net",
    "https://tidal.kinoplus.online",
    "https://tidal-api.binimum.org",
]

def load_settings():
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_settings(settings_data):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings_data, f, indent=4)

# ---------------------------------------------------------------------------
# Sockseek config helpers
# ---------------------------------------------------------------------------

def _is_wsl() -> bool:
    """Returns True when this process is running inside WSL (any version)."""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _wsl_windows_appdata() -> Path | None:
    """Resolve the Windows %APPDATA% directory as a Linux /mnt/... path.

    Uses WSL interop (cmd.exe + wslpath) so we can check the native Windows
    sockseek config even when running from WSL.  Returns None if interop
    is unavailable or the path cannot be determined.
    """
    import subprocess
    try:
        # Ask the Windows CMD shell for the expanded %APPDATA% value.
        win = subprocess.run(
            ["cmd.exe", "/c", "echo %APPDATA%"],
            capture_output=True, text=True, timeout=5
        )
        if win.returncode != 0:
            return None
        appdata_win = win.stdout.strip()
        # If the variable was unexpanded (no interop), bail out.
        if not appdata_win or "%" in appdata_win:
            return None
        # Translate the Windows path to the WSL mount point.
        wsl = subprocess.run(
            ["wslpath", "-u", appdata_win],
            capture_output=True, text=True, timeout=5
        )
        if wsl.returncode == 0 and wsl.stdout.strip():
            return Path(wsl.stdout.strip())
    except Exception:
        pass
    return None


def _get_sockseek_config_dir() -> Path:
    """Returns the PRIMARY (write-target) sockseek config directory for this OS."""
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "sockseek"
        # Fallback if APPDATA is somehow unset
        return Path.home() / "AppData" / "Roaming" / "sockseek"
    return Path("~/.config/sockseek").expanduser()


def _get_default_music_dir() -> str:
    """Returns the OS-appropriate default music directory for the config template."""
    if platform.system() == "Windows":
        userprofile = os.environ.get("USERPROFILE", str(Path.home()))
        return str(Path(userprofile) / "Music")
    else:
        return str(Path("~/Music").expanduser())


def _all_sockseek_config_files() -> list[Path]:
    """Returns every sockseek.conf path that should be checked for credentials.

    On WSL this includes BOTH the Linux-side path (~/.config/sockseek) AND the
    Windows APPDATA path (/mnt/c/Users/.../AppData/Roaming/sockseek) so that
    credentials set up in either environment are recognised.
    """
    primary = _get_sockseek_config_dir() / "sockseek.conf"
    candidates: list[Path] = [primary]

    # WSL: also honour creds stored by native Windows sockseek
    if platform.system() != "Windows" and _is_wsl():
        appdata = _wsl_windows_appdata()
        if appdata:
            win_conf = appdata / "sockseek" / "sockseek.conf"
            if win_conf != primary:
                candidates.append(win_conf)

    return candidates


_PLACEHOLDER_NAMES = frozenset({
    "your_username_here",
    "your-soulseek-username",
    "your_soulseek_username",
})
_PLACEHOLDER_PASSWORDS = frozenset({
    "your_soulseek_password",
    "your_password_here",
    "",
})


def _has_valid_creds(config_file: Path) -> bool:
    """Returns True if *config_file* contains non-placeholder Soulseek credentials."""
    if not config_file.exists():
        return False
    try:
        username = ""
        password = ""
        for raw_line in config_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().lower()
            v = v.strip()
            if k == "username":
                username = v
            elif k == "password":
                password = v
        return bool(
            username and username not in _PLACEHOLDER_NAMES
            and password and password not in _PLACEHOLDER_PASSWORDS
        )
    except Exception:
        return False


def ensure_soulseek_config():
    """Ensures a valid Soulseek config exists with real credentials.

    Checks all platform-appropriate config locations (including both the Linux
    path and the Windows APPDATA path when running under WSL).  Only prompts
    for credentials if *none* of the candidate files contain valid,
    non-placeholder values.  New credentials are always written to the primary
    OS-appropriate path.

      - Windows exe : %APPDATA%\\sockseek\\sockseek.conf
      - Linux/Mac   : ~/.config/sockseek/sockseek.conf
      - WSL (dev)   : checks both of the above
    """
    config_files = _all_sockseek_config_files()

    if any(_has_valid_creds(f) for f in config_files):
        return  # At least one location already has valid credentials

    primary_config = config_files[0]
    config_dir = primary_config.parent

    print(f"\n[🔑] \033[1mSoulseek Credentials Required\033[0m")
    print("To download tracks, SpotDLextended needs a Soulseek P2P account.")
    if len(config_files) > 1:
        checked = ", ".join(str(f) for f in config_files)
        print(f"  [ℹ️] Checked: {checked}")
    username = input("Enter your Soulseek username: ").strip()
    password = input("Enter your Soulseek password: ").strip()

    config_dir.mkdir(parents=True, exist_ok=True)
    primary_config.write_text(
        f"# Sockseek Configuration\n"
        f"username = {username}\n"
        f"password = {password}\n"
        f"output-dir = {_get_default_music_dir()}\n\n"
        f"# Optional: set preferred format\n"
        f"pref-format = mp3,flac\n"
        f"pref-length-tol = 3\n"
        f"length-tol = -1\n"
        f"pref-min-bitrate = 320\n"
        f"pref-max-samplerate = 48000\n\n"
        f"# Job engine optimization\n"
        f"concurrent-jobs = 5\n"
        f"concurrent-searches = 3\n",
        encoding='utf-8'
    )
    print(f"  [✓] Soulseek configuration saved to {primary_config}")

def get_settings():
    """Checks for existing settings; handles onboarding if missing."""
    ensure_soulseek_config()
    
    settings = load_settings()    
    needs_save = False
    
    if "api_endpoints" not in settings:
        settings["api_endpoints"] = DEFAULT_API_ENDPOINTS
        needs_save = True

    if "full_overwrite" not in settings:
        settings["full_overwrite"] = False
        needs_save = True

    if "playlist_only" not in settings:
        settings["playlist_only"] = False
        needs_save = True

    if "get_extended_mixes" not in settings:
        settings["get_extended_mixes"] = True
        needs_save = True
        
    if "download_dir" in settings:
        if needs_save:
            save_settings(settings)
        return settings

    # First-run Onboarding
    print(f"\n[👋] \033[1mWelcome to SpotDLextended!\033[0m")
    print(f"It looks like this is your first time running the tool.")
    print(f"The default download dir is \033[92m\"{FALLBACK_DEFAULT_DIR}\"\033[0m.")
    
    choice = input("\nWould you like to keep the default or update to a custom path? [Default / Update]: ").strip().lower()
    
    if choice in ["update", "u", "new", "n"]:
        new_path = input("Enter your preferred music root directory: ").strip()
        if new_path:
            settings["download_dir"] = new_path
            save_settings(settings)
            print(f"  [✓] Default path updated to: {new_path}")
            return settings
            
    # Defaulting
    settings["download_dir"] = FALLBACK_DEFAULT_DIR
    settings["api_endpoints"] = DEFAULT_API_ENDPOINTS
    save_settings(settings)
    print(f"  [✓] Kept default path: {FALLBACK_DEFAULT_DIR}")
    return settings
