using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

using LibUsbDotNet;
using LibUsbDotNet.Main;
using Device = LibUsbDotNet.Device;

using Serilog;

namespace Mirance.Usb;

/// <summary>
/// USB Device Manager - EXACT implementation like AnyMiro's Core.Connection.dll
/// 
/// Handles:
/// - iPhone/iPad device detection via libusb
/// - USB connection and communication
/// </summary>
public class DeviceManager : IDisposable
{
    #region Constants
    
    // Apple Vendor ID - same as AnyMiro
    public const int APPLE_VID = 0x05AC;
    
    // iPhone/iPad product IDs - same as AnyMiro
    private static readonly int[] IPHONE_PIDS = {
        0x12A8, 0x12A9, 0x12AA, 0x12AB, 0x12AC, 0x12AD, // iPhone 5-6s
        0x12E0, 0x12E1, 0x12E2, 0x12E3, 0x12E4, 0x12E5, // iPhone 7+
        0x12F0, 0x12F1, 0x12F2, 0x12F3, 0x12F4, 0x12F5, // iPhone 8/X
        0x12F7, 0x12F8, 0x12F9, 0x12FA, 0x12FB, // iPhone 11+
        0x12FE, 0x12FF, // iPhone 12+
        0x13D0, 0x13D1, 0x13D2, 0x13D3, // iPhone 13+
        0x13D4, 0x13D5, 0x13D6, 0x13D7, // iPhone 14+
    };
    
    private static readonly int[] IPAD_PIDS = {
        0x12A2, 0x12A3, 0x12A4, 0x12A5, // iPad
        0x12E8, 0x12E9, 0x12EA, // iPad Pro
        0x12F6, // iPad Pro 2018+
    };
    
    #endregion
    
    #region Events
    
    public event EventHandler<UsbDeviceInfo>? DeviceConnected;
    public event EventHandler<UsbDeviceInfo>? DeviceDisconnected;
    
    #endregion
    
    #region Fields
    
    private UsbContext? _usbContext;
    private Thread? _pollingThread;
    private bool _running;
    private readonly Dictionary<string, UsbDeviceInfo> _connectedDevices = new();
    private readonly object _lock = new();
    
    #endregion
    
    public DeviceManager()
    {
        // Initialize libusb - same as AnyMiro
        _usbContext = new UsbContext();
    }
    
    public void Start()
    {
        if (_running) return;
        
        _running = true;
        _pollingThread = new Thread(PollingLoop)
        {
            IsBackground = true,
            Name = "DevicePolling",
            Priority = ThreadPriority.BelowNormal
        };
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
    
    #region Polling
    
    private void PollingLoop()
    {
        Log.Debug("Device polling started");
        
        while (_running)
        {
            try
            {
                PollDevices();
            }
            catch (Exception ex)
            {
                Log.Warning(ex, "Polling error");
            }
            
            Thread.Sleep(2000);
        }
        
        Log.Debug("Device polling stopped");
    }
    
    private void PollDevices()
    {
        if (_usbContext == null) return;
        
        var deviceList = _usbContext.List();
        
        var currentUdids = new HashSet<string>();
        
        foreach (var device in deviceList)
        {
            // Check if Apple device
            if (device.VendorId != APPLE_VID)
                continue;
            
            // Check if iPhone/iPad
            if (!IsAppleMobileProduct(device.ProductId))
                continue;
            
            var udid = GetDeviceUdid(device);
            currentUdids.Add(udid);
            
            lock (_lock)
            {
                // New device
                if (!_connectedDevices.ContainsKey(udid))
                {
                    var deviceInfo = CreateDeviceInfo(device);
                    _connectedDevices[udid] = deviceInfo;
                    
                    Log.Information("Device connected: {Name}", deviceInfo.DisplayName);
                    DeviceConnected?.Invoke(this, deviceInfo);
                }
            }
        }
        
        // Check for disconnected devices
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
    
    private bool IsAppleMobileProduct(int productId)
    {
        foreach (var pid in IPHONE_PIDS)
        {
            if (productId == pid) return true;
        }
        
        foreach (var pid in IPAD_PIDS)
        {
            if (productId == pid) return true;
        }
        
        return false;
    }
    
    private string GetDeviceUdid(Device device)
    {
        return $"{device.VendorId:X4}:{device.ProductId:X4}.{device.SerialNumber}";
    }
    
    private UsbDeviceInfo CreateDeviceInfo(Device device)
    {
        return new UsbDeviceInfo
        {
            Udid = GetDeviceUdid(device),
            VendorId = device.VendorId,
            ProductId = device.ProductId,
            DisplayName = GetDeviceName(device),
            SerialNumber = device.SerialNumber ?? "",
        };
    }
    
    private string GetDeviceName(Device device)
    {
        var name = device.Product ?? "Unknown iOS Device";
        
        // Try to detect device type
        foreach (var pid in IPHONE_PIDS)
        {
            if (device.ProductId == pid)
                return $"iPhone ({name})";
        }
        
        foreach (var pid in IPAD_PIDS)
        {
            if (device.ProductId == pid)
                return $"iPad ({name})";
        }
        
        return name;
    }
    
    #endregion
    
    public void Dispose()
    {
        Stop();
        
        _usbContext?.Dispose();
        
        Log.Debug("Device manager disposed");
    }
}

/// <summary>
/// USB Device Information
/// </summary>
public class UsbDeviceInfo
{
    public string Udid { get; set; } = "";
    public int VendorId { get; set; }
    public int ProductId { get; set; }
    public string DisplayName { get; set; } = "";
    public string SerialNumber { get; set; } = "";
    
    public override string ToString() => DisplayName;
}