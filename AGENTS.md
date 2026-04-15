# Mirance - iPhone USB Screen Mirroring

## Quick Reference

### Key Commands
```bash
# Run the application
python -m mirance

# Development
pip install -e .
```

### Protocol Implementation

Based on analysis of external files from DropMeFiles:
- `iPhone_USB_Mirror_Dev_Guide.md` - Protocol specification
- `anym_capture.pcapng` - PCAP capture for validation

### Critical Implementation Details

1. **USB QuickTime Mode Activation**
   - Control transfer: `0x40, 0x52, wIndex=0x0002`
   - Re-enumerate and poll for `subclass=0x2A`

2. **Magic Bytes (REVERSED on wire!)**
   - ASYN → `nysa`
   - SYNC → `cnys`
   - HPD1 → `1dph`
   - HPA1 → `1aph`

3. **Buffer Settings (pcap-confirmed)**
   - BufferAheadInterval: 73ms
   - ScreenLatency: 40ms

### Architecture

```
mirance/
├── capture/        # Stream capture backends
├── config.py        # Configuration
├── decode/          # Video decoding (FFmpeg/VAAPI/D3D11VA)
├── gui/             # GUI (PyQt)
├── render/          # Display rendering
├── usb/             # USB handling
│   ├── packets.py   # Protocol packet parsing
│   └── endpoint.py  # USB endpoint management
└── protocol.py       # NEW: Protocol implementation
```

## Notes

- Uses pymobiledevice3 for lockdown/pairing
- Uses pyusb + libusb for USB communication
- HEVC decoding via FFmpeg (D3D11VA on Windows)