# Mirance - iPhone USB Screen Mirroring

## Quick Reference

### Key Commands
```bash
# Run the application
python -m mirance

# Development
pip install -r requirements.txt
pip install -e .
```

### Protocol Implementation (FINAL)

Based on analysis of external files from DropMeFiles:
- `iPhone_USB_Mirror_Dev_Guide.md` - Protocol specification ✓ Verified
- `anym_capture.pcapng` - PCAP capture for validation
- `ispyoutput.zip` - 47 C# reference files

### Critical Implementation Details (ALL VERIFIED)

| Feature | Code Location | Status |
|---------|--------------|--------|
| USB QuickTime activation | `protocol.py:activate_quicktime_mode()` | ✓ 0x52 control transfer |
| REVERSED magic bytes | `protocol.py:PacketType` | ✓ All 16 verified |
| Handshake state machine | `protocol.py:HandshakeHandler` | ✓ PING→...→OG |
| BufferAhead=73ms | `config.py` + `protocol.py` | ✓ Verified |
| ScreenLatency=40ms | `config.py` + `protocol.py` | ✓ Verified |
| QuickTime interface | `usb/device.py:find_qt_device()` | ✓ Subclass 0x2A |

### Magic Bytes Verification (ALL PASSED)
```
ASYN:nysa ✓ SYNC:cnys ✓ RPLY:ylpr ✓ HPD1:1dph ✓ HPA1:1aph ✓
AFMT:tmfa ✓ CVRP:prvc ✓ FEED:feed ✓ EAT:\x00eat ✓ NEED:need ✓
PING:gnip ✓ CWPA:cwap ✓ CLOK:loko ✓ TIME:emit ✓ SKEW:weks ✓ OG:\x00go ✓
```

### Capture Backends
- Only **Valeria** (USB QuickTime streaming) - No screenshot mode
- Screenshot saving still works (Ctrl+S saves current frame)

### Architecture

```
mirance/
├── capture/        # Stream capture (Valeria only)
├── protocol.py     # Protocol implementation (handshake, magic bytes)
├── config.py       # Configuration (buffer, USB settings)
├── decode/         # Video (HEVC/AVC) + Audio (48kHz PCM)
├── usb/           # USB device management
└── gui/           # GUI (PyQt6)
```

## Dependencies
- pyusb, libusb-package (USB communication)
- pymobiledevice3 (pairing)
- PyAV (FFmpeg - video decode)
- PyQt6 (GUI)
- sounddevice (audio output)