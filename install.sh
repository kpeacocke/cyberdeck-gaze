#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 -c 'import tkinter, picamera2, cv2, smbus2; from PIL import ImageTk'
mkdir -p "$HOME/.config/cyberdeck-gaze" "$HOME/.local/share/applications" "$HOME/.config/autostart" "$HOME/.config/systemd/user"
if [ ! -f "$HOME/.config/cyberdeck-gaze/config.json" ]; then
    cp config.json "$HOME/.config/cyberdeck-gaze/config.json"
fi
cat > "$HOME/.config/systemd/user/cyberdeck-gaze.service" <<UNIT
[Unit]
Description=Cyberdeck Gaze local vision desktop
StartLimitIntervalSec=120
StartLimitBurst=5
[Service]
Type=simple
WorkingDirectory=$PWD
ExecStart=/usr/bin/python3 -m gaze.app
Restart=on-failure
RestartSec=5
TimeoutStopSec=10
UMask=0077
UNIT
cat > "$HOME/.local/share/applications/cyberdeck-gaze.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Cyberdeck Gaze
Comment=Local AI Camera tracking and attention
Exec="$PWD/launch.sh"
Path=$PWD
Terminal=false
Categories=Video;Science;
Icon=camera-web
DESKTOP
if [ -w "$HOME/.config/autostart" ]; then
    cp "$HOME/.local/share/applications/cyberdeck-gaze.desktop" "$HOME/.config/autostart/cyberdeck-gaze.desktop"
else
    sudo install -m 644 -o "$(id -un)" -g "$(id -gn)" "$HOME/.local/share/applications/cyberdeck-gaze.desktop" "$HOME/.config/autostart/cyberdeck-gaze.desktop"
fi
systemctl --user daemon-reload
printf 'Installed desktop launcher and login autostart. Closing Gaze keeps it closed until relaunched.\n'
