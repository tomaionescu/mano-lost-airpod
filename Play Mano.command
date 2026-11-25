#!/bin/bash
# Launch "Mano & the Lost AirPod" (Godot 4.7). Double-click in Finder.
cd "$(dirname "$0")"
GODOT="$HOME/Applications/godot/Godot.app/Contents/MacOS/Godot"
if [ ! -x "$GODOT" ]; then
  echo "Godot 4.7.2 not found at $GODOT"
  echo "Download it from https://godotengine.org/download (macOS) and put Godot.app in ~/Applications/godot/"
  read -n 1 -s -r -p "Press any key to close"
  exit 1
fi
# first launch imports the assets (a few minutes); later launches start in seconds
if [ ! -d ".godot/imported" ]; then
  echo "First launch: importing assets, this takes a few minutes..."
  "$GODOT" --headless --path . --import > /dev/null 2>&1
fi
exec "$GODOT" --path . "$@"
