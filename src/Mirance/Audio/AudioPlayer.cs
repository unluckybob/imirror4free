using System;
using System.IO;

using NAudio.Wave;

using Serilog;

namespace Mirance.Audio;

/// <summary>
/// Audio Player - EXACT same as AnyMiro's Core.AudioDevices.dll
/// 
/// Uses NAudio for audio playback
/// </summary>
public class AudioPlayer : IDisposable
{
    private WaveOutEvent? _waveOut;
    private BufferedWaveProvider? _waveProvider;
    private int _sampleRate = 44100;
    private int _channels = 2;
    
    public AudioPlayer()
    {
        try
        {
            // Create buffered wave provider
            _waveProvider = new BufferedWaveProvider(WaveFormat.CreateIeeeFloatWaveFormat(_sampleRate, _channels));
            _waveProvider.BufferLength = _sampleRate * _channels * 4 * 10;  // 10 seconds buffer
            _waveProvider.BufferDuration = TimeSpan.FromSeconds(10);
            
            // Create wave out
            _waveOut = new WaveOutEvent();
            _waveOut.Init(_waveProvider);
            _waveOut.Play();
            
            Log.Information("Audio player initialized: {Rate}Hz, {Channels}ch", _sampleRate, _channels);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Audio player init failed");
        }
    }
    
    public void PlayAudio(byte[] audioData)
    {
        if (_waveProvider == null) return;
        
        try
        {
            // Add audio data to buffer
            _waveProvider.AddSamples(audioData, 0, audioData.Length);
        }
        catch (Exception ex)
        {
            Log.Warning(ex, "Audio play error");
        }
    }
    
    public void SetFormat(int sampleRate, int channels)
    {
        _sampleRate = sampleRate;
        _channels = channels;
        
        // Recreate with new format
        _waveOut?.Stop();
        _waveProvider = new BufferedWaveProvider(WaveFormat.CreateIeeeFloatWaveFormat(_sampleRate, _channels));
        
        if (_waveOut != null)
        {
            _waveOut.Init(_waveProvider);
            _waveOut.Play();
        }
        
        Log.Information("Audio format changed: {Rate}Hz, {Channels}ch", _sampleRate, _channels);
    }
    
    public void Dispose()
    {
        _waveOut?.Stop();
        _waveOut?.Dispose();
        
        Log.Debug("Audio player disposed");
    }
}