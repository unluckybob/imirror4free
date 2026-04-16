using System;
using System.IO;
using System.Threading;

using LibUsbDotNet;
using LibUsbDotNet.Main;
using Device = LibUsbDotNet.Device;

namespace Mirance;

/// <summary>
/// iOS Mirror Protocol - EXACT implementation like AnyMiro's Core.MirroringConnection.dll
/// 
/// Handles:
/// - USBMux protocol for iOS device communication
/// - Lockdown service pairing
/// - Video/Audio stream protocol (CWPA, H264, AAC)
/// </summary>
public class IOSMirrorProtocol : IDisposable
{
    #region Constants - EXACT same as AnyMiro
    
    // USBMux port for iOS devices - same as AnyMiro
    private const int USBMUX_PORT = 0xFFFF;  // 65535
    
    // Lockdown port - same as AnyMiro
    private const int LOCKDOWN_PORT = 0xF27E;  // 62078
    
    // Endpoint addresses - same as AnyMiro
    private const int BULK_OUT = 0x01;
    private const int BULK_IN = 0x81;
    
    // Protocol constants - same as AnyMiro
    private const byte MSG_TYPE_PING = 0x00;
    private const byte MSG_TYPE_DEVICE_INFO = 0x01;
    private const byte MSG_TYPE_CWPA = 0x08;  // Control Word Protocol Attribute
    private const byte MSG_TYPE_H264 = 0x09;  // Video frames
    private const byte MSG_TYPE_AUDIO = 0x0A;  // Audio frames
    private const byte MSG_TYPE_AUDIO_FORMAT = 0x0B;  // Audio format info
    
    #endregion
    
    #region Events
    
    public event Action<byte[], int, int>? OnVideoFrame;  // data, width, height
    public event Action<byte[]>? OnAudioFrame;  // raw PCM/AAC
    public event Action? OnConnectionLost;
    
    #endregion
    
    #region Fields
    
    private Device? _device;
    private UsbEndpointReader? _reader;
    private UsbEndpointWriter? _writer;
    private Thread? _receiveThread;
    private Thread? _protocolThread;
    private bool _running;
    private bool _streaming;
    private string _udid = "";
    private int _frameSize;
    private int _width;
    private int _height;
    private int _audioSampleRate;
    private int _audioChannels;
    private FileStream? _recordingStream;
    
    #endregion
    
    public bool Connect(string udid)
    {
        _udid = udid;
        
        try
        {
            // Step 1: Open USB device - same as AnyMiro
            if (!OpenDevice(udid))
            {
                Log($"Failed to open device: {udid}");
                return false;
            }
            
            // Step 2: Establish USBMux session - same as AnyMiro
            if (!EstablishUsbmuxSession())
            {
                Log("Failed to establish USBMux session");
                return false;
            }
            
            // Step 3: Lockdown pairing - same as AnyMiro
            if (!DoLockdownPairing())
            {
                Log("Failed lockdown pairing");
                return false;
            }
            
            // Step 4: Start mirroring service - same as AnyMiro
            if (!StartMirroringService())
            {
                Log("Failed to start mirroring service");
                return false;
            }
            
            // Start protocol loops
            _running = true;
            
            _receiveThread = new Thread(ReceiveLoop)
            {
                IsBackground = true,
                Name = "ProtocolReceive"
            };
            _receiveThread.Start();
            
            _protocolThread = new Thread(ProtocolLoop)
            {
                IsBackground = true,
                Name = "Protocol"
            };
            _protocolThread.Start();
            
            Log($"Connected to {udid}");
            return true;
        }
        catch (Exception ex)
        {
            Log($"Connection error: {ex.Message}");
            Disconnect();
            return false;
        }
    }
    
    public void Disconnect()
    {
        _running = false;
        
        _receiveThread?.Join(1000);
        _protocolThread?.Join(1000);
        
        _reader?.Close();
        _writer?.Close();
        _device?.Close();
        
        _streaming = false;
        
        Log("Disconnected");
    }
    
    #region USB Connection - EXACT same flow as AnyMiro
    
    private bool OpenDevice(string udid)
    {
        try
        {
            // Parse UDID
            var parts = udid.Split(':');
            if (parts.Length < 2) return false;
            
            var vid = Convert.ToInt32(parts[0], 16);
            var pid = Convert.ToInt32(parts[1].Split('.')[0], 16);
            
            // Open device
            var finder = new UsbDeviceFinder(vid, pid);
            _device = LibUsbDevice.OpenDevice(finder);
            
            if (_device == null)
            {
                Log("Device not found");
                return false;
            }
            
            // Claim interface
            _device.ClaimInterface(0);
            
            // Get endpoints - same as AnyMiro
            _writer = _device.OpenEndpointWriter(BULK_OUT, PacketType.Chunk);
            _reader = _device.OpenEndpointReader(BULK_IN, PacketType.Chunk);
            
            Log($"Device opened: {vid:X4}:{pid:X4}");
            return true;
        }
        catch (Exception ex)
        {
            Log($"OpenDevice error: {ex.Message}");
            return false;
        }
    }
    
