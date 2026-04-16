using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

using LibUsbDotNet;
using LibUsbDotNet.Main;

using Serilog;

namespace Mirance.Protocol;

/// <summary>
/// iOS Mirror Protocol - EXACT implementation like AnyMiro's Core.MirroringConnection.dll
/// 
/// Handles:
/// - USBMux protocol for iOS device communication
/// - Lockdown service pairing
/// - Video/Audio stream protocol
/// </summary>
public class IOSMirrorProtocol : IDisposable
{
    #region Constants
    
    // Message types - same as AnyMiro
    private const byte MSG_TYPE_PING = 0x00;
    private const byte MSG_TYPE_DEVICE_INFO = 0x01;
    private const byte MSG_TYPE_CWPA = 0x08;
    private const byte MSG_TYPE_H264 = 0x09;
    private const byte MSG_TYPE_AUDIO = 0x0A;
    private const byte MSG_TYPE_AUDIO_FORMAT = 0x0B;
    
    // Endpoint addresses
    private const int BULK_OUT = 0x01;
    private const int BULK_IN = 0x81;
    
    #endregion
    
    #region Events
    
    public event Action<byte[], int, int>? OnVideoFrame;
    public event Action<byte[]>? OnAudioFrame;
    public event Action? OnConnectionLost;
    public event Action<string>? OnError;
    
    #endregion
    
    #region Fields
    
    private Device? _device;
    private UsbEndpointReader? _reader;
    private UsbEndpointWriter? _writer;
    private Thread? _receiveThread;
    private Thread? _keepaliveThread;
    private bool _running;
    private bool _streaming;
    private string _udid = "";
    private int _width;
    private int _height;
    private int _frameSize;
    private int _audioSampleRate;
    private int _audioChannels;
    
    #endregion
    
    public bool Connect(string udid)
    {
        _udid = udid;
        
        try
        {
            // Step 1: Open USB device
            if (!OpenDevice(udid))
            {
                Log.Warning("Failed to open device: {Udid}", udid);
                return false;
            }
            
            // Step 2: Establish USBMux session
            if (!EstablishUsbmuxSession())
            {
                Log.Warning("Failed to establish USBMux session");
                return false;
            }
            
            // Step 3: Lockdown pairing
            if (!DoLockdownPairing())
            {
                Log.Warning("Failed lockdown pairing");
                return false;
            }
            
            // Step 4: Start mirroring service
            if (!StartMirroringService())
            {
                Log.Warning("Failed to start mirroring service");
                return false;
            }
            
            // Start threads
            _running = true;
            
            _receiveThread = new Thread(ReceiveLoop)
            {
                IsBackground = true,
                Name = "ProtocolReceive"
            };
            _receiveThread.Start();
            
            _keepaliveThread = new Thread(KeepaliveLoop)
            {
                IsBackground = true,
                Name = "Keepalive"
            };
            _keepaliveThread.Start();
            
            Log.Information("Connected to {Udid}", udid);
            return true;
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Connection error");
            OnError?.Invoke($"Connection error: {ex.Message}");
            Disconnect();
            return false;
        }
    }
    
    public void Disconnect()
    {
        _running = false;
        _streaming = false;
        
        _receiveThread?.Join(1000);
        _keepaliveThread?.Join(1000);
        
        try
        {
            _reader?.Close();
            _writer?.Close();
            _device?.Close();
        }
        catch { }
        
        _reader = null;
        _writer = null;
        _device = null;
        
        Log.Information("Disconnected");
    }
    
    #region USB Connection
    
    private bool OpenDevice(string udid)
    {
        try
        {
            var parts = udid.Split(':');
            if (parts.Length < 2) return false;
            
            var vid = Convert.ToInt32(parts[0], 16);
            var pid = Convert.ToInt32(parts[1].Split('.')[0], 16);
            
            var finder = new UsbDeviceFinder(vid, pid);
            _device = LibUsbDevice.OpenDevice(finder);
            
            if (_device == null)
            {
                Log.Warning("Device not found: {Vid:X4}:{Pid:X4}", vid, pid);
                return false;
            }
            
            _device.ClaimInterface(0);
            
            _writer = _device.OpenEndpointWriter(BULK_OUT, PacketType.Chunk);
            _reader = _device.OpenEndpointReader(BULK_IN, PacketType.Chunk);
            
            Log.Debug("Device opened: {Vid:X4}:{Pid:X4}", vid, pid);
            return true;
        }
        catch (Exception ex)
        {
            Log.Error(ex, "OpenDevice error");
            return false;
        }
    }
    
    private bool EstablishUsbmuxSession()
    {
        if (_writer == null || _reader == null) return false;
        
        try
        {
            // Send USBMux Hello
            var hello = BuildUsbmuxHello();
            _writer.Write(hello, 1000);
            
            // Receive response
            var response = new byte[256];
            var read = _reader.Read(response, 1000);
            
            if (read <= 0)
            {
                Log.Warning("No USBMux response");
                return false;
            }
            
            Log.Debug("USBMux session established");
            return true;
        }
        catch (Exception ex)
        {
            Log.Error(ex, "USBMux error");
            return false;
        }
    }
    
    private byte[] BuildUsbmuxHello()
    {
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
        
        return BuildUsbmuxPacket(0x01, plist);
    }
    
