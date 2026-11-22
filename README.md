# ✋ Hey Handy

**Say `"Hey Handy"`, then control your video or audio with simple hand gestures — built for watching and listening while eating.**

[![CI](https://github.com/ahmedtarek26/hey-handy/actions/workflows/ci.yml/badge.svg)](https://github.com/ahmedtarek26/hey-handy/actions/workflows/ci.yml)
![Python 3.10–3.12](https://img.shields.io/badge/python-3.10--3.12-2dd4bf)
![License: MIT](https://img.shields.io/badge/license-MIT-blue)
![Platform: Linux | macOS | Windows](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-slate)

Most open-source webcam gesture apps trigger constantly while you eat (mistaking a fork, sandwich, or cup near your face for a gesture), leave your webcam running 24/7, clutter your screen with an OpenCV preview window, and send brittle keyboard shortcuts (`Space` / `F`) that scroll the page or miss audio tabs.

**Hey Handy** solves all of that:

![Hey Handy Settings](docs/screenshot.png)

---

## ✨ Key Features

- **Offline `"Hey Handy"` Wake Word (`sherpa-onnx`)**: Your webcam stays **off** while you eat (webcam LED off, zero false triggers). Say **"Hey Handy"** softly in your normal voice and the camera wakes for an **8-second window** (automatically extending while you adjust volume), then goes right back to sleep.
- **Smart Soft-Voice Mic Pipeline**: Automatically bypasses silent/over-gated virtual noise filters (like PipeWire `rnnoise_source`) when a cleaner hardware mic is available, and uses fast RMS gain normalization so you never have to shout.
- **Works on Your Active Browser Tab *and* Local Desktop Players**:
  - **Out of the box**: Controls browsers (`Zen`, `Firefox`, `Chrome`, `Brave`) and local media apps (`VLC`, `mpv`, `Celluloid`, `Spotify`) via MPRIS + compositor/OS media & volume controls.
  - **With the Browser Extension**: Targets `<video>` and `<audio>` directly inside whichever tab you're actively in (including Shadow DOM and iframes), adds cinema fullscreen on any HTML5 player, and renders an isolated in-fullscreen HUD pill.
- **Pause & Resume Keep Your Place**: Pausing stops playback right at your current timestamp; resuming continues from the exact second you stopped.
- **Anti-False-Trigger Gesture Engine**: Combines MediaPipe `GestureRecognizer`, 21-landmark geometric fallbacks for dim evening rooms, hand bounding-box size checks, multi-frame stability consensus (`3` frames), and action cooldowns.
- **Customizable Window & No-Clutter Tray Mode**: Switch between **Small** (`500×680`, single-column), **Standard** (`980×880`), or **Full** window presets, or minimize quietly to the system tray with only a small translucent HUD pill.

---

## 🍽️ How to Use It While Eating

1. **Start Hey Handy** (minimize to the system tray once configured — no webcam preview window stays on screen).
2. **Eat normally**: The webcam is **off** and eating motions will never pause or mute your media.
3. **Say `"Hey Handy"`** in your normal speaking voice:
   - You'll hear a soft chime (toggleable) and see a small **ARMED (8s)** corner pill as the webcam turns on.
4. **Hold one hand gesture for ~100 ms**:

| Gesture | Default Action | What It Does |
| --- | --- | --- |
| ✋ **Open Palm** | **Play / Pause** | Pauses playback at your exact timestamp; show again to resume |
| ✊ **Closed Fist** | **Pause (Stop)** | Dedicated pause — stops playback without accidentally resuming |
| ✌️ **Peace / Victory** | **Toggle Fullscreen** | Enters/exits fullscreen on your active video player or browser tab |
| 👍 **Thumbs Up** | **Volume Up** | Smoothly steps volume up while held and keeps the wake window open |
| 👎 **Thumbs Down** | **Volume Down** | Smoothly steps volume down while held and keeps the wake window open |
| ☝️ **Pointing Up** | **Mute / Unmute** | Mutes or unmutes audio immediately |

> Every gesture can be remapped (`Play/Pause`, `Pause`, `Resume`, `Fullscreen`, `Volume Up`, `Volume Down`, `Mute`, `Dismiss Handy`, or `Disabled`) in **Settings**.

---

## 🚀 Installation & Setup

### Prerequisites

- A webcam and microphone
- [uv](https://docs.astral.sh/uv/) (automatically fetches Python 3.12 and all dependencies on Linux, macOS, and Windows)

### 1. Clone & Launch the Desktop App

```bash
git clone https://github.com/ahmedtarek26/hey-handy.git
cd hey-handy
uv sync --python 3.12
uv run hey-handy --settings
```

On first launch, Hey Handy downloads two compact offline models (~23 MB total) into your user data directory:
- **Linux**: `~/.local/share/hey-handy/models`
- **macOS**: `~/Library/Application Support/hey-handy/models`
- **Windows**: `%LOCALAPPDATA%\hey-handy\models`

You can also pre-download them at any time:

```bash
uv run hey-handy --download-models
```

### 2. (Optional, Recommended) Install the Browser Extension

Hey Handy already works across browsers and local players (`VLC`, `mpv`, `Spotify`) via OS/MPRIS controls. Installing the unified Manifest V3 extension from [`extension/`](extension) unlocks direct per-tab `<video>`/`<audio>` control on any website plus an in-video fullscreen HUD:

- **Chrome / Chromium / Brave / Edge**:
  1. Open `chrome://extensions` and enable **Developer mode**.
  2. Click **Load unpacked** and select the [`extension/`](extension) folder.
- **Firefox / Zen Browser / LibreWolf**:
  1. Open `about:debugging#/runtime/this-firefox`.
  2. Click **Load Temporary Add-on...** and select [`extension/manifest.json`](extension/manifest.json).

The extension automatically connects to the desktop app at `ws://127.0.0.1:17421`.

---

## ⚙️ Settings & Window Modes

- **Window Size Presets**: Use the top-right **Small** (`500×680`), **Standard** (`980×880`), and **Full** buttons (or drag any window border — the layout adapts automatically between 1-column and 2-column views and remembers your size).
- **Camera & Gesture Tester**: Check **Enable live camera test preview** to verify framing, see the 21-landmark skeleton, and test live gesture actions before hiding the window to the tray.
- **Wake Sensitivity (`72%` default)**: Increase toward `100%` for very soft voices, or lower in noisy rooms. Watch the live **Mic level** bar to verify input.
- **Volume Target**: Choose **System Volume** (works across all tabs and apps), **Active Browser Tab Volume**, or **Active Tab + System**.
- **Keep Camera Warm**: Keeps slow USB webcams initialized between wakes while still disabling gesture triggers until `"Hey Handy"` is spoken.

---

## 💻 CLI Options

```text
hey-handy --settings         Open the Settings & Live Camera Test window
hey-handy --always-on        Keep gesture recognition active without wake word
hey-handy --no-tray          Show Settings window and exit when closed
hey-handy --download-models  Download offline ML models and exit
hey-handy --port 17421       Use a custom localhost WebSocket port
```

---

## 🏗️ Architecture

```text
Microphone ──▶ Fast RMS AGC + sherpa-onnx KWS ("Hey Handy")
                      │
                      ▼  wakes for 8s (webcam turns on)
Webcam ──────▶ MediaPipe GestureRecognizer + Landmark Geometry Guards
                      │
                      ▼  localhost WebSocket (ws://127.0.0.1:17421)
Browser Extension (Chrome / Firefox / Zen MV3)
   ├── Active Tab <video> / <audio> + Shadow DOM / iframe targeting
   ├── Cinema Fullscreen + window state + In-Tab HUD Pill
   └── Fallback ─▶ OS Volume & Media (MPRIS / wpctl / Hyprland / macOS / Win32)
```

---

## 🧪 Running Tests

```bash
uv sync --python 3.12 --extra dev
QT_QPA_PLATFORM=offscreen uv run pytest -v
```

---

## 🛠️ Troubleshooting

- **Linux (Wayland / Hyprland / PipeWire)**:
  - Ensure `gdbus` and `wpctl` (or `pactl`) are installed; `mpv` works cleanly with `mpv-mpris`.
  - If your desktop routes mic audio through a virtual noise-suppression filter that gates quiet speech, leave **Microphone** on **Auto (best hardware mic)** or pick your hardware analog/USB mic directly in Settings.
- **macOS**: Grant **Microphone** and **Camera** permissions to your terminal / Python runtime in **System Settings → Privacy & Security**.
- **Windows**: Ensure microphone/camera privacy permissions are enabled for desktop apps in **Windows Settings → Privacy & security**.

---

## 🤝 Collaborations & Credits

- Built by [@ahmedtarek26](https://github.com/ahmedtarek26) in collaboration with **Gemini**.
- Powered by [MediaPipe](https://developers.google.com/mediapipe) (hand landmark & gesture recognition), [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) (offline streaming keyword spotting), and [PySide6](https://doc.qt.io/qtforpython-6/).

## 📄 License

MIT — see [LICENSE](LICENSE).
