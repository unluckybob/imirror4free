using System;
using System.IO;

using Serilog;

namespace Mirance;

/// <summary>
/// Recording Manager - Handles video/audio recording
/// </summary>
public class RecordingManager : IDisposable
{
    private FileStream? _videoStream;
    private FileStream? _audioStream;
    private string _outputPath;
    private bool _running;
    private DateTime _startTime;
    
    public RecordingManager(string outputPath)
    {
        _outputPath = outputPath;
    }
    
    public void Start()
    {
        try
        {
            // Create output file
            _videoStream = new FileStream(_outputPath + ".video", 
                FileMode.Create, FileAccess.Write);
            
            _audioStream = new FileStream(_outputPath + ".audio",
                FileMode.Create, FileAccess.Write);
            
            _running = true;
            _startTime = DateTime.Now;
            
            // TODO: Use FFMpegCore to encode to MP4
            
            Log.Information("Recording started: {Path}", _outputPath);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Recording start failed");
            throw;
        }
    }
    
    public void WriteVideoFrame(byte[] data)
    {
        if (!_running || _videoStream == null) return;
        
        try
        {
            _videoStream.Write(data, 0, data.Length);
        }
        catch (Exception ex)
        {
            Log.Warning(ex, "Video write error");
        }
    }
    
    public void WriteAudioFrame(byte[] data)
    {
        if (!_running || _audioStream == null) return;
        
        try
        {
            _audioStream.Write(data, 0, data.Length);
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
            _videoStream?.Close();
            _audioStream?.Close();
            
            // TODO: Combine with FFMpeg
            
            Log.Information("Recording stopped");
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Recording stop failed");
        }
    }
    
    public void Dispose()
    {
        Stop();
        
        _videoStream?.Dispose();
        _audioStream?.Dispose();
    }
}