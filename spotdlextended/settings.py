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

def get_settings():
    """Checks for existing settings; handles onboarding if missing."""
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
    save_settings(settings)
    print(f"  [✓] Kept default path: {FALLBACK_DEFAULT_DIR}")
    return settings
