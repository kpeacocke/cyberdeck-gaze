# Cyberdeck Gaze

A native desktop application on the Raspberry Pi: live IMX500 detection,
short-lived subject tracking, attention switching and local sighting storage.
One Python application, no cloud service, no external desktop dependency.

## Current release: 0.1.0

Implemented and exercised on KP-Pi5:

- Sony IMX500 object detection using its on-camera model and Picamera2.
- Tk desktop live view with detection boxes and click-to-follow target selection.
- Explore / Follow / Park attention modes, dwell time and subject cooldown.
- Brief retention of obscured tracks; no pursuit using stale positions.
- Recent thumbnails, manually named saved sightings, deletion and retention limits.
- Settings for storage directory, retention, image budget, dwell and confidence.
- NVMe default `/mnt/nvme/cyberdeck-gaze`; refuse SD fallback if that mount is missing.
- Exclusive app instance. Only the camera worker touches camera/motor hardware.
- PCA9685 motor adapter with speed limiting, centre deadband and bounded travel,
  disabled until the controller is connected and calibration is established.

**A name on a saved sighting is not identity recognition.** Automatic face/pet
recognition, learned places, scene-change detection, best-frame selection and
active search after losing a subject are not implemented in this first release.
Tracks are short-term geometric associations and can switch identity when similar
subjects cross. Object detector labels can also be wrong, especially with an
obscured or sideways camera. No emotion or threat inference is performed.

## Install on the Pi

```sh
sudo apt-get install python3-picamera2 python3-tk python3-pil.imagetk python3-opencv python3-smbus2 imx500-models
./install.sh
python3 -m gaze.app
```

Launch **Cyberdeck Gaze** from the desktop application menu. The launcher runs from
the installation directory; do not move that directory without rerunning install.sh.
This does not change the existing e-paper application or boot configuration.
Closing the window stops capture. Automatic boot launch is not enabled.

Config: `~/.config/cyberdeck-gaze/config.json`. Settings changes apply on restart;
changing storage location does not migrate existing data. Unknown images and rows
expire after 24 hours by default. Named sightings persist until deleted. The image
budget is 512 MiB, pruning oldest unknowns first; saved images are not silently
removed. This budget covers JPEG data, not filesystem/database overhead. Retention
cleanup runs on startup, new saves, and once a minute during normal capture.

## Camera and motor

Verified camera: IMX500, 960×720 preview, SSD MobileNet model from
`/usr/share/imx500-models`. The app currently supports this specific postprocessed
model output layout. Other model paths require checking output decoding first.

The installed Arducam sample at `/home/kpeacocke/pca9685` uses bus 1, address
`0x40`, tilt channel 0, pan channel 1. Those are sample assignments; the controller
did not acknowledge a read on 13 September 2026. This does not establish why.
No motor movement has been verified. Default travel bounds are provisional.

Before setting both `motor.enabled` and `motor.calibrated` to true, verify supply,
I²C address, channel assignment, axis signs, pulse limits and mechanical travel.
PCA9685 drives ordinary open-loop servos: commanded angle is not measured position.
The first command can move a servo from its unknown physical position. Do not
assume software speed limiting limits that initial physical movement.

Explore uses four bounded viewpoints when no tracks remain. Park requests the
centre within configured limits and keeps detection active. Movement is inactive
in the deployed configuration pending actual hardware calibration.

## Development

```sh
python3 -m unittest discover -s tests -v
```

Modules: `hardware.py` (camera/motor), `core.py` (tracking/attention), `storage.py`
(SQLite/thumbnails), `app.py` (native UI). Unit tests cover tracking selection,
cooldowns, stale targets and data retention; they do not prove motor calibration.

Hardware/API references:
- https://www.raspberrypi.com/documentation/accessories/ai-camera.html
- https://github.com/ArduCAM/PCA9685
