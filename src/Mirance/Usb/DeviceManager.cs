using System;
using System.Collections.Generic;
using System.Threading;

using LibUsbDotNet;
using LibUsbDotNet.Main;

using Serilog;

namespace Mirance.Usb;

/// <summary>
/// USB Device Manager - Using LibUsbDotNet 2.x
/// </summary>
public class DeviceManager : IDisposable
{
    public const int APPLE_VID = 0x05AC;
    
    public event EventHandler<UsbDeviceInfo>? DeviceConnected;
    public event EventHandler<UsbDeviceInfo>? DeviceDisconnected;
    
    private UsbContext? _usbContext;
    private Thread? _pollingThread;
    private bool _running;
    private readonly Dictionary<string, UsbDeviceInfo> _connectedDevices = new();
    private readonly object _lock = new();
    
    public DeviceManager()
    {
        _usbContext = new UsbContext();
    }
    
    public void Start()
    {
        if (_running) return;
        _running = true;
        _pollingThread = new Thread(PollingLoop) { IsBackground = true, Name = "DevicePolling" };
        _pollingThread.Start();
        Log.Information("Device manager started");
    }
    
    public void Stop()
    {
        _running = false;
        _pollingThread?.Join(2000);
        Log.Information("Device manager stopped");
    }
    
    public List<UsbDeviceInfo> GetDevices()
    {
        lock (_lock)
        {
            return new List<UsbDeviceInfo>(_connectedDevices.Values);
        }
    }
    
    private void PollingLoop()
    {
        while (_running)
        {
            try { PollDevices(); }
            catch (Exception ex) { Log.Warning(ex, "Polling error"); }
            Thread.Sleep(2000);
        }
    }
    
    private void PollDevices()
    {
        if (_usbContext == null) return;
        
        var deviceList = _usbContext.List();
        var currentUdids = new HashSet<string>();
        
        foreach (var device in deviceList)
        {
            if (device.VendorId != APPLE_VID) continue;
            
            var udid = $"{device.VendorId:X4}:{device.ProductId:X4}";
            currentUdids.Add(udid);
            
            lock (_lock)
            {
                if (!_connectedDevices.ContainsKey(udid))
                {
                    var deviceInfo = new UsbDeviceInfo
                    {
                        Udid = udid,
                        VendorId = device.VendorId,
                        ProductId = device.ProductId,
                        DisplayName = device.Product ?? "iOS Device"
                    };
                    _connectedDevices[udid] = deviceInfo;
                    Log.Information("Device connected: {Name}", deviceInfo.DisplayName);
                    DeviceConnected?.Invoke(this, deviceInfo);
                }
            }
        }
        
        lock (_lock)
        {
            var toRemove = new List<string>();
            foreach (var kvp in _connectedDevices)
            {
                if (!currentUdids.Contains(kvp.Key))
                {
                    toRemove.Add(kvp.Key);
                }
            }
            foreach (var udid in toRemove)
            {
                var deviceInfo = _connectedDevices[udid];
                _connectedDevices.Remove(udid);
                Log.Information("Device disconnected: {Name}", deviceInfo.DisplayName);
                DeviceDisconnected?.Invoke(this, deviceInfo);
            }
        }
    }
    
    public void Dispose()
    {
        Stop();
        _usbContext?.Dispose();
    }
}

public class UsbDeviceInfo
{
    public string Udid { get; set; } = "";
    public int VendorId { get; set; }
    public int ProductId { get; set; }
    public string DisplayName { get; set; } = "";
    public override string ToString() => DisplayName;
}
