using System;
using System.IO;

using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

using Serilog;

namespace Mirance.Settings;

/// <summary>
/// Application Settings - Same format as AnyMiro's appsettings.json
/// </summary>
public class AppSettings
{
    private static readonly string SettingsPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "Mirance", "settings.json");
    
    // Capture settings
    public string CaptureBackend { get; set; } = "auto";
    public int MaxFPS { get; set; } = 60;
    public bool VSync { get; set; } = true;
    public bool EnableAudio { get; set; } = true;
    public int AudioSampleRate { get; set; } = 44100;
    public int AudioChannels { get; set; } = 2;
    
    // Display settings
    public bool StartFullscreen { get; set; } = false;
    public bool AlwaysOnTop { get; set; } = false;
    public bool ShowFPS { get; set; } = false;
    
    // Recording settings
    public string RecordPath { get; set; } = "";
    public string VideoCodec { get; set; } = "h264";
    public string AudioCodec { get; set; } = "aac";
    public int VideoBitrate { get; set; } = 8000000;
    public int AudioBitrate { get; set; } = 128000;
    
    // Network settings
    public bool AutoReconnect { get; set; } = true;
    public int ReconnectDelay { get; set; } = 3000;
    public int KeepAliveInterval { get; set; } = 5000;
    
    // Driver settings
    public bool AutoInstallDriver { get; set; } = true;
    
    public static AppSettings Load()
    {
        try
        {
            if (File.Exists(SettingsPath))
            {
                var json = File.ReadAllText(SettingsPath);
                var settings = JsonConvert.DeserializeObject<AppSettings>(json);
                
                if (settings != null)
                {
                    Log.Debug("Settings loaded");
                    return settings;
                }
            }
        }
        catch (Exception ex)
        {
            Log.Warning(ex, "Failed to load settings, using defaults");
        }
        
        // Return default settings
        var defaultSettings = new AppSettings();
        defaultSettings.RecordPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyVideos),
            "Mirance");
        
        return defaultSettings;
    }
    
    public void Save()
    {
        try
        {
            var dir = Path.GetDirectoryName(SettingsPath);
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
            {
                Directory.CreateDirectory(dir);
            }
            
            var json = JsonConvert.SerializeObject(this, Formatting.Indented);
            File.WriteAllText(SettingsPath, json);
            
            Log.Debug("Settings saved");
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Failed to save settings");
        }
    }
}