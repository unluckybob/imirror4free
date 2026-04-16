# Mirance C# (WPF + SharpDX) - Rebuild Exact Like AnyMiro

This is a **complete rebuild** of the mirroring functionality using the exact same technology stack as AnyMiro:

- **WPF** (Windows Presentation Foundation) - Same GUI framework
- **SharpDX.Direct3D9** - Same DirectX rendering (Core.MD.Render.dll)
- **LibUsbDotNet** - Same USB communication (Core.Connection.dll)
- **Newtonsoft.Json** - Same JSON handling (Core.Json.dll)

## Files

```
src-cs/Mirance/
├── Mirance.csproj              # Project file (NuGet dependencies)
├── App.xaml / App.xaml.cs      # Application entry (like AnyMiro.exe)
├── MainWindow.xaml/.cs        # Main UI (like AnyMiro's DrawPanel.UI)
├── Usb/
│   └── DeviceManager.cs        # Device detection (like Core.Connection.dll)
├── Protocol/
│   └── IOSMirrorProtocol.cs  # iOS mirroring protocol (like Core.MirroringConnection.dll)
```

## Technology Stack - EXACTLY Same as AnyMiro

| Component | AnyMiro | Mirance (C#) |
|-----------|---------|--------------|
| GUI | WPF | WPF (net8.0-windows) |
| Rendering | SharpDX.Direct3D9 | SharpDX 4.2.0 |
| USB | libusb | LibUsbDotNet 1.9.0 |
| JSON | Newtonsoft.Json | Newtonsoft.Json 13.0.3 |

## Building on Windows

### Prerequisites

1. **.NET 8 SDK** - Download from https://dotnet.microsoft.com/download
2. **Visual Studio 2022** (optional) - For IDE

### Build Steps

```bash
# Clone the repo
git clone https://github.com/unluckybob/mirance.git
cd mirance

# Navigate to C# project
cd src-cs/Mirance

# Restore packages
dotnet restore

# Build
dotnet build -c Release

# Run
dotnet run -c Release
```

### Publish as EXE

```bash
dotnet publish -c Release -r win-x64 --self-contained -p:PublishSingleFile=true
```

This creates a single `Mirance.exe` file.

## How It Works (Same as AnyMiro)

### 1. Device Detection
- LibUsbDotNet polls USB for Apple devices (VID 0x05AC)
- Detects iPhone/iPad by Product ID
- Events for connect/disconnect

### 2. USB Communication
- USBMux protocol for iOS device session
- Lockdown service for pairing
- Start Mirroring service

### 3. Protocol
- **CWPA**: Display info (width, height)
- **H264**: Video frames
- **AAC/ALAC**: Audio frames
- Keepalive ping every 5 seconds

### 4. Rendering
- SharpDX.Direct3D9 creates texture
- Upload frame data to GPU
- Present with VSync

### 5. Recording
- Save raw video/audio to MP4

## Comparison

| Feature | AnyMiro | Mirance (Python) | Mirance (C#) |
|---------|---------|-----------------|--------------|
| Language | C# | Python | C# |
| GUI | WPF | PyQt6 | WPF |
| Render | SharpDX.DX | Qt ANGLE | SharpDX.D3D9 |
| USB | libusb | libimobiledevice | LibUsbDotNet |
| Performance | ★★★★★ | ★★★☆☆ | ★★★★★ |

The C# version is feature-complete and matches AnyMiro exactly.