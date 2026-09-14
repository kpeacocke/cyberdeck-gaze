# Cyberdeck Gaze

A native desktop application on the Raspberry Pi: live IMX500 detection,
short-lived subject tracking, attention switching and local sighting storage.
One Python application, no cloud service, no external desktop dependency.

## Current release: 0.3.0

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

**Save with name** labels a photo. **Enrol friend / pet** creates a recognition
reference. Local face recognition uses YuNet detection/alignment and SFace
embeddings; pet matching compares local visual features and is always presented
as an experimental **Possible** match. These are separate from short-term track IDs.
General scene-change understanding and gesture recognition remain future work.
Brief loss recovery revisits the last commanded viewpoint; it is not a room map.
Tracks are short-term geometric associations and can switch identity when similar
subjects cross. Object detector labels can also be wrong, especially with an
obscured or sideways camera. No emotion or threat inference is performed.

## Install on the Pi

```sh
sudo apt-get install python3-picamera2 python3-tk python3-pil.imagetk python3-opencv python3-smbus2 imx500-models
python3 setup-models.py
./install.sh
./launch.sh
```

Launch **Cyberdeck Gaze** from the desktop application menu. The launcher runs from
the installation directory; do not move that directory without rerunning install.sh.
This does not change the existing e-paper application or boot configuration.
Closing the window stops capture and leaves the app closed. A desktop-login
autostart entry launches it next session; a persistent user service restarts
crashes. Capture failures retry after three seconds. Startup requires a logged-in
graphical desktop, not merely a headless boot.

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

## Attention and short-term memory

Version 0.2 adds predicted-position, size-aware one-to-one association, background
optical-flow compensation excluding subject boxes, and an interest score composed
of detector confidence, preferred class, novelty and residual movement. Minimum
dwell and a score margin resist rapid target switching; timed cooldown encourages
looking elsewhere. Motion scoring is suppressed during commanded camera movement
and settling, or when background flow cannot be estimated reliably.

The desktop shows the current reason, remaining dwell and top three candidates.
Lost targets retain their track briefly and the camera revisits their last viewing
direction. Expired tracks remain in bounded two-minute session memory. This memory
is not restored as identity across application restarts. Appeared, moving, stopped,
reacquired, selected and left-view events are stored in NVMe SQLite, capped at 1000
rows and subject to the unknown retention setting. No emotion labels are inferred.

Limitations: translation-only background compensation cannot fully model rotation,
parallax or a scene dominated by moving subjects. Geometric tracking can still
swap IDs at crossings. Detector jitter can create false arrival/movement events;
these are observations to tune, not guaranteed real-world activity classifications.

## Enrolment and recognition

Select a clear person, dog or cat sighting and press **Enrol friend / pet**. Reuse
the same name to add views. People need exactly one face, at least 40 pixels wide
and high, with sufficient sharpness. Live matches require two consecutive accepted
comparisons. Face cosine similarity must exceed 0.5 with a 0.08 lead over another
identity by default; scores are similarity values, not calibrated probabilities.
Names disappear on rejected comparisons. There is no guarantee against ID swaps.

Pet matching is experimental ORB detail plus colour-histogram comparison, not a
trained individual-animal recognizer. It can match the background or confuse similar
animals. Enrol several clear views; treat **Possible NAME** as a suggestion to check.
No breeds, emotions or threat levels are inferred from these comparisons.

**Known subjects / forget** deletes all recognition references for a chosen name.
Saved sighting photos are separately deletable. References live in
`known-subjects.json` under configured NVMe storage with owner-only permissions;
unknown embeddings stay in memory and are not added to the gallery. A 200-example
cap bounds the gallery. Models live separately in `/mnt/nvme/models/cyberdeck-gaze`.
No sightings, identity names or embeddings are committed to GitHub.

Recognition runs in a bounded background queue, round-robin across visible people
and pets. The camera remains IMX500-driven; face/pet comparison uses the Pi CPU.
Face model smoke tests used a public OpenCV fixture, not the user's people. Real
friend/pet recognition accuracy must be evaluated using their enrolled examples.

## Calibration, viewpoints and sighting quality

**Motors → Calibrate limits / directions** supports trial changes of at most 5°
per bound. Apply a trial, jog in the motor window, observe travel and cable slack,
then save observed limits. Cancel discards trial limits. Existing defaults remain
80–100° until an operator confirms wider travel; open-loop PWM cannot sense stops.

**Viewpoints → Save current direction** records a name and commanded angles.
**Look at selection** holds that direction; Explore resumes attention and revisits
saved viewpoints when there is no chosen subject. Positions outside current limits
are rejected. Storage is local `viewpoints.json`, capped at 30 entries.

Sighting capture now chooses the highest sharpness-times-confidence crop from a
short observation window instead of blindly taking its first frame. It retains
at most 30 pending crops, saves no more often than every 30 seconds per track,
and uses up to 640×480 pixels for better enrolment detail.

## Validation and model provenance

Automated tests cover motion-compensated association, crossing trajectories,
closed-loop centring in a simulated scene, occlusion, dwell/cooldown policy,
recognition ambiguity/abstention, deletion, persistence, calibration bounds,
viewpoints and storage retention. Synthetic tests are not physical calibration.

Recognition model sources and their own licence terms:
- [YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)
- [SFace](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface)
- [OpenCV face recognition API](https://docs.opencv.org/4.10.0/d0/dd4/tutorial_dnn_face.html)

`setup-models.py` checks pinned SHA-256 digests before installing model downloads.
