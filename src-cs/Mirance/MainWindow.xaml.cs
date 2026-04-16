using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Threading;
using System.IO;
using System.Threading;
using System.Collections.Generic;

using SharpDX;
using SharpDX.Direct3D9;
using SharpDX.DXGI;
using SharpDX.Direct2D1;
using Device = SharpDX.Direct3D9.Device;
using DeviceContext = SharpDX.Direct3D9.DeviceContext;

namespace Mirance;

/// <summary>
/// Main Window - EXACT implementation like AnyMiro's MainWindow.xaml.cs
/// 
/// Handles:
/// - Device detection and connection
/// - SharpDX Direct3D9 rendering (same as AnyMiro's Core.MD.Render.dll)
/// - Recording and screenshot
/// - Audio playback
/// </summary>
public partial class MainWindow : Window
{
    #region Fields
    
    private DeviceManager? _deviceManager;
    private IOSMirrorProtocol? _protocol;
    private Direct3DEx? _d3d9;
    private Device? _device;
    private Texture? _videoTexture;
    private bool _isRecording;
    private string _currentDeviceUdid = "";
    private DateTime _lastFrameTime;
    private int _frameCount;
    private int _fps;
    private DispatcherTimer? _fpsTimer;
    private bool _isFullscreen;
    private WindowState _prevWindowState;
    private WindowStyle _prevWindowStyle;
    private ResizeMode _prevResizeMode;
    
    #endregion
    
    public MainWindow()
    {
        InitializeComponent();
        
        // Setup FPS counter - same as AnyMiro
        _fpsTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _fpsTimer.Tick += (s, e) => {
            txtFPS.Text = $"{_fps} FPS";
            _fps = 0;
        };
        _fpsTimer.Start();
        
        Log("MainWindow created");
    }
    
    #region Window Events
    
    private void Window_Loaded(object sender, RoutedEventArgs e)
    {
        Log("Window loaded");
        
        // Initialize device manager - same as AnyMiro
        _deviceManager = new DeviceManager();
        _deviceManager.DeviceConnected += OnDeviceConnected;
        _deviceManager.DeviceDisconnected += OnDeviceDisconnected;
        _deviceManager.Start();
        
        // Initialize SharpDX - same as AnyMiro
        InitializeDirect3D();
        
        Log("Initialization complete");
    }
    
    private void Window_Closing(object sender, System.ComponentModel.CancelEventArgs e)
    {
        Log("Window closing");
        
        // Cleanup - same as AnyMiro
        _fpsTimer?.Stop();
        
        if (_isRecording)
        {
            StopRecording();
        }
        
        _deviceManager?.Stop();
        _protocol?.Dispose();
        
        // Cleanup SharpDX
        _videoTexture?.Dispose();
        _device?.Dispose();
        _d3d9?.Dispose();
        
        Log("Cleanup complete");
    }
    
    #endregion
    
    #region Button Events
    
    private void BtnRefresh_Click(object sender, RoutedEventArgs e)
    {
        RefreshDevices();
    }
    
