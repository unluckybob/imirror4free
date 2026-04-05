# IMIRROR4FREE 🪞

**The definitive free iPhone USB screen mirroring tool for Windows.**

Full native resolution • Low latency • GPU-accelerated rendering • Zero watermarks

---

## 🎯 What is this?

IMIRROR4FREE mirrors your iPhone screen to your Windows PC over USB with the highest possible quality.
No subscriptions, no paywalls, no bullshit — just pure, sharp, real-time mirroring.

## ✨ Features

- **Full native resolution** — 2556×1179 on iPhone 14 Pro, up to 2868×1320 on iPhone 15 Pro Max
- **Low latency** — GPU-accelerated H.264 decode + OpenGL rendering pipeline
- **Audio passthrough** — hear your iPhone through your PC speakers
- **Auto device detection** — plug in your iPhone and go
- **Dark Windows 11 UI** — clean, minimal, stays out of your way
- **Fullscreen mode** — press F11 or double-click
- **FPS overlay** — real-time performance stats (toggle with F3)

## 🏗️ Architecture

```
iPhone (USB) → Valeria Protocol → H.264 Video Stream
                                        ↓
                              FFmpeg Hardware Decode (DXVA2)
                                        ↓
                              OpenGL GPU Texture Upload
                                        ↓
                              PyQt6 Render Window (VSync)
```

### Capture Backends

| Backend | FPS | Quality | Status |
|---------|-----|---------|--------|
| `ScreenshotCapture` | ~10-15 | Full res PNG | ✅ Phase 1 (working) |
| `ValeriaStreamCapture` | 30-60 | Full res H.264 | 🔧 Phase 2 (in development) |

The app auto-selects the best available backend.

## 📋 Prerequisites

- **Windows 10/11** (64-bit)
- **iTunes** installed from Microsoft Store ([link](https://apps.microsoft.com/detail/9pb2mz1zmb1s))
- **iPhone** with iOS 14+ connected via USB cable
- **Trust** the computer on your iPhone when prompted

## 🚀 Quick Start

### From Source

```bash
# Clone the repo
git clone https://github.com/unluckybob/IMIRROR4FREE.git
cd IMIRROR4FREE

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run
python -m imirror
```

### From Release (.exe)

Download the latest release from the [Releases](https://github.com/unluckybob/IMIRROR4FREE/releases) page.
Double-click `IMIRROR4FREE.exe` — no installation required.

## ⌨️ Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `F11` | Toggle fullscreen |
| `F3` | Toggle FPS overlay |
| `Escape` | Exit fullscreen / Quit |
| `Ctrl+Q` | Quit |

## 🛠️ Development

### Project Structure

```
IMIRROR4FREE/
├── imirror/
│   ├── main.py                 # Entry point
│   ├── config.py               # App configuration
│   ├── usb/
│   │   ├── device_manager.py   # Device detection (pymobiledevice3)
│   │   ├── valeria.py          # Valeria protocol implementation
│   │   └── packets.py          # Protocol packet codec
│   ├── capture/
│   │   ├── base.py             # Abstract capture backend
│   │   ├── screenshot.py       # Screenshot-based capture (Phase 1)
│   │   └── stream.py           # H.264 stream capture (Phase 2)
│   ├── decode/
│   │   ├── video.py            # Hardware-accelerated H.264 decode
│   │   └── audio.py            # Audio playback (Phase 2)
│   ├── render/
│   │   ├── gl_renderer.py      # OpenGL zero-copy renderer
│   │   └── shaders.py          # GLSL shader programs
│   └── gui/
│       ├── main_window.py      # Main application window
│       ├── overlay.py          # FPS/status overlay
│       └── styles.py           # Windows 11 dark theme
├── assets/
│   └── icon.ico
├── build/
│   └── build_exe.py            # PyInstaller packaging
├── requirements.txt
└── setup.py
```

### Tech Stack

- **pymobiledevice3** — Apple USB protocol handling (device detection, pairing, DVT services)
- **pyusb** — Raw USB access for Valeria protocol (Phase 2)
- **PyAV (FFmpeg)** — Hardware-accelerated H.264/HEVC decode via DXVA2
- **PyQt6** — Application framework
- **PyOpenGL** — GPU-accelerated rendering
- **NumPy** — Fast frame buffer operations

## 📜 License

MIT License — do whatever you want with this.

## 🙏 Credits

Built on the shoulders of:
- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) by doronz88
- [quicktime_video_hack](https://github.com/danielpaulus/quicktime_video_hack) by danielpaulus (Valeria protocol documentation)
- The open-source iOS reverse engineering community

---

**IMIRROR4FREE** — because screen mirroring should be free. 🪞
