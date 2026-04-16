using System;
using System.Windows;
using System.Windows.Forms;

using Mirance.Settings;

namespace Mirance;

/// <summary>
/// Settings Window
/// </summary>
public partial class SettingsWindow : Window
{
    private AppSettings _settings;
    
    public SettingsWindow(AppSettings settings)
    {
        InitializeComponent();
        
        _settings = settings;
        
        // Load current settings
        LoadSettings();
    }
    
    private void LoadSettings()
    {
        // Capture
        cboMaxFPS.SelectedIndex = _settings.MaxFPS switch {
            30 => 0,
            60 => 1,
            120 => 2,
            _ => 1
        };
        
        chkVSync.IsChecked = _settings.VSync;
        chkAutoReconnect.IsChecked = _settings.AutoReconnect;
        chkAutoInstallDriver.IsChecked = _settings.AutoInstallDriver;
        
        // Audio
        chkEnableAudio.IsChecked = _settings.EnableAudio;
        cboSampleRate.SelectedIndex = _settings.AudioSampleRate switch {
            44100 => 0,
            48000 => 1,
            96000 => 2,
            _ => 0
        };
        
        // Display
        chkStartFullscreen.IsChecked = _settings.StartFullscreen;
        chkAlwaysOnTop.IsChecked = _settings.AlwaysOnTop;
        chkShowFPS.IsChecked = _settings.ShowFPS;
        
        // Recording
        cboVideoBitrate.SelectedIndex = _settings.VideoBitrate switch {
            4000000 => 0,
            8000000 => 1,
            16000000 => 2,
            _ => 1
        };
        
        txtRecordPath.Text = _settings.RecordPath;
    }
    
    private void SaveSettings()
    {
        // Capture
        _settings.MaxFPS = cboMaxFPS.SelectedIndex switch {
            0 => 30,
            1 => 60,
            2 => 120,
            _ => 60
        };
        
        _settings.VSync = chkVSync.IsChecked == true;
        _settings.AutoReconnect = chkAutoReconnect.IsChecked == true;
        _settings.AutoInstallDriver = chkAutoInstallDriver.IsChecked == true;
        
        // Audio
        _settings.EnableAudio = chkEnableAudio.IsChecked == true;
        _settings.AudioSampleRate = cboSampleRate.SelectedIndex switch {
            0 => 44100,
            1 => 48000,
            2 => 96000,
            _ => 44100
        };
        
        // Display
        _settings.StartFullscreen = chkStartFullscreen.IsChecked == true;
        _settings.AlwaysOnTop = chkAlwaysOnTop.IsChecked == true;
        _settings.ShowFPS = chkShowFPS.IsChecked == true;
        
        // Recording
        _settings.VideoBitrate = cboVideoBitrate.SelectedIndex switch {
            0 => 4000000,
            1 => 8000000,
            2 => 16000000,
            _ => 8000000
        };
        
        _settings.RecordPath = txtRecordPath.Text;
    }
    
    private void BtnBrowse_Click(object sender, RoutedEventArgs e)
    {
        using var dialog = new FolderBrowserDialog();
        
        if (dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK)
        {
            txtRecordPath.Text = dialog.SelectedPath;
        }
    }
    
    private void BtnSave_Click(object sender, RoutedEventArgs e)
    {
        SaveSettings();
        
        DialogResult = true;
        Close();
    }
    
    private void BtnCancel_Click(object sender, RoutedEventArgs e)
    {
        DialogResult = false;
        Close();
    }
}