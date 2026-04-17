using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Threading;

using Serilog;

namespace Mirance;

/// <summary>
/// Application entry point - EXACT implementation like AnyMiro's App.xaml.cs
/// </summary>
public partial class App : Application
{
    private static readonly string LogPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "Mirance", "logs", "mirance.log");
    
    protected override void OnStartup(StartupEventArgs e)
    {
        // Ensure log directory exists
        var logDir = Path.GetDirectoryName(LogPath);
        if (!string.IsNullOrEmpty(logDir) && !Directory.Exists(logDir))
        {
            Directory.CreateDirectory(logDir);
        }
        
        // Configure Serilog - same as Core.Tracing.dll
        Log.Logger = new LoggerConfiguration()
            .MinimumLevel.Debug()
            .WriteTo.File(LogPath,
                rollingInterval: RollingInterval.Day,
                retainedFileCountLimit: 7,
                outputTemplate: "{Timestamp:yyyy-MM-dd HH:mm:ss.fff} [{Level:u3}] {Message:lj}{NewLine}{Exception}")
            .CreateLogger();
        
        Log.Information("=== Mirance starting ===");
        
        // Global exception handlers - EXACT same as AnyMiro
        AppDomain.CurrentDomain.UnhandledException += OnUnhandledException;
        TaskScheduler.UnobservedTaskException += OnUnobservedTaskException;
        
        base.OnStartup(e);
        
        Log.Information("Application started successfully");
    }
    
    protected override void OnExit(ExitEventArgs e)
    {
        Log.Information("=== Mirance exiting ===");
        Log.CloseAndFlush();
        
        base.OnExit(e);
    }
    
    private void App_DispatcherUnhandledException(object sender, DispatcherUnhandledExceptionEventArgs e)
    {
        Log.Error(e.Exception, "Unhandled dispatcher exception");
        
        MessageBox.Show(
            $"An error occurred: {e.Exception.Message}\n\nThe application will continue.",
            "Mirance Error",
            MessageBoxButton.OK,
            MessageBoxImage.Warning);
        
        e.Handled = true;
    }
    
    private void OnUnhandledException(object sender, UnhandledExceptionEventArgs e)
    {
        var ex = e.ExceptionObject as Exception;
        Log.Fatal(ex, "Fatal unhandled exception");
        
        if (e.IsTerminating)
        {
            MessageBox.Show(
                $"A fatal error occurred: {ex?.Message}\n\nThe application will close.",
                "Mirance Fatal Error",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
            
            Environment.Exit(1);
        }
    }
    
    private void OnUnobservedTaskException(object? sender, UnobservedTaskExceptionEventArgs e)
    {
        Log.Error(e.Exception, "Unobserved task exception");
        e.SetObserved();
    }
}