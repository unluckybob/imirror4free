# MIRROR4FREE <img src="assets/icon.png" width="32" alt="Mirror4Free">

**The definitive free iPhone USB screen mirroring tool for Windows.**

Full native resolution • Low latency • GPU-accelerated • No watermarks • No subscriptions

---

## 🎯 What is this?

MIRROR4FREE mirrors your iPhone screen to your Windows PC over USB — for free. It uses Apple's Valeria protocol (the same technology behind QuickTime) to stream your iPhone's HEVC video directly over USB at up to 60 FPS.

**No companion app on iPhone.** No WiFi. No cloud. Just plug in your USB cable and go.

## ✨ Features

| Feature | Details |
|---------|---------|
| 📺 **Full native resolution** | Up to 2868×1320 (iPhone 15 Pro Max) |
| ⚡ **Low latency** | Direct HEVC stream over USB, GPU-accelerated decode |
| 🔊 **Audio passthrough** | iPhone audio plays through your PC speakers |
| 🎬 **Screen recording** | Record to MP4/MKV with zero quality loss (direct mux) |
| 📸 **Screenshots** | PNG/JPEG capture with one click or Ctrl+S |
| 🔌 **Plug and play** | One-time driver install, then just plug in and go |
| 🎨 **Dark Windows 11 UI** | Clean, minimal, modern dark theme |
| ⚙ **Settings panel** | Configure decoder, audio, recording, and UI options |
| 📊 **FPS overlay** | Real-time performance stats (F3 to toggle) |
| 🖥️ **Fullscreen mode** | F11 or double-click to go fullscreen |
| 🔧 **CLI tools** | Driver install, diagnostics, and more from command line |

## 🏗️ How it Works

```
iPhone (USB)
    │
    ├─── Apple's Valeria Protocol (USB Configuration 5)
    │         │
    │    USB Bulk Transfer (H.264 + LPCM Audio)
    │         │
    ├─── libusb-win32 Driver (one-time install, replaces Apple's driver on Interface 2)
    │         │
    │    MIRROR4FREE
    │    ├── Valeria Protocol Handler (handshake, FEED/EAT!/NEED packets)
    │    ├── H.264 Decoder (D3D11VA/DXVA2 GPU or FFmpeg software)
    │    ├── PCM Audio Player (48kHz stereo via sounddevice)
    │    ├── Screen Recorder (direct H.264 mux to MP4 — zero re-encode)
    │    └── PyQt6 GUI (dark theme, OpenGL rendering, FPS overlay)
    │
    └─── Your PC Screen 🖥️
```

### Capture Backends

| Backend | FPS | Method | When Used |
|---------|-----|--------|-----------|
| **Valeria Stream** | 30-60 | H.264 over USB | Default (after driver install) |
| **Screenshot** | ~10-15 | PNG screenshots via DVT | Fallback (no driver needed) |

The app auto-selects the best available backend.

## 📋 Prerequisites

