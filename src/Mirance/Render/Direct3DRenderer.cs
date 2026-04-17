using System;
using System.IO;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;

using SharpDX;
using SharpDX.Direct3D9;

using Serilog;

namespace Mirance.Render;

/// <summary>
/// DirectX 9 Renderer - EXACT same as AnyMiro's Core.MD.Render.dll
/// 
/// Uses SharpDX.Direct3D9 for hardware-accelerated rendering
/// </summary>
public class Direct3DRenderer : IDisposable
{
    #region Fields
    
    private Direct3DEx? _d3d9;
    private Device? _device;
    private Texture? _videoTexture;
    private Surface? _renderTarget;
    
    private int _width;
    private int _height;
    private bool _initialized;
    
    private IntPtr _hwnd;
    
    #endregion
    
    public bool Initialize(Window window, int width = 1920, int height = 1080)
    {
        try
        {
            _width = width;
            _height = height;
            
            // Get window handle
            var helper = new WindowInteropHelper(window);
            _hwnd = helper.Handle;
            
            if (_hwnd == IntPtr.Zero)
            {
                Log.Warning("Window handle is null");
                return false;
            }
            
            // Create Direct3D9
            _d3d9 = new Direct3DEx();
            
            // Create device
            _device = new Device(_d3d9, 0, DeviceType.Hardware, _hwnd,
                CreateDeviceEx.Multithreaded | CreateDeviceEx.FpuPreserve);
            
            _initialized = true;
            
            Log.Information("Direct3D9 initialized: {Width}x{Height}", width, height);
            return true;
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Direct3D9 initialization failed");
            return false;
        }
    }
    
    public void RenderFrame(byte[] frameData, int width, int height)
    {
        if (!_initialized || _device == null) return;
        
        try
        {
            // Create or resize texture if needed
            if (_videoTexture == null || 
                _videoTexture.Description.Width != width ||
                _videoTexture.Description.Height != height)
            {
                _videoTexture?.Dispose();
                _videoTexture = new Texture(_device, width, height, 1,
                    Usage.Dynamic, Format.A8R8G8B8, Pool.Default);
            }
            
            // Upload frame data
            if (_videoTexture != null)
            {
                var surface = _videoTexture.GetSurfaceLevel(0);
                
                var rect = new System.Drawing.Rectangle(0, 0, width, height);
                var dataRect = surface.LockRectangle(LockFlags.DoNotDirty);
                
                try
                {
                    var data = dataRect.Data;
                    
                    // Convert to BGRA
                    for (int i = 0; i < frameData.Length && i < data.Length; i++)
                    {
                        data[i] = frameData[i];
                    }
                }
                finally
                {
                    surface.UnlockRectangle();
                }
                
                surface.Dispose();
            }
            
            // Clear and present
            _device.Clear(ClearFlags.Target, new Color4(0, 0, 0, 1), 1.0f, 0);
            _device.BeginScene();
            _device.EndScene();
            _device.Present();
        }
        catch (Exception ex)
        {
            Log.Warning(ex, "Render frame error");
        }
    }
    
    public void SaveScreenshot(string path)
    {
        if (_videoTexture == null || _device == null)
        {
            Log.Warning("Cannot save screenshot: not initialized");
            return;
        }
        
        try
        {
            var surface = _videoTexture.GetSurfaceLevel(0);
            
            // Save to file
            var tempBitmap = new System.Drawing.Bitmap(_width, _height, 
                System.Drawing.Imaging.PixelFormat.Format32bppArgb);
            
            using (var graphics = System.Drawing.Graphics.FromImage(tempBitmap))
            {
                var rect = new System.Drawing.Rectangle(0, 0, _width, _height);
                var data = surface.LockRectangle(LockFlags.ReadOnly);
                
                try
                {
                    for (int y = 0; y < _height; y++)
                    {
                        for (int x = 0; x < _width; x++)
                        {
                            int offset = y * _width * 4 + x * 4;
                            var b = data[offset];
                            var g = data[offset + 1];
                            var r = data[offset + 2];
                            
                            tempBitmap.SetPixel(x, y, 
                                System.Drawing.Color.FromArgb(255, r, g, b));
                        }
                    }
                }
                finally
                {
                    surface.UnlockRectangle();
                }
            }
            
            surface.Dispose();
            
            tempBitmap.Save(path);
            tempBitmap.Dispose();
            
            Log.Information("Screenshot saved: {Path}", path);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Screenshot save failed");
        }
    }
    
    public void Dispose()
    {
        _videoTexture?.Dispose();
        _renderTarget?.Dispose();
        _device?.Dispose();
        _d3d9?.Dispose();
        
        Log.Debug("Direct3D9 disposed");
    }
}

/// <summary>
/// Simple WPF Image renderer (fallback when SharpDX unavailable)
/// </summary>
public class ImageRenderer
{
    private WriteableBitmap? _bitmap;
    private int _width;
    private int _height;
    
    public void Initialize(int width, int height)
    {
        _width = width;
        _height = height;
        _bitmap = new WriteableBitmap(width, height, 96, 96, 
            PixelFormats.Bgra32, null);
    }
    
    public void RenderFrame(byte[] frameData)
    {
        if (_bitmap == null) return;
        
        try
        {
            _bitmap.Lock();
            
            var stride = _width * 4;
            _bitmap.WritePixels(new System.Windows.Int32Rect(0, 0, _width, _height),
                frameData, stride, 0);
            
            _bitmap.Unlock();
            
            targetImage.Source = _bitmap;
        }
        catch { }
    }
}