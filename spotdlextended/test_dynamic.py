import sys
from pathlib import Path
import logging

# Ensure the spotdlextended package can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import settings

logging.basicConfig(level=logging.INFO)

def test_dynamic_endpoints():
    s = settings.get_settings()
    print("API Endpoints loaded:")
    for i, ep in enumerate(s.get("api_endpoints", [])):
        print(f"  {i+1}: {ep}")

if __name__ == "__main__":
    test_dynamic_endpoints()