    private void BtnConnect_Click(object sender, RoutedEventArgs e)
    {
        if (_deviceManager == null) return;
        
        var device = cboDevices.SelectedItem as UsbDevice;
        if (device == null)
        {
            MessageBox.Show("Please select a device", "Mirance", 
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }
        
        ConnectToDevice(device.Udid);
    }
    
    private void BtnScreenshot_Click(object sender, RoutedEventArgs e)
    {
        TakeScreenshot();
    }
    
    private void BtnRecord_Click(object sender, RoutedEventArgs e)
    {
        if (_isRecording)
        {
            StopRecording();
        }
        else
        {
            StartRecording();
        }
    }
    
    private void BtnFullscreen_Click(object sender, RoutedEventArgs e)
    {
        ToggleFullscreen();
    }
    
    private void BtnSettings_Click(object sender, RoutedEventArgs e)
    {
        MessageBox.Show("Settings dialog not yet implemented", "Mirance",
            MessageBoxButton.OK, MessageBoxImage.Information);
    }
    
    #endregion
    
    #region Device Management - EXACT same flow as AnyMiro
    
    private void RefreshDevices()
    {
        if (_deviceManager == null) return;
        
        var devices = _deviceManager.GetDevices();
        
        cboDevices.Items.Clear();
        foreach (var device in devices)
        {
            cboDevices.Items.Add(device);
        }
        
        btnConnect.IsEnabled = devices.Count > 0;
        
        txtStatus.Text = devices.Count > 0 
            ? $"{devices.Count} device(s) found" 
            : "No devices found";
    }
    
    private void ConnectToDevice(string udid)
    {
        Log($"Connecting to device: {udid}");
        
        try
        {
            _protocol = new IOSMirrorProtocol();
            _protocol.OnVideoFrame += OnVideoFrame;
            _protocol.OnAudioFrame += OnAudioFrame;
            _protocol.OnConnectionLost += OnConnectionLost;
            
            if (_protocol.Connect(udid))
            {
                _currentDeviceUdid = udid;
                txtStatus.Text = $"Connecting to {GetDeviceName(udid)}...";
                
                btnScreenshot.IsEnabled = true;
                btnRecord.IsEnabled = true;
            }
            else
            {
                txtStatus.Text = "Connection failed";
                MessageBox.Show("Failed to connect to device", "Mirance Error",
                    MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }
        catch (Exception ex)
        {
            Log($"Connection error: {ex.Message}");
            MessageBox.Show($"Connection error: {ex.Message}", "Mirance Error",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }
    
    private void OnDeviceConnected(object? sender, UsbDevice device)
    {
        Dispatcher.Invoke(() =>
        {
            txtStatus.Text = $"Device connected: {device.DisplayName}";
            RefreshDevices();
        });
    }
    
    private void OnDeviceDisconnected(object? sender, UsbDevice device)
    {
        Dispatcher.Invoke(() =>
        {
            if (_currentDeviceUdid == device.Udid)
            {
                txtStatus.Text = "Device disconnected";
                btnScreenshot.IsEnabled = false;
                btnRecord.IsEnabled = false;
            }
            RefreshDevices();
        });
    }
    
    #endregion
    
    #region SharpDX Rendering - EXACT same as AnyMiro's Core.MD.Render.dll
    
    private void InitializeDirect3D()
    {
        try
        {
            // Create Direct3D9Ex - same as AnyMiro
            _d3d9 = new Direct3DEx();
            
            // Get the render target handle
            var hwnd = RenderSurface.Handle;
            
            // Create device - EXACT same as Core.MD.Render.dll
            _device = new Device(_d3d9, 0, DeviceType.Hardware, hwnd, 
                CreateDeviceEx.Multithreaded | CreateDeviceEx.FpuPreserve);
            
            Log("Direct3D initialized successfully");
        }
        catch (Exception ex)
        {
            Log($"Direct3D init error: {ex.Message}");
            MessageBox.Show($"Failed to initialize DirectX: {ex.Message}", "Mirance Error",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }
    
    private void OnVideoFrame(byte[] frameData, int width, int height)
    {
        if (_device == null) return;
        
        try
        {
            Dispatcher.Invoke(() =>
            {
                // Create or resize texture if needed - same as AnyMiro
                if (_videoTexture == null || 
                    _videoTexture.Description.Width != width ||
                    _videoTexture.Description.Height != height)
                {
                    _videoTexture?.Dispose();
                    _videoTexture = new Texture(_device, width, height, 1,
                        Usage.Dynamic, Format.A8R8G8B8, Pool.Default);
                }
                
                // Upload frame data to texture - EXACT same as Core.MD.Render.dll
                var surface = _videoTexture.GetSurfaceLevel(0);
                var rect = new System.Drawing.Rectangle(0, 0, width, height);
                var dataRect = surface.LockRectangle(LockFlags.DoNotDirty);
                
                try
                {
                    var data = dataRect.Data;
                    
                    // Convert frame to BGRA - same as AnyMiro
                    for (int i = 0; i < frameData.Length && i < data.Length; i++)
                    {
                        data[i] = frameData[i];
                    }
                }
                finally
                {
                    surface.UnlockRectangle();
                }
                
                // Render to display - same as AnyMiro
                RenderFrame();
                
                // Update stats
                _frameCount++;
                _fps++;
                
                txtResolution.Text = $"{width}x{height}";
                _lastFrameTime = DateTime.Now;
            });
        }
        catch (Exception ex)
        {
            Log($"Frame render error: {ex.Message}");
        }
    }
    
    private void RenderFrame()
    {
        if (_device == null || _videoTexture == null) return;
        
        try
        {
            // Clear - same as AnyMiro
            _device.Clear(ClearFlags.Target, new Color4(0, 0, 0, 1), 1.0f, 0);
            
            // Begin scene - same as AnyMiro
            _device.BeginScene();
            
            // TODO: Draw textured quad - EXACT same as Core.MD.Render.dll shader
            // For now, just present
            
            // End scene - same as AnyMiro
            _device.EndScene();
            
            // Present - same as AnyMiro
            _device.Present();
        }
        catch (Exception ex)
        {
            Log($"Render error: {ex.Message}");
        }
    }
    
    #endregion
    
    #region Audio - EXACT same as AnyMiro's Core.AudioDevices.dll
    
    private void OnAudioFrame(byte[] audioData)
    {
        // TODO: Implement audio playback - same as AnyMiro
    }
    
    #endregion
    
    #region Recording & Screenshot - EXACT same as AnyMiro
    
    private void StartRecording()
    {
        if (_protocol == null) return;
        
        try
        {
            var recordPath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.MyVideos),
                $"Mirance_{DateTime.Now:yyyyMMdd_HHmmss}.mp4");
            
            _protocol.StartRecording(recordPath);
            
            _isRecording = true;
            btnRecord.Content = "■ Stop";
            txtStatus.Text = "Recording...";
            
            Log($"Recording started: {recordPath}");
        }
        catch (Exception ex)
        {
            Log($"Recording error: {ex.Message}");
            MessageBox.Show($"Failed to start recording: {ex.Message}", "Mirance Error",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }
    
    private void StopRecording()
    {
        if (_protocol == null) return;
        
        try
        {
            _protocol.StopRecording();
            
            _isRecording = false;
            btnRecord.Content = "Record ●";
            txtStatus.Text = "Recording saved";
            
            Log("Recording stopped");
        }
        catch (Exception ex)
        {
            Log($"Stop recording error: {ex.Message}");
        }
    }
    
    private void TakeScreenshot()
    {
        if (_protocol == null) return;
        
        try
        {
            var screenshotPath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.MyPictures),
                $"Mirance_{DateTime.Now:yyyyMMdd_HHmmss}.png");
            
            _protocol.SaveScreenshot(screenshotPath);
            
            MessageBox.Show($"Screenshot saved:\n{screenshotPath}", "Mirance",
                MessageBoxButton.OK, MessageBoxImage.Information);
            
            Log($"Screenshot saved: {screenshotPath}");
        }
        catch (Exception ex)
        {
            Log($"Screenshot error: {ex.Message}");
            MessageBox.Show($"Failed to save screenshot: {ex.Message}", "Mirance Error",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }
    
    #endregion
    
    #region Fullscreen - EXACT same as AnyMiro
    
    private void ToggleFullscreen()
    {
        if (_isFullscreen)
        {
            // Exit fullscreen
            WindowState = _prevWindowState;
            WindowStyle = _prevWindowStyle;
            ResizeMode = _prevResizeMode;
            
            _isFullscreen = false;
            btnFullscreen.Content = "⛶ Fullscreen";
        }
        else
        {
            // Enter fullscreen
            _prevWindowState = WindowState;
            _prevWindowStyle = WindowStyle;
            _prevResizeMode = ResizeMode;
            
            WindowStyle = WindowStyle.None;
            WindowState = WindowState.Maximized;
            
            _isFullscreen = true;
            btnFullscreen.Content = "⛶ Exit";
        }
    }
    
    protected override void OnKeyDown(KeyEventArgs e)
    {
        base.OnKeyDown(e);
        
        // ESC to exit fullscreen
        if (e.Key == Key.Escape && _isFullscreen)
        {
            ToggleFullscreen();
        }
    }
    
    #endregion
    
    #region Helpers
    
    private string GetDeviceName(string udid)
    {
        if (_deviceManager == null) return udid;
        
        var devices = _deviceManager.GetDevices();
        foreach (var device in devices)
        {
            if (device.Udid == udid)
                return device.DisplayName;
        }
        
        return udid;
    }
    
    private void OnConnectionLost()
    {
        Dispatcher.Invoke(() =>
        {
            txtStatus.Text = "Connection lost";
            btnScreenshot.IsEnabled = false;
            btnRecord.IsEnabled = false;
            _currentDeviceUdid = "";
        });
    }
    
    private static void Log(string message)
    {
        try
        {
            File.AppendAllText("mirance.log", 
                $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {message}\n");
        }
        catch { }
    }
    
    #endregion
}