- **Windows 10/11** (64-bit)
- **iTunes** installed from [Microsoft Store](https://apps.microsoft.com/detail/9pb2mz1zmb1s) or Apple's website
- **iPhone** with iOS 14+ connected via USB cable
- **Trust** the computer on your iPhone when prompted

## 🚀 Quick Start

### From Source

```bash
# Clone the repo
git clone https://github.com/unluckybob/mirror4free.git
cd mirror4free

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run
python -m imirror
```

### First-Time Setup: Install Mirror Driver

The Valeria stream backend requires a one-time driver installation:

**Option A: GUI** — Click "🔧 Install Mirror Driver" in the app when prompted

**Option B: CLI:**
```bash
python -m imirror --install-driver
```

After installing, unplug and replug your iPhone. The app will auto-detect and start streaming.

### From Release (.exe)

Download the latest release from the [Releases](https://github.com/unluckybob/mirror4free/releases) page.
Double-click `MIRROR4FREE.exe` — no installation required.

## ⌨️ Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `F11` | Toggle fullscreen |
| `F3` | Toggle FPS overlay |
| `Ctrl+S` | Take screenshot |
| `Ctrl+R` | Start/stop recording |
| `Ctrl+,` | Open settings |
| `Ctrl+Q` | Quit |
| `Escape` | Exit fullscreen / Quit |

## 🛠️ CLI Commands

```bash
# Launch the GUI
python -m imirror

# Force a specific capture backend
python -m imirror --backend valeria
python -m imirror --backend screenshot

# Driver management
python -m imirror --install-driver     # Install libusb-win32 mirror driver
python -m imirror --uninstall-driver   # Restore Apple's original driver
python -m imirror --check-driver       # Check driver status

# Diagnostics
python -m imirror --diag               # Full USB diagnostic

# Display options
python -m imirror --fps                # Show FPS overlay
python -m imirror --fullscreen         # Start fullscreen
python -m imirror --always-on-top      # Window stays on top
python -m imirror --verbose            # Debug logging
```

## 📂 Project Structure

```
mirror4free/
├── imirror/
│   ├── __init__.py               # Version, metadata
│   ├── main.py                   # Entry point + CLI
│   ├── config.py                 # All settings (persistent)
│   ├── usb/
│   │   ├── driver_installer.py   # libusb-win32 driver auto-installer
│   │   ├── driver_check.py       # Driver diagnostics
│   │   ├── device_manager.py     # iPhone detection (usbmuxd + pyusb)
│   │   ├── endpoint.py           # USB endpoint I/O + QT mode switch
│   │   ├── valeria.py            # Valeria protocol state machine
│   │   └── packets.py            # Protocol packet codec (AVCC → Annex B)
│   ├── capture/
│   │   ├── base.py               # Abstract capture backend
│   │   ├── stream.py             # Valeria H.264 stream capture
│   │   ├── screenshot.py         # Screenshot capture (fallback)
│   │   └── recording.py          # MP4/MKV recording + screenshots
│   ├── decode/
│   │   ├── video.py              # HW-accelerated H.264 decoder
│   │   └── audio.py              # Audio playback with ring buffer
│   └── gui/
│       ├── main_window.py        # Main window + settings dialog
│       ├── overlay.py            # FPS/status overlay
│       └── styles.py             # Windows 11 dark theme
├── build/
│   └── build_exe.py              # PyInstaller packaging
├── requirements.txt
└── README.md
```

## 🔧 Technical Details

### The Valeria Protocol

MIRROR4FREE uses Apple's proprietary Valeria protocol — the same protocol QuickTime uses to mirror iPhones over USB on macOS. Here's how it works:

1. **USB Configuration Switch**: Send a USB control transfer to switch the iPhone to Configuration 5, which exposes the QT AV interface (SubClass 0x2A)
2. **PING Handshake**: Exchange PING packets to establish the session
3. **SYNC Negotiations**: Handle CWPA (audio clock), AFMT (audio format), CVRP (video format + SPS/PPS), CLOK, TIME, SKEW
4. **Start Streaming**: Send HPD1 (start video) and HPA1 (start audio)
5. **Continuous Stream**: Receive FEED (H.264 in CMSampleBuffer) and EAT! (LPCM audio) packets
6. **NEED Flow**: Send NEED packets after each FEED to request more frames

### The Driver Problem (and Solution)

On Windows, Apple's USB driver claims the iPhone's Valeria interface exclusively. The solution is to install a libusb-win32 driver specifically for the Valeria interface (Interface 2, SubClass 0x2A), while letting Apple's driver keep the other interfaces for normal iPhone functionality.

Our `driver_installer.py` handles this automatically:
- Detects the iPhone via WMI
- Generates a libusb-win32 .inf targeting only the Valeria interface
- Installs via Windows `pnputil`
- Creates a backup for clean uninstall

### Recording

Recording works by muxing the raw H.264 stream directly into an MP4/MKV container — **zero re-encoding**. This means:
- Recording has zero CPU overhead
- Output quality is identical to the stream (no generation loss)
- Files are much smaller than screen capture recordings

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `pyusb` + `libusb-package` | Raw USB access for Valeria protocol |
| `pymobiledevice3` | iPhone detection, pairing, DVT services |
| `av` (PyAV/FFmpeg) | H.264 decode + recording mux |
| `PyQt6` | Application framework |
| `PyOpenGL` | GPU-accelerated rendering |
| `sounddevice` | Low-latency audio playback |
| `numpy` | Frame buffer operations |
| `Pillow` | Image processing (screenshots) |

## 📜 License

GPL-3.0 License — free as in freedom, free as in beer.

## 🙏 Credits

Built on the shoulders of:
- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) by doronz88
- [quicktime_video_hack](https://github.com/danielpaulus/quicktime_video_hack) by danielpaulus (Valeria protocol documentation)
- [libimobiledevice](https://github.com/libimobiledevice/libimobiledevice) community
- The open-source iOS reverse engineering community

---

**MIRROR4FREE** — because screen mirroring should be free. <img src="assets/icon.png" width="20" alt="Mirror4Free">
