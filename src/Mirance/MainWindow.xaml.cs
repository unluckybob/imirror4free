using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Threading;
using System.IO;
using System.Threading;
using System.Collections.Generic;

using Serilog;

using SharpDX;
using SharpDX.Direct3D9;

using Mirance.Usb;
using Mirance.Protocol;
using Mirance.Render;
using Mirance.Audio;
using Mirance.Settings;

namespace Mirance;

/// <summary>
/// Main Window - EXACT implementation like AnyMiro's MainWindow.xaml.cs
/// 
/// Handles:
/// - Device detection and connection
/// - SharpDX Direct3D9 rendering
/// - Recording and screenshot
/// - Audio playback
/// </summary>
public partial class MainWindow : Window
{
    #region Fields
    
    private DeviceManager? _deviceManager;
    private IOSMirrorProtocol? _protocol;
    private Direct3DRenderer? _renderer;
    private AudioPlayer? _audioPlayer;
    private RecordingManager? _recordingManager;
    private AppSettings _settings;
    
    private bool _isConnected;
    private bool _isRecording;
    private bool _isFullscreen;
    private string _currentDeviceUdid = "";
    
    private DateTime _lastFrameTime;
    private int _frameCount;
    private int _fps;
    private int _fpsAccumulator;
    private DateTime _fpsLastUpdate;
    
    private DispatcherTimer? _fpsTimer;
    private DispatcherTimer? _statusTimer;
    
    private WindowState _prevWindowState;
    private WindowStyle _prevWindowStyle;
    private ResizeMode _prevResizeMode;
    
    #endregion
    
    public MainWindow()
    {
        InitializeComponent();
        
        _settings = AppSettings.Load();
        
        // Setup FPS counter - same as AnyMiro
        _fpsTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _fpsTimer.Tick += FpsTimer_Tick;
        
        // Setup periodic status updates
        _statusTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(2) };
        _statusTimer.Tick += StatusTimer_Tick;
        
