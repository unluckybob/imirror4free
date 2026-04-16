using System;
using System.Threading;
using System.Windows;

using Serilog;

namespace Mirance.Usb;

/// <summary>
/// iOS Trust Checker - Checks if device trusts this computer
/// 
/// Critical: iOS devices show a "Trust this computer?" dialog that
/// must be answered on the device before mirroring works.
/// </summary>
public class TrustChecker
{
    #region Constants
    
    // How long to wait for trust prompt (seconds)
    public const int TrustCheckTimeout = 30;
    
    // How often to poll device state
    public const int TrustCheckInterval = 1000;
    
    #endregion
    
    #region Events
    
    public event Action<TrustState>? OnTrustStateChanged;
    
    #endregion
    
    #region Fields
    
    private Thread? _checkThread;
    private bool _running;
    private string _currentDeviceUdid = "";
    private TrustState _currentState = TrustState.Unknown;
    
    #endregion
    
    #region Public Methods
    
    public void Start(string udid)
    {
        if (_running) return;
        
        _currentDeviceUdid = udid;
        _running = true;
        
        _checkThread = new Thread(CheckLoop)
        {
            IsBackground = true,
            Name = "TrustCheck"
        };
        _checkThread.Start();
        
        Log.Information("Trust checker started for {Udid}", udid);
    }
    
    public void Stop()
    {
        _running = false;
        
        _checkThread?.Join(2000);
        
        Log.Information("Trust checker stopped");
    }
    
    public TrustState GetCurrentState()
    {
        return _currentState;
    }
    
    #endregion
    
    #region Trust Check Loop
    
    private void CheckLoop()
    {
        Log.Debug("Trust check loop started");
        
        var timeout = DateTime.Now.AddSeconds(TrustCheckTimeout);
        
        while (_running && DateTime.Now < timeout)
        {
            try
            {
                // Try to query device trust state via Lockdown
                var state = CheckDeviceTrust(_currentDeviceUdid);
                
                if (state != _currentState)
                {
                    _currentState = state;
                    OnTrustStateChanged?.Invoke(state);
                    
                    Log.Information("Trust state changed: {State}", state);
                }
                
                // If trusted, we're done waiting
                if (state == TrustState.Trusted)
                {
                    break;
                }
            }
            catch (Exception ex)
            {
                Log.Warning(ex, "Trust check error");
            }
            
            Thread.Sleep(TrustCheckInterval);
        }
        
        Log.Debug("Trust check loop stopped");
    }
    
    private TrustState CheckDeviceTrust(string udid)
    {
        try
        {
            // Try to connect via lockdown without pairing
            // If succeeds, device is trusted
            
            // In practice, this would use LibUsbDotNet to query
            // the usbmuxd service for trust state
            
            // For now, assume we need to check manually
            return TrustState.NeedPrompt;
        }
        catch
        {
            return TrustState.Unknown;
        }
    }
    
    #endregion
    
    #region Static Methods
    
    /// <summary>
    /// Show trust prompt dialog to user
    /// </summary>
    public static void ShowTrustPrompt()
    {
        Application.Current.Dispatcher.Invoke(() =>
        {
            MessageBox.Show(
                "Please unlock your iPhone and tap 'Trust' on the prompt.\n\n" +
                "Then click OK to continue.",
                "Trust Computer",
                MessageBoxButton.OK,
                MessageBoxImage.Information);
        });
    }
    
    /// <summary>
    /// Show device locked dialog
    /// </summary>
    public static void ShowDeviceLocked()
    {
        Application.Current.Dispatcher.Invoke(() =>
        {
            MessageBox.Show(
                "Your iPhone is locked.\n\n" +
                "Please unlock your iPhone and tap 'Trust' if prompted.",
                "iPhone Locked",
                MessageBoxButton.OK,
                MessageBoxImage.Warning);
        });
    }
    
    #endregion
}

/// <summary>
/// Trust state
/// </summary>
public enum TrustState
{
    Unknown,
    NeedPrompt,      // User needs to tap Trust on device
    Untrusted,       // Device doesn't trust this computer
    Trusted,        // Device trusts this computer
    DeviceLocked    // iPhone is locked
}