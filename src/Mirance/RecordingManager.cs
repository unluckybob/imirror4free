using System;
using System.IO;
using System.Diagnostics;

using Serilog;

namespace Mirance;

/// <summary>
/// Recording Manager - Handles video/audio recording with FFmpeg
/// 
/// Uses FFMpegCore for encoding to MP4/H.264
/// </summary>
public class RecordingManager : IDisposable
{
    private string _outputPath;
    private bool _running;
    private DateTime _startTime;
    private int _width;
    private int _height;
    private int _frameCount;
    private long _totalBytes;
    
    private Process? _ffmpegProcess;
    private FileStream? _videoStream;
    private FileStream? _audioStream;
    
    public RecordingManager(string outputPath)
    {
        _outputPath = outputPath;
    }
    
    public void Start(int width = 1920, int height = 1080, int videoBitrate = 8000000, int audioBitrate = 128000)
    {
        try
        {
            _width = width;
            _height = height;
            
            // Ensure output directory
            var dir = Path.GetDirectoryName(_outputPath);
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
            {
                Directory.CreateDirectory(dir);
            }
            
            // Try to use FFMpegCore if available
            if (TryStartFFmpeg(videoBitrate, audioBitrate))
            {
                _running = true;
                _startTime = DateTime.Now;
                
                Log.Information("Recording started (FFmpeg): {Path}", _outputPath);
                return;
            }
            
            // Fallback to raw file recording
            StartRawRecording();
            
            _running = true;
            _startTime = DateTime.Now;
            
            Log.Information("Recording started (raw): {Path}", _outputPath);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Recording start failed");
            throw;
        }
    }
    
    private bool TryStartFFmpeg(int videoBitrate, int audioBitrate)
    {
        try
        {
            // Check if FFmpeg is available
            var ffmpegPath = FindFFmpeg();
            if (string.IsNullOrEmpty(ffmpegPath))
            {
                Log.Debug("FFmpeg not found, using raw recording");
                return false;
            }
            
            // Build FFmpeg arguments
            var args = $"-f rawvideo -pix_fmt bgra -s {_width}x{height} -r 60 -i - " +
                     $"-f s16le -ar 44100 -ac 2 -i - " +
                     $"-c:v libx264 -preset ultrafast -b:v {videoBitrate} " +
                     $"-c:a aac -b:a {audioBitrate} " +
                     $"-y \"{_outputPath}\"";
            
            // Start FFmpeg process
            _ffmpegProcess = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = ffmpegPath,
                    Arguments = args,
                    UseShellExecute = false,
                    RedirectStandardInput = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true
                }
            };
            
            _ffmpegProcess.Start();
            
            return true;
        }
        catch (Exception ex)
        {
            Log.Warning(ex, "FFmpeg start failed");
            return false;
        }
    }
    
    private string? FindFFmpeg()
    {
        // Check common locations
        var locations = new[]
        {
            "ffmpeg",
            "ffmpeg.exe",
            Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "ffmpeg.exe"),
            @"C:\ffmpeg\bin\ffmpeg.exe",
            @"C:\Program Files\ffmpeg\bin\ffmpeg.exe"
        };
        
        foreach (var loc in locations)
        {
            try
            {
                var testProcess = new Process
                {
                    StartInfo = new ProcessStartInfo
                    {
                        FileName = loc,
                        Arguments = "-version",
                        UseShellExecute = false,
                        RedirectStandardOutput = true,
                        CreateNoWindow = true
                    }
                };
                
                if (testProcess.Start())
                {
                    testProcess.WaitForExit(1000);
                    if (testProcess.ExitCode == 0)
                    {
                        return loc;
                    }
                }
            }
            catch { }
        }
        
        return null;
    }
    
    private void StartRawRecording()
    {
        _videoStream = new FileStream(_outputPath + ".video", 
            FileMode.Create, FileAccess.Write);
        
        _audioStream = new FileStream(_outputPath + ".audio",
            FileMode.Create, FileAccess.Write);
    }
    
    public void WriteVideoFrame(byte[] data)
    {
        if (!_running) return;
        
        try
        {
            _frameCount++;
            _totalBytes += data.Length;
            
            if (_ffmpegProcess != null && !_ffmpegProcess.HasExited)
            {
                _ffmpegProcess.StandardInput.BaseStream.Write(data, 0, data.Length);
            }
            else if (_videoStream != null)
            {
                _videoStream.Write(data, 0, data.Length);
            }
        }
        catch (Exception ex)
        {
            Log.Warning(ex, "Video write error");
        }
    }
    
    public void WriteAudioFrame(byte[] data)
    {
        if (!_running) return;
        
        try
        {
            if (_ffmpegProcess != null && !_ffmpegProcess.HasExited)
            {
                _ffmpegProcess.StandardInput.BaseStream.Write(data, 0, data.Length);
            }
            else if (_audioStream != null)
            {
                _audioStream.Write(data, 0, data.Length);
            }
        }
        catch (Exception ex)
        {
            Log.Warning(ex, "Audio write error");
        }
    }
    
    public void Stop()
    {
        _running = false;
        
        try
        {
            if (_ffmpegProcess != null)
            {
                _ffmpegProcess.StandardInput.Close();
                _ffmpegProcess.WaitForExit(10000);
                _ffmpegProcess.Dispose();
                _ffmpegProcess = null;
            }
            
            _videoStream?.Close();
            _audioStream?.Close();
            
            var duration = DateTime.Now - _startTime;
            var bitrate = _totalBytes * 8 / duration.TotalSeconds;
            
            Log.Information("Recording stopped: {Frames} frames, {Duration}s, {Bitrate} bps",
                _frameCount, duration.TotalSeconds, bitrate);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Recording stop failed");
        }
    }
    
    public int FrameCount => _frameCount;
    public long TotalBytes => _totalBytes;
    public TimeSpan Duration => _running ? DateTime.Now - _startTime : TimeSpan.Zero;
    
    public void Dispose()
    {
        Stop();
        
        _videoStream?.Dispose();
        _audioStream?.Dispose();
    }
}