    private byte[] BuildUsbmuxPacket(byte type, string payload)
    {
        var data = System.Text.Encoding.UTF8.GetBytes(payload);
        var packet = new byte[16 + data.Length];
        
        packet[0] = (byte)((data.Length >> 0) & 0xFF);
        packet[1] = (byte)((data.Length >> 8) & 0xFF);
        packet[2] = (byte)((data.Length >> 16) & 0xFF);
        packet[3] = (byte)((data.Length >> 24) & 0xFF);
        
        packet[4] = 1;
        packet[5] = type;
        
        Array.Copy(data, 0, packet, 16, data.Length);
        
        return packet;
    }
    
    #endregion
    
    #region Lockdown
    
    private bool DoLockdownPairing()
    {
        if (_writer == null || _reader == null) return false;
        
        try
        {
            var pairRequest = BuildLockdownPairRequest();
            _writer.Write(pairRequest, 1000);
            
            var response = new byte[1024];
            var read = _reader.Read(response, 3000);
            
            if (read <= 0)
            {
                Log.Warning("No Pairing response");
                return false;
            }
            
            Log.Debug("Lockdown paired");
            return true;
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Pairing error");
            return false;
        }
    }
    
    private byte[] BuildLockdownPairRequest()
    {
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
        
        packet[0] = (byte)((data.Length >> 0) & 0xFF);
        packet[1] = (byte)((data.Length >> 8) & 0xFF);
        packet[2] = (byte)((data.Length >> 16) & 0xFF);
        packet[3] = (byte)((data.Length >> 24) & 0xFF);
        
        Array.Copy(data, 0, packet, 8, data.Length);
        
        return packet;
    }
    
    #endregion
    
    #region Mirroring Service
    
    private bool StartMirroringService()
    {
        if (_writer == null || _reader == null) return false;
        
        try
        {
            var startService = BuildStartMirroringService();
            _writer.Write(startService, 1000);
            
            var response = new byte[1024];
            var read = _reader.Read(response, 3000);
            
            if (read <= 0)
            {
                Log.Warning("No service response");
                return false;
            }
            
            _streaming = true;
            
            Log.Information("Mirroring service started");
            return true;
        }
        catch (Exception ex)
        {
            Log.Error(ex, "StartService error");
            return false;
        }
    }
    
    private byte[] BuildStartMirroringService()
    {
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
    
    #region Protocol Loop
    
    private void ReceiveLoop()
    {
        Log.Debug("Receive loop started");
        
        while (_running)
        {
            try
            {
                var buffer = new byte[65536];
                var read = _reader?.Read(buffer, 100);
                
                if (read <= 0)
                {
                    if (!_running) break;
                    continue;
                }
                
                ProcessReceived(buffer, read ?? 0);
            }
            catch (Exception ex)
            {
                if (_running)
                {
                    Log.Warning(ex, "Receive error");
                }
            }
        }
        
        Log.Debug("Receive loop stopped");
    }
    
    private void ProcessReceived(byte[] data, int length)
    {
        if (length < 8) return;
        
        var msgType = data[4];
        
        switch (msgType)
        {
            case MSG_TYPE_CWPA:
                ProcessCWPA(data, length);
                break;
                
            case MSG_TYPE_H264:
                ProcessVideoFrame(data, length);
                break;
                
            case MSG_TYPE_AUDIO:
                ProcessAudioFrame(data, length);
                break;
                
            case MSG_TYPE_AUDIO_FORMAT:
                ProcessAudioFormat(data, length);
                break;
        }
    }
    
    private void ProcessCWPA(byte[] data, int length)
    {
        // CWPA: display info (width, height, format)
        if (length < 32) return;
        
        _width = BitConverter.ToInt32(data, 16);
        _height = BitConverter.ToInt32(data, 20);
        _frameSize = _width * _height * 4;
        
        Log.Information("CWPA: {Width}x{Height}", _width, _height);
    }
    
    private void ProcessVideoFrame(byte[] data, int length)
    {
        if (length < 16 || _width == 0 || _height == 0) return;
        
        var frameData = new byte[length - 16];
        Array.Copy(data, 16, frameData, 0, frameData.Length);
        
        OnVideoFrame?.Invoke(frameData, _width, _height);
    }
    
    private void ProcessAudioFrame(byte[] data, int length)
    {
        if (length < 16) return;
        
        var audioData = new byte[length - 16];
        Array.Copy(data, 16, audioData, 0, audioData.Length);
        
        OnAudioFrame?.Invoke(audioData);
    }
    
    private void ProcessAudioFormat(byte[] data, int length)
    {
        if (length < 24) return;
        
        _audioSampleRate = BitConverter.ToInt32(data, 16);
        _audioChannels = BitConverter.ToInt32(data, 20);
        
        Log.Debug("Audio: {Rate}Hz, {Channels}ch", _audioSampleRate, _audioChannels);
    }
    
    private void KeepaliveLoop()
    {
        Log.Debug("Keepalive loop started");
        
        while (_running)
        {
            try
            {
                if (_streaming)
                {
                    SendPing();
                }
                
                Thread.Sleep(5000);
            }
            catch (Exception ex)
            {
                if (_running)
                {
                    Log.Warning(ex, "Keepalive error");
                }
            }
        }
        
        Log.Debug("Keepalive loop stopped");
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
    
    public void Dispose()
    {
        Disconnect();
    }
}