using System;
using System.Windows;
using System.IO;
using System.Threading;

namespace Mirance;

/// <summary>
/// Application entry point - EXACT implementation like AnyMiro's App.xaml.cs
/// File: AnyMiro.exe → Mirance.exe
/// </summary>
public partial class App : Application
{
    private static readonly string LogPath = "mirance.log";
    
    protected override void OnStartup(StartupEventArgs e)
    {
        // Init logging first - like AnyMiro
        Log("Application starting...");
        
        // Global exception handlers - EXACT same as AnyMiro
        AppDomain.CurrentDomain.UnhandledException += OnUnhandledException;
        DispatcherUnhandledException += OnDispatcherUnhandledException;
        TaskScheduler.UnobservedTaskException += OnUnobservedTaskException;
        
        base.OnStartup(e);
        
        Log("Application started successfully");
    }
    
    private void OnUnhandledException(object sender, UnhandledExceptionEventArgs e)
    {
        var ex = e.ExceptionObject as Exception;
        LogError("Unhandled exception", ex);
        
        if (e.IsTerminating)
        {
            MessageBox.Show($"Fatal error: {ex?.Message}", "Mirance Error", 
                MessageBoxButton.OK, MessageBoxImage.Error);
            Environment.Exit(1);
        }
    }
    
    private void OnDispatcherUnhandledException(object sender, 
        System.Windows.Threading.DispatcherUnhandledExceptionEventArgs e)
    {
        LogError("Dispatcher exception", e.Exception);
        e.Handled = true;
        
        MessageBox.Show($"Error: {e.Exception.Message}", "Mirance Error",
            MessageBoxButton.OK, MessageBoxImage.Warning);
    }
    
    private void OnUnobservedTaskException(object? sender, UnobservedTaskExceptionEventArgs e)
    {
        LogError("Unobserved task exception", e.Exception);
        e.SetObserved();
    }
    
    private static void Log(string message)
    {
        try
        {
            File.AppendAllText(LogPath, $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {message}\n");
        }
        catch { }
    }
    
    private static void LogError(string source, Exception? ex)
    {
        if (ex == null) return;
        
        try
        {
            File.AppendAllText(LogPath, 
                $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] ERROR {source}: {ex.Message}\n{ex.StackTrace}\n");
        }
        catch { }
    }
}