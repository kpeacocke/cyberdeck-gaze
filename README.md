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
  enabled on this cyberdeck after observed axis-direction tests.

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
`0x40`, tilt channel 0, pan channel 1. The user reconnected the controller power lead on physical pin 4 on 13 September
2026. Bus 1 address `0x40` then acknowledged reads with PCA9685 default registers
(MODE1 `0x11`, MODE2 `0x04`, SUBADR1–3 `0xe2/0xe4/0xe8`, ALLCALL `0xe0`).
A centre / pan +4° / centre / tilt +4° / centre command sequence completed, and
both channel PWM registers read back correctly. The user subsequently confirmed physical movement: positive pan turns right and
positive tilt moves up, viewed from the camera. Tracking uses pan sign +1 and
tilt sign -1 (image Y increases downward). Full mechanical travel remains unmeasured.
Established wiring: 5V physical pin 4, GND pin 9, SDA pin 3/GPIO2, SCL pin 5/GPIO3.

For another assembly, disable `motor.enabled` until you verify supply,
I²C address, channel assignment, axis signs, pulse limits and mechanical travel.
PCA9685 drives ordinary open-loop servos: commanded angle is not measured position.
The first command can move a servo from its unknown physical position. Do not
assume software speed limiting limits that initial physical movement.

Explore uses four bounded viewpoints when no tracks remain. Park requests the
centre within configured limits and keeps detection active. Movement is active in the deployed configuration, with conservative 80–100°
bounds on both axes. Click a subject to follow it; Explore switches attention
and scans when no subjects remain. Park returns to centre. The Motors panel
provides release and manual jog controls; Explore/Park or selecting a subject
re-arms automatic motion after manual release.

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

### Manual motor controls

Open **Motors** to pause automatic movement and test the controller. **Arm / retry**
requires a responding address and refuses kernel-owned devices. The first jog
commands a position near 90°; verify the assembly can reach centre first.
Pan/tilt ±2° buttons command bounded, rate-limited movement. **Stop / release**
disables both servo outputs. Closing the motor panel also releases them.
Motor I/O failure leaves the live camera running. Successful I²C communication
still does not prove motor power, direction or physical movement.

Runtime status is written atomically to `runtime.json` in the configured storage
directory. It records the last frame time, mode, target ID and commanded angles;
these angles are software commands, not servo position feedback.
