import asyncio
import json
import os
from aioslsk.client import SoulSeekClient
from aioslsk.settings import Settings

# 1. Define the path to your config file
config_path = os.path.expanduser("~/.config/sockseek/config.json")

# 2. Load the settings from the JSON file
with open(config_path, 'r') as f:
    config_data = json.load(f)

# 3. Initialize settings by unpacking the dictionary
# This maps the JSON structure directly to the Settings Pydantic model
settings = Settings(**config_data)

async def perform_search(query: str):
    # The client handles the connection to the SoulSeek network
    async with SoulSeekClient(settings) as client:
        await client.login()
        
        print(f"Searching for: {query}")
        
        # Start a network search request
        search_request = await client.searches.search(query)
        
        # Wait a short period to allow results to arrive from the network
        await asyncio.sleep(5)
        
        # Access the results
        print(f"Found {len(search_request.results)} results.")
        for result in search_request.results:
            # Safely access the first shared item if it exists
            if result.shared_items:
                print(f"User: {result.username} | File: {result.shared_items[0].filename}")

# Example usage:
artist = "Artist Name"
track = "Track Name"
query = f"{artist} {track}"

asyncio.run(perform_search(query))