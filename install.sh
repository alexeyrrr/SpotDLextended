#!/bin/bash

# 1. Define the directory
INSTALL_DIR="$HOME/.local/bin"
mkdir -p "$INSTALL_DIR"

# 2. Download the latest release
# Note: Copy the "Copy link address" from the 'sockseek_3.0.4_linux-x64.tar.gz' 
# link on the GitHub page and replace the URL below
FILE_URL="https://github.com/fiso64/sockseek/releases/download/v3.0.4/sockseek_3.0.4_linux-x64.tar.gz"
OUTPUT_FILE="sockseek.tar.gz"

echo "Downloading..."
curl -L -o "$OUTPUT_FILE" "$FILE_URL"

# 3. Extract the tarball
# -x: extract, -z: gzip, -f: file
echo "Extracting..."
tar -xzf "$OUTPUT_FILE" -C "$INSTALL_DIR"

# 4. Clean up
rm "$OUTPUT_FILE"

# 5. Make it executable
chmod +x "$INSTALL_DIR/sockseek"

echo "Success! sockseek is installed in $INSTALL_DIR"

# Generate blank config file
# Define the config directory
CONFIG_DIR="$HOME/.config/sockseek"
CONFIG_FILE="$CONFIG_DIR/sockseek.conf"

# Create the directory if it doesn't exist
mkdir -p "$CONFIG_DIR"

# Create config file if it doesn't exist
if [ ! -f "$CONFIG_FILE" ]; then
    # Using printf to ensure clean, simple key=value format
    printf "username=your_username_here\npassword=your_password_here\noutput-dir=%s/Music\n" "$HOME" > "$CONFIG_FILE"
    echo "Created default config file at $CONFIG_FILE"
else
    echo "Config file already exists, skipping creation."
fi