using System;
using System.IO;
using System.Threading;
using LibUsbDotNet;
using LibUsbDotNet.Main;
using Serilog;

namespace Mirance.Protocol;

/// <summary>
/// iOS Mirror Protocol - Using LibUsbDotNet 2.x
/// </summary>
public class IOSMirrorProtocol : IDisposable
{
    private const byte MSG_TYPE_PING = 0x00;
    private const byte MSG_TYPE_CWPA = 0x08;
    private const byte MSG_TYPE_H264 = 0x09;
    private const byte MSG_TYPE_AUDIO = 0x0A;
    private const byte MSG_TYPE_AUDIO_FORMAT = 0x0B;
    
    public event Action<byte[], int, int>? OnVideoFrame;
    public event Action<byte[]>? OnAudioFrame;
    public event Action? OnConnectionLost;
    public event Action<string>? OnError;
    
    private UsbDevice? _device;
    private UsbEndpointReader? _reader;
    private UsbEndpointWriter? _writer;
    private Thread? _receiveThread;
    private Thread? _keepaliveThread;
    private bool _running;
    private string _udid = "";
    private int _width;
    private int _height;
    
    public bool Connect(string udid)
    {
        _udid = udid;
        try
        {
            var parts = udid.Split(':');
            if (parts.Length < 2) return false;
            
            var vid = Convert.ToInt32(parts[0], 16);
            var pid = Convert.ToInt32(parts[1].Split('.')[0], 16);
            
            var finder = new UsbDeviceFinder(vid, pid);
            _device = UsbDevice.OpenDevice(finder);
            
            if (_device == null) return false;
            
            _device.ClaimInterface(0);
            _writer = _device.OpenEndpointWriter(WriteEndpointID.Ep01, PacketType.Chunk);
            _reader = _device.OpenEndpointReader(ReadEndpointID.Ep01, PacketType.Chunk);
            
            _running = true;
            _receiveThread = new Thread(ReceiveLoop) { IsBackground = true };
            _receiveThread.Start();
            _keepaliveThread = new Thread(KeepaliveLoop) { IsBackground = true };
            _keepaliveThread.Start();
            
            Log.Information("Connected to {Udid}", udid);
            return true;
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Connection error");
            Disconnect();
            return false;
        }
    }
    
    public void Disconnect()
    {
        _running = false;
        try { _reader?.Close(); _writer?.Close(); _device?.Close(); } catch { }
        _reader = null; _writer = null; _device = null;
    }
    
    private void ReceiveLoop()
    {
        while (_running)
        {
            try
            {
                var buffer = new byte[65536];
                var read = _reader?.Read(buffer, 100);
                if (read > 0) ProcessReceived(buffer, read ?? 0);
            }
            catch { }
        }
    }
    
    private void ProcessReceived(byte[] data, int length)
    {
        if (length < 8) return;
        var msgType = data[4];
        
        switch (msgType)
        {
            case MSG_TYPE_CWPA:
                if (length >= 32) { _width = BitConverter.ToInt32(data, 16); _height = BitConverter.ToInt32(data, 20); }
                break;
            case MSG_TYPE_H264:
                if (length > 16 && _width > 0)
                {
                    var frameData = new byte[length - 16];
                    Array.Copy(data, 16, frameData, 0, frameData.Length);
                    OnVideoFrame?.Invoke(frameData, _width, _height);
                }
                break;
            case MSG_TYPE_AUDIO:
                if (length > 16)
                {
                    var audioData = new byte[length - 16];
                    Array.Copy(data, 16, audioData, 0, audioData.Length);
                    OnAudioFrame?.Invoke(audioData);
                }
                break;
        }
    }
    
    private void KeepaliveLoop()
    {
        while (_running)
        {
            try { Thread.Sleep(5000); SendPing(); } catch { }
        }
    }
    
    private void SendPing()
    {
        try
        {
            var ping = new byte[16];
            ping[4] = MSG_TYPE_PING;
            _writer?.Write(ping, 100);
        }
        catch { }
    }
    
    public void Dispose() { Disconnect(); }
}
