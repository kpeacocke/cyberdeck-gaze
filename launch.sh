#!/bin/sh
set -eu
systemctl --user import-environment DISPLAY XAUTHORITY WAYLAND_DISPLAY XDG_RUNTIME_DIR
systemctl --user reset-failed cyberdeck-gaze.service 2>/dev/null || true
systemctl --user start cyberdeck-gaze.service