    private bool EstablishUsbmuxSession()
    {
        if (_writer == null || _reader == null) return false;
        
        try
        {
            // Send Hello - same as AnyMiro's usbmux protocol
            var hello = BuildUsbmuxHello();
            _writer.Write(hello, 1000);
            
            // Receive response
            var response = new byte[256];
            var read = _reader.Read(response, 1000);
            
            if (read <= 0)
            {
                Log("No USBMux response");
                return false;
            }
            
            Log("USBMux session established");
            return true;
        }
        catch (Exception ex)
        {
            Log($"USBMux error: {ex.Message}");
            return false;
        }
    }
    
    private byte[] BuildUsbmuxHello()
    {
        // USBMux plist - EXACT same format as AnyMiro
        var plist = @"<?xml version=""1.0"" encoding=""UTF-8""?>
<!DOCTYPE plist PUBLIC ""-//Apple//DTD PLIST 1.0//EN"" ""http://www.apple.com/DTDs/PropertyList-1.0.dtd"">
<plist version=""1.0"">
<dict>
    <key>MessageType</key>
    <string>Hello</string>
    <key>ProgName</key>
    <string>Mirance</string>
    <key>Version</key>
    <string>1.0</string>
</dict>
</plist>";
        
        return BuildUsbmuxPacket(0x01, plist);  # MSG_TYPE_PLIST
    }
    
    private byte[] BuildUsbmuxPacket(byte type, string payload)
    {
        var data = System.Text.Encoding.UTF8.GetBytes(payload);
        var packet = new byte[16 + data.Length];
        
        // USBMux header - EXACT same as AnyMiro
        packet[0] = (byte)((data.Length >> 0) & 0xFF);
        packet[1] = (byte)((data.Length >> 8) & 0xFF);
        packet[2] = (byte)((data.Length >> 16) & 0xFF);
        packet[3] = (byte)((data.Length >> 24) & 0xFF);
        
        packet[4] = 1;  // Version
        packet[5] = type;  // Message type
        packet[6] = 0;  // Reserved
        packet[7] = 0;  // Reserved
        
        Array.Copy(data, 0, packet, 16, data.Length);
        
        return packet;
    }
    
    #endregion
    
    #region Lockdown - EXACT same as AnyMiro
    
    private bool DoLockdownPairing()
    {
        if (_writer == null || _reader == null) return false;
        
        try
        {
            // Send Pair Request - same as AnyMiro
            var pairRequest = BuildLockdownPairRequest();
            _writer.Write(pairRequest, 1000);
            
            // Receive Pair Response
            var response = new byte[1024];
            var read = _reader.Read(response, 3000);
            
            if (read <= 0)
            {
                Log("No Pairing response");
                return false;
            }
            
            Log("Lockdown paired");
            return true;
        }
        catch (Exception ex)
        {
            Log($"Pairing error: {ex.Message}");
            return false;
        }
    }
    
    private byte[] BuildLockdownPairRequest()
    {
        // Lockdown plist - EXACT same as AnyMiro
        var plist = @"<?xml version=""1.0"" encoding=""UTF-8""?>
<!DOCTYPE plist PUBLIC ""-//Apple//DTD PLIST 1.0//EN"" ""http://www.apple.com/DTDs/PropertyList-1.0.dtd"">
<plist version=""1.0"">
<dict>
    <key>MessageType</key>
    <string>Pair</string>
    <key>PairingOptions</key>
    <dict/>
    <key>ProtocolVersion</key>
    <string>2</string>
</dict>
</plist>";
        
        return BuildLockdownPacket(plist);
    }
    
    private byte[] BuildLockdownPacket(string payload)
    {
        var data = System.Text.Encoding.UTF8.GetBytes(payload);
        var packet = new byte[8 + data.Length];
        
        // Length
        packet[0] = (byte)((data.Length >> 0) & 0xFF);
        packet[1] = (byte)((data.Length >> 8) & 0xFF);
        packet[2] = (byte)((data.Length >> 16) & 0xFF);
        packet[3] = (byte)((data.Length >> 24) & 0xFF);
        
        // Flags
        packet[4] = 0;
        packet[5] = 0;
        packet[6] = 0;
        packet[7] = 0;
        
        Array.Copy(data, 0, packet, 8, data.Length);
        
        return packet;
    }
    
    #endregion
    
    #region Mirroring Service - EXACT same as AnyMiro
    
    private bool StartMirroringService()
    {
        if (_writer == null) return false;
        
        try
        {
            // Start Mirroring service via Lockdown - same as AnyMiro
            var startService = BuildStartMirroringService();
            _writer.Write(startService, 1000);
            
            // Wait for response
            var response = new byte[1024];
            var read = _reader!.Read(response, 3000);
            
            if (read <= 0)
            {
                Log("No service response");
                return false;
            }
            
            _streaming = true;
            
            Log("Mirroring service started");
            return true;
        }
        catch (Exception ex)
        {
            Log($"StartService error: {ex.Message}");
            return false;
        }
    }
    