        Log.Information("MainWindow initialized");
    }
    
    #region Window Events
    
    private void Window_Loaded(object sender, RoutedEventArgs e)
    {
        Log.Information("Window loaded");
        
        try
        {
            // Initialize renderer - EXACT same as Core.MD.Render.dll
            _renderer = new Direct3DRenderer();
            
            // Initialize audio player - EXACT same as Core.AudioDevices.dll
            _audioPlayer = new AudioPlayer();
            
            // Initialize device manager - EXACT same as Core.Connection.dll
            _deviceManager = new DeviceManager();
            _deviceManager.DeviceConnected += DeviceManager_DeviceConnected;
            _deviceManager.DeviceDisconnected += DeviceManager_DeviceDisconnected;
            _deviceManager.Start();
            
            // Start status timer
            _statusTimer!.Start();
            
            // Initial device scan
            RefreshDevices();
            
            Log.Information("Initialization complete");
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Initialization failed");
            MessageBox.Show($"Initialization failed: {ex.Message}", "Mirance Error",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }
    
    private void Window_Closing(object sender, System.ComponentModel.CancelEventArgs e)
    {
        Log.Information("Window closing");
        
        // Stop timers
        _fpsTimer?.Stop();
        _statusTimer?.Stop();
        
        // Stop recording if active
        if (_isRecording)
        {
            StopRecording();
        }
        
        // Disconnect if connected
        if (_isConnected)
        {
            Disconnect();
        }
        
        // Cleanup
        _deviceManager?.Stop();
        _deviceManager?.Dispose();
        
        _protocol?.Dispose();
        _renderer?.Dispose();
        _audioPlayer?.Dispose();
        _recordingManager?.Dispose();
        
        // Save settings
        _settings.Save();
        
        Log.Information("Cleanup complete");
    }
    
    private void Window_KeyDown(object sender, KeyEventArgs e)
    {
        // ESC to exit fullscreen
        if (e.Key == Key.Escape && _isFullscreen)
        {
            ToggleFullscreen();
        }
        
        // F for fullscreen
        if (e.Key == Key.F && Keyboard.Modifiers == ModifierKeys.Control)
        {
            ToggleFullscreen();
        }
        
        // S for screenshot
        if (e.Key == Key.S && Keyboard.Modifiers == ModifierKeys.Control)
        {
            TakeScreenshot();
        }
        
        // R for record toggle
        if (e.Key == Key.R && Keyboard.Modifiers == ModifierKeys.Control)
        {
            ToggleRecording();
        }
    }
    
    #endregion
    
    #region Device Management
    
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
        
        UpdateStatus(devices.Count > 0 ? $"{devices.Count} device(s) found" : "No devices");
    }
    
    private void CboDevices_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        btnConnect.IsEnabled = cboDevices.SelectedItem != null;
    }
    
    private void BtnRefresh_Click(object sender, RoutedEventArgs e)
    {
        RefreshDevices();
    }
    
    private void BtnConnect_Click(object sender, RoutedEventArgs e)
    {
        if (_isConnected)
        {
            Disconnect();
        }
        else
        {
            Connect();
        }
    }
    
    private void Connect()
    {
        if (_deviceManager == null || cboDevices.SelectedItem == null)
        {
            MessageBox.Show("Please select a device", "Mirance",
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }
        
        var device = cboDevices.SelectedItem as UsbDeviceInfo;
        if (device == null) return;
        
        Log.Information("Connecting to device: {Udid}", device.Udid);
        
        try
        {
            // Disable connect button during connection
            btnConnect.IsEnabled = false;
            btnScreenshot.IsEnabled = false;
            btnRecord.IsEnabled = false;
            UpdateStatus($"Connecting to {device.DisplayName}...");
            
            // Create protocol handler
            _protocol = new IOSMirrorProtocol();
            _protocol.OnVideoFrame += Protocol_OnVideoFrame;
            _protocol.OnAudioFrame += Protocol_OnAudioFrame;
            _protocol.OnConnectionLost += Protocol_OnConnectionLost;
            _protocol.OnError += Protocol_OnError;
            
            // Connect to device
            if (_protocol.Connect(device.Udid))
            {
                _isConnected = true;
                _currentDeviceUdid = device.Udid;
                
                // Update UI
                btnConnect.Content = "Disconnect";
                btnScreenshot.IsEnabled = true;
                btnRecord.IsEnabled = true;
                
                // Start FPS counter
                _fpsTimer!.Start();
                _fpsLastUpdate = DateTime.Now;
                
                UpdateStatus($"Connected to {device.DisplayName}");
                Log.Information("Connected to {Udid}", device.Udid);
            }
            else
            {
                UpdateStatus("Connection failed");
                MessageBox.Show("Failed to connect to device", "Mirance Error",
                    MessageBoxButton.OK, MessageBoxImage.Error);
                btnConnect.IsEnabled = true;
            }
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Connection error");
            UpdateStatus("Connection error");
            MessageBox.Show($"Connection error: {ex.Message}", "Mirance Error",
                MessageBoxButton.OK, MessageBoxImage.Error);
            btnConnect.IsEnabled = true;
        }
    }
    
    private void Disconnect()
    {
        Log.Information("Disconnecting");
        
        // Stop recording if active
        if (_isRecording)
        {
            StopRecording();
        }
        
        // Disconnect protocol
        _protocol?.Dispose();
        _protocol = null;
        
        _isConnected = false;
        _currentDeviceUdid = "";
        
        // Stop FPS counter
        _fpsTimer?.Stop();
        
        // Update UI
        btnConnect.Content = "Connect";
        btnScreenshot.IsEnabled = false;
        btnRecord.IsEnabled = false;
        txtFPS.Text = "";
        txtResolution.Text = "";
        txtBitrate.Text = "";
        
        UpdateStatus("Disconnected");
    }
    
    private void DeviceManager_DeviceConnected(object? sender, UsbDeviceInfo device)
    {
        Dispatcher.Invoke(() =>
        {
            UpdateStatus($"Device connected: {device.DisplayName}");
            RefreshDevices();
        });
    }
    
    private void DeviceManager_DeviceDisconnected(object? sender, UsbDeviceInfo device)
    {
        Dispatcher.Invoke(() =>
        {
            if (_currentDeviceUdid == device.Udid)
            {
                UpdateStatus("Device disconnected");
                Disconnect();
            }
            RefreshDevices();
        });
    }
    
    #endregion
    
    #region Protocol Events
    
    private void Protocol_OnVideoFrame(byte[] frameData, int width, int height)
    {
        try
        {
            Dispatcher.Invoke(() =>
            {
                // Update frame count
                _frameCount++;
                _fpsAccumulator++;
                
                // Update resolution display
                if (string.IsNullOrEmpty(txtResolution.Text))
                {
                    txtResolution.Text = $"{width}x{height}";
                }
                
                // Render frame via SharpDX
                _renderer?.RenderFrame(frameData, width, height);
                
                // Record if needed
                _recordingManager?.WriteVideoFrame(frameData);
            });
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Video frame error");
        }
    }
    
    private void Protocol_OnAudioFrame(byte[] audioData)
    {
        try
        {
            Dispatcher.Invoke(() =>
            {
                // Play audio
                if (chkAudio.IsChecked == true)
                {
                    _audioPlayer?.PlayAudio(audioData);
                }
                
                // Record if needed
                _recordingManager?.WriteAudioFrame(audioData);
            });
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Audio frame error");
        }
    }
    
    private void Protocol_OnConnectionLost()
    {
        Dispatcher.Invoke(() =>
        {
            Log.Warning("Connection lost");
            UpdateStatus("Connection lost");
            
            _isConnected = false;
            btnConnect.Content = "Connect";
            btnScreenshot.IsEnabled = false;
            btnRecord.IsEnabled = false;
            
            // Try to reconnect
            if (!string.IsNullOrEmpty(_currentDeviceUdid))
            {
                Log.Information("Attempting to reconnect...");
                Thread.Sleep(1000);
                Connect();
            }
        });
    }
    
    private void Protocol_OnError(string error)
    {
        Dispatcher.Invoke(() =>
        {
            Log.Error("Protocol error: {Error}", error);
        });
    }
    
    #endregion
    
    #region Recording & Screenshot
    
    private void BtnScreenshot_Click(object sender, RoutedEventArgs e)
    {
        TakeScreenshot();
    }
    
    private void TakeScreenshot()
    {
        if (_protocol == null || !_isConnected) return;
        
        try
        {
            var screenshotsFolder = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.MyPictures),
                "Mirance");
            
            if (!Directory.Exists(screenshotsFolder))
            {
                Directory.CreateDirectory(screenshotsFolder);
            }
            
            var screenshotPath = Path.Combine(screenshotsFolder,
                $"Mirance_{DateTime.Now:yyyyMMdd_HHmmss}.png");
            
            _renderer?.SaveScreenshot(screenshotPath);
            
            // Open the screenshot
            System.Diagnostics.Process.Start("explorer.exe", $"/select,\"{screenshotPath}\"");
            
            Log.Information("Screenshot saved: {Path}", screenshotPath);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Screenshot failed");
            MessageBox.Show($"Screenshot failed: {ex.Message}", "Mirance Error",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }
    
    private void BtnRecord_Click(object sender, RoutedEventArgs e)
    {
        ToggleRecording();
    }
    
    private void ToggleRecording()
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
    
    private void StartRecording()
    {
        if (_protocol == null || !_isConnected) return;
        
        try
        {
            var videosFolder = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.MyVideos),
                "Mirance");
            
            if (!Directory.Exists(videosFolder))
            {
                Directory.CreateDirectory(videosFolder);
            }
            
            var recordingPath = Path.Combine(videosFolder,
                $"Mirance_{DateTime.Now:yyyyMMdd_HHmmss}.mp4");
            
            _recordingManager = new RecordingManager(recordingPath);
            _recordingManager.Start();
            
            _isRecording = true;
            btnRecord.Content = "■ Stop";
            UpdateStatus("Recording...");
            
            Log.Information("Recording started: {Path}", recordingPath);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Recording start failed");
            MessageBox.Show($"Recording failed: {ex.Message}", "Mirance Error",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }
    
    private void StopRecording()
    {
        if (_recordingManager == null) return;
        
        try
        {
            _recordingManager.Stop();
            _recordingManager.Dispose();
            _recordingManager = null;
            
            _isRecording = false;
            btnRecord.Content = "Record ●";
            UpdateStatus("Recording saved");
            
            Log.Information("Recording stopped");
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Recording stop failed");
        }
    }
    
    #endregion
    
    #region Fullscreen
    
    private void BtnFullscreen_Click(object sender, RoutedEventArgs e)
    {
        ToggleFullscreen();
    }
    
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
    
    #endregion
    
    #region Settings
    
    private void BtnSettings_Click(object sender, RoutedEventArgs e)
    {
        var settingsWindow = new SettingsWindow(_settings);
        settingsWindow.Owner = this;
        
        if (settingsWindow.ShowDialog() == true)
        {
            _settings.Save();
            Log.Information("Settings updated");
        }
    }
    
    #endregion
    
    #region Timers
    
    private void FpsTimer_Tick(object? sender, EventArgs e)
    {
        var elapsed = (DateTime.Now - _fpsLastUpdate).TotalSeconds;
        if (elapsed > 0)
        {
            _fps = (int)(_fpsAccumulator / elapsed);
            _fpsAccumulator = 0;
            _fpsLastUpdate = DateTime.Now;
        }
        
        txtFPS.Text = $"{_fps} FPS";
    }
    
    private void StatusTimer_Tick(object? sender, EventArgs e)
    {
        if (_deviceManager != null && !_isConnected)
        {
            RefreshDevices();
        }
    }
    
    #endregion
    
    #region Helpers
    
    private void UpdateStatus(string status)
    {
        txtStatus.Text = status;
    }
    
    #endregion
}