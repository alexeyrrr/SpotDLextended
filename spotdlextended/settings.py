import os
import sys
import json
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

def ensure_soulseek_config():
    """Ensures Soulseek config exists and is populated."""
    config_dir = Path("~/.config/sockseek").expanduser()
    config_file = config_dir / "sockseek.conf"
    
    has_creds = False
    if config_file.exists():
        try:
            content = config_file.read_text(encoding='utf-8')
            username = ""
            password = ""
            for line in content.splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    k = k.strip().lower()
                    v = v.strip()
                    if k == "username":
                        username = v
                    elif k == "password":
                        password = v
            if username and username not in ["your_username_here", "your-soulseek-username"] and password:
                has_creds = True
        except Exception:
            pass
            
    if not has_creds:
        print(f"\n[🔑] \033[1mSoulseek Credentials Required\033[0m")
        print("To download tracks, SpotDLextended needs a Soulseek P2P account.")
        username = input("Enter your Soulseek username: ").strip()
        password = input("Enter your Soulseek password: ").strip()
        
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            f"# Sockseek Configuration\n"
            f"username = {username}\n"
            f"password = {password}\n"
            f"output-dir = {str(Path('~/Music').expanduser())}\n\n"
            f"pref-format = mp3,flac\n"
            f"pref-length-tol = 3\n"
            f"pref-min-bitrate = 320\n"
            f"pref-max-samplerate = 48000\n",
            encoding='utf-8'
        )
        print(f"  [✓] Soulseek configuration saved to {config_file}")

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