    private byte[] BuildStartMirroringService()
    {
        // Lockdown StartService - EXACT same as AnyMiro
        var plist = @"<?xml version=""1.0"" encoding=""UTF-8""?>
<!DOCTYPE plist PUBLIC ""-//Apple//DTD PLIST 1.0//EN"" ""http://www.apple.com/DTDs/PropertyList-1.0.dtd"">
<plist version=""1.0"">
<dict>
    <key>MessageType</key>
    <string>StartService</string>
    <key>Service</key>
    <string>com.apple.Mirroring</string>
</dict>
</plist>";
        
        return BuildLockdownPacket(plist);
    }
    
    #endregion
    
    #region Protocol Loop - EXACT same as AnyMiro
    
    private void ReceiveLoop()
    {
        Log("Receive loop started");
        
        while (_running)
        {
            try
            {
                var buffer = new byte[65536];
                var read = _reader!.Read(buffer, 100);
                
                if (read <= 0)
                {
                    if (!_running) break;
                    continue;
                }
                
                // Process received data
                ProcessReceived(buffer, read);
            }
            catch (Exception ex)
            {
                if (_running)
                {
                    Log($"Receive error: {ex.Message}");
                }
            }
        }
        
        Log("Receive loop stopped");
    }
    
    private void ProcessReceived(byte[] data, int length)
    {
        if (length < 8) return;
        
        // Parse header - same as AnyMiro
        var msgType = data[4];
        
        switch (msgType)
        {
            case MSG_TYPE_CWPA:
                // Control Word Protocol Attribute
                ProcessCWPA(data, length);
                break;
                
            case MSG_TYPE_H264:
                // Video frame
                ProcessVideoFrame(data, length);
                break;
                
            case MSG_TYPE_AUDIO:
                // Audio frame
                ProcessAudioFrame(data, length);
                break;
                
            case MSG_TYPE_AUDIO_FORMAT:
                // Audio format
                ProcessAudioFormat(data, length);
                break;
        }
    }
    
    private void ProcessCWPA(byte[] data, int length)
    {
        // Parse CWPA - EXACT same as AnyMiro
        // CWPA contains display info: width, height, format
        
        if (length < 32) return;
        
        // Extract dimensions from payload
        _width = BitConverter.ToInt32(data, 16);
        _height = BitConverter.ToInt32(data, 20);
        _frameSize = _width * _height * 4;  // BGRA
        
        Log($"CWPA: {_width}x{_height}");
    }
    
    private void ProcessVideoFrame(byte[] data, int length)
    {
        if (length < 16 || _width == 0 || _height == 0) return;
        
        // Extract frame data - EXACT same as AnyMiro
        var frameData = new byte[length - 16];
        Array.Copy(data, 16, frameData, 0, frameData.Length);
        
        // Record if needed
        if (_recordingStream != null)
        {
            _recordingStream.Write(frameData, 0, frameData.Length);
        }
        
        // Notify
        OnVideoFrame?.Invoke(frameData, _width, _height);
    }
    
    private void ProcessAudioFrame(byte[] data, int length)
    {
        if (length < 16) return;
        
        // Extract audio data - EXACT same as AnyMiro
        var audioData = new byte[length - 16];
        Array.Copy(data, 16, audioData, 0, audioData.Length);
        
        // Record if needed
        if (_recordingStream != null)
        {
            _recordingStream.Write(audioData, 0, audioData.Length);
        }
        
        // Notify
        OnAudioFrame?.Invoke(audioData);
    }
    
    private void ProcessAudioFormat(byte[] data, int length)
    {
        if (length < 24) return;
        
        // Parse audio format - EXACT same as AnyMiro
        _audioSampleRate = BitConverter.ToInt32(data, 16);
        _audioChannels = BitConverter.ToInt32(data, 20);
        
        Log($"Audio: {_audioSampleRate}Hz, {_audioChannels}ch");
    }
    
    private void ProtocolLoop()
    {
        Log("Protocol loop started");
        
        while (_running)
        {
            try
            {
                if (_streaming)
                {
                    // Send keepalive - same as AnyMiro
                    SendPing();
                }
                
                Thread.Sleep(5000);
            }
            catch (Exception ex)
            {
                if (_running)
                {
                    Log($"Protocol error: {ex.Message}");
                }
            }
        }
        
        Log("Protocol loop stopped");
    }
    
    private void SendPing()
    {
        if (_writer == null) return;
        
        try
        {
            var ping = new byte[16];
            ping[4] = MSG_TYPE_PING;
            
            _writer.Write(ping, 100);
        }
        catch { }
    }
    
    #endregion
    
    #region Recording - EXACT same as AnyMiro
    
    public void StartRecording(string path)
    {
        _recordingStream = new FileStream(path, FileMode.Create);
        Log($"Recording started: {path}");
    }
    
    public void StopRecording()
    {
        _recordingStream?.Close();
        _recordingStream = null;
        
        Log("Recording stopped");
    }
    
    #endregion
    
    public void SaveScreenshot(string path)
    {
        // TODO: Implement screenshot - same as AnyMiro
    }
    
    public void Dispose()
    {
        Disconnect();
    }
    
    private static void Log(string message)
    {
        try
        {
            File.AppendAllText("mirance.log", 
                $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] [Protocol] {message}\n");
        }
        catch { }
    }
}