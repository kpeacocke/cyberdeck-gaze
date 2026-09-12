#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -c 'import tkinter, picamera2, cv2, smbus2; from PIL import ImageTk'
mkdir -p "$HOME/.config/cyberdeck-gaze" "$HOME/.local/share/applications"
if [ ! -f "$HOME/.config/cyberdeck-gaze/config.json" ]; then
    cp config.json "$HOME/.config/cyberdeck-gaze/config.json"
fi
cat > "$HOME/.local/share/applications/cyberdeck-gaze.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Cyberdeck Gaze
Comment=Local AI Camera tracking and attention
Exec=python3 -m gaze.app
Path=$PWD
Terminal=false
Categories=Video;Science;
Icon=camera-web
DESKTOP
printf 'Installed desktop launcher. Storage defaults to /mnt/nvme/cyberdeck-gaze.\n'
