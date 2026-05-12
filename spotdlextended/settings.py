import os
import sys
import json
import requests
import logging
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

def fetch_dynamic_endpoints():
    """Fetches the latest active endpoints from the uptime monitor."""
    endpoints = []
    try:
        response = requests.get("https://tidal-uptime.geeked.wtf/", timeout=5)
        response.raise_for_status()
        data = response.json()
        
        # 'api' and 'streaming' arrays contain the active, valid endpoints
        for category in ["api", "streaming"]:
            if category in data:
                for item in data[category]:
                    url = item.get("url")
                    if url:
                        # Strip trailing slashes to keep format consistent
                        endpoints.append(url.rstrip('/'))
                        
        # Deduplicate while preserving order
        unique_endpoints = []
        for ep in endpoints:
            if ep not in unique_endpoints:
                unique_endpoints.append(ep)
                
        return unique_endpoints
    except Exception as e:
        logging.warning(f"  [⚠️] Could not fetch dynamic endpoints: {e}")
        return []

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
    
    # Always fetch the latest dynamic endpoints at runtime
    dynamic_endpoints = fetch_dynamic_endpoints()
    
    if "api_endpoints" not in settings or not settings["api_endpoints"]:
        # Seed with defaults if empty, but we won't necessarily use only these
        settings["api_endpoints"] = DEFAULT_API_ENDPOINTS
        needs_save = True

    # Combine dynamic endpoints with whatever is in the settings (or defaults)
    # This prioritizes the newly fetched ones, and keeps hardcoded/saved ones as a backup
    combined_endpoints = list(dynamic_endpoints)
    for ep in settings.get("api_endpoints", []):
        if ep not in combined_endpoints:
            combined_endpoints.append(ep)
            
    # Assign the combined list for this session (not saved back to the file unless it was missing)
    # This ensures if a custom URL was saved, it's appended at the end.
    session_settings = settings.copy()
    session_settings["api_endpoints"] = combined_endpoints

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
        return session_settings

    # First-run Onboarding
    print(f"\n[👋] \033[1mWelcome to SpotDLextended!\033[0m")
    print(f"It looks like this is your first time running the tool.")
    print(f"The default download dir is \033[92m\"{FALLBACK_DEFAULT_DIR}\"\033[0m.")
    
    choice = input("\nWould you like to keep the default or update to a custom path? [Default / Update]: ").strip().lower()
    
    if choice in ["update", "u", "new", "n"]:
        new_path = input("Enter your preferred music root directory: ").strip()
        if new_path:
            settings["download_dir"] = new_path
            session_settings["download_dir"] = new_path
            save_settings(settings)
            print(f"  [✓] Default path updated to: {new_path}")
            return session_settings
            
    # Defaulting
    settings["download_dir"] = FALLBACK_DEFAULT_DIR
    session_settings["download_dir"] = FALLBACK_DEFAULT_DIR
    save_settings(settings)
    print(f"  [✓] Kept default path: {FALLBACK_DEFAULT_DIR}")
    return session_settings
