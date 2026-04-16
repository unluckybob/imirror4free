# Mirance C# (WPF + SharpDX) - Full Rebuild Like AnyMiro

**Complete rebuild** of the iPhone mirroring application using the exact same technology stack as AnyMiro:

- **WPF** (Windows Presentation Foundation) - GUI framework
- **SharpDX.Direct3D9** - DirectX rendering (like Core.MD.Render.dll)
- **LibUsbDotNet** - USB communication (like Core.Connection.dll)
- **NAudio** - Audio playback (like Core.AudioDevices.dll)
- **Serilog** - Logging (like Core.Tracing.dll)

## Requirements

- **.NET 8 SDK** - https://dotnet.microsoft.com/download
- **Windows 10/11** (64-bit)

## Building

### From Command Line

```bash
# Clone the repo
git clone https://github.com/unluckybob/mirance.git
cd mirance

# Navigate to project
cd src/Mirance

# Restore packages
dotnet restore

# Build
dotnet build -c Release

# Run
dotnet run -c Release

# Publish as single EXE
dotnet publish -c Release -r win-x64 --self-contained -p:PublishSingleFile=true -o ./publish
```

### From GitHub Actions

The project automatically builds on every push to main branch:

1. Go to https://github.com/unluckybob/mirance/actions
2. Click on the latest workflow run
3. Download the built EXE from Artifacts

## Project Structure

```
src/Mirance/
├── Mirance.csproj           # Project file with dependencies
├── App.xaml / .cs          # Application entry point
├── MainWindow.xaml / .cs   # Main UI with SharpDX rendering
├── SettingsWindow.xaml / .cs # Settings dialog
├── Usb/
│   └── DeviceManager.cs     # Device detection (LibUsbDotNet)
├── Protocol/
│   └── IOSMirrorProtocol.cs # iOS mirroring protocol
├── Render/
│   └── Direct3DRenderer.cs # SharpDX rendering
├── Audio/
│   └── AudioPlayer.cs    # NAudio playback
├── Settings/
│   └── AppSettings.cs   # Application settings
└── RecordingManager.cs     # Recording to file
```

## Features

| Feature | Status | Implementation |
|---------|--------|----------------|
| Device Detection | ✅ | LibUsbDotNet polls USB for iPhone/iPad |
| USBMux | ✅ | usbmux protocol |
| Lockdown Pairing | ✅ | Lockdown service |
| Mirroring Protocol | ✅ | CWPA, H264, AAC |
| SharpDX Rendering | ✅ | Direct3D9 texture upload |
| Audio Playback | ✅ | NAudio wave out |
| Recording | 🔄 | Raw file output |
| Settings | ✅ | JSON persistence |
| Fullscreen | ✅ | Window state toggle |
| Screenshot | ✅ | PNG export |

## Comparison with AnyMiro

| Component | AnyMiro | Mirance C# |
|-----------|---------|------------|
| GUI | WPF | WPF (net8.0-windows) |
| Rendering | SharpDX.D3D9 | SharpDX 4.2.0 |
| USB | libusb | LibUsbDotNet 1.9.0 |
| Audio | Windows Audio | NAudio 2.2.1 |
| JSON | Newtonsoft | Newtonsoft.Json 13.0.3 |
| Logging | Custom | Serilog 3.1.1 |

## Usage

1. Run `Mirance.exe`
2. Connect your iPhone/iPad via USB
3. Select device from dropdown
4. Click "Connect"

### Keyboard Shortcuts

- **Ctrl+F** - Toggle fullscreen
- **Ctrl+S** - Take screenshot
- **Ctrl+R** - Toggle recording
- **ESC** - Exit fullscreen

## Troubleshooting

### No device detected

1. Install iTunes (Apple Device Driver)
2. Unlock your iPhone and tap "Trust"
3. Replug USB cable

### Black screen after connect

1. Check iPhone for trust prompt
2. Tap "Trust" on iPhone
3. Restart app

### High CPU usage

1. Open Settings
2. Lower Max FPS to 30
3. Disable VSync if needed

## License

MIT License - Built by Mirance Team