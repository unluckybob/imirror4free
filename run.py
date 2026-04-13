"""
MIRANCE — Startup wrapper for the built EXE.

This is the PyInstaller entry point. It catches any startup/import errors
and shows a user-friendly Windows error dialog instead of silently crashing
(which is what happens with --windowed PyInstaller builds).

Without this wrapper, if a DLL is missing or an import fails, the user
sees absolutely nothing — the EXE just doesn't start. With this wrapper,
they get a clear error message and a crash log file.
"""

import sys
import os
import traceback
from datetime import datetime
from multiprocessing import freeze_support

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


def show_error_dialog(title: str, message: str) -> None:
    """Show a native Windows error dialog (no dependencies required)."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)  # MB_ICONERROR
    except Exception:
        # Fallback: print to stderr (visible if launched from console)
        print(f"ERROR: {title}\n{message}", file=sys.stderr)


def write_crash_log(error_text: str) -> str | None:
    """Write crash info to a log file next to the executable."""
    try:
        if getattr(sys, "frozen", False):
            log_dir = os.path.dirname(sys.executable)
        else:
            log_dir = os.path.dirname(os.path.abspath(__file__))

        log_path = os.path.join(log_dir, "mirance_crash.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"MIRANCE Crash Log — {datetime.now()}\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"Executable: {sys.executable}\n")
            f.write(f"Frozen: {getattr(sys, 'frozen', False)}\n\n")
            f.write(error_text)
        return log_path
    except Exception:
        return None


if __name__ == "__main__":
    freeze_support()
    try:
        from mirance.main import main

        sys.exit(main())
    except Exception as e:
        error_text = traceback.format_exc()
        log_path = write_crash_log(error_text)

        msg = f"MIRANCE failed to start:\n\n{type(e).__name__}: {e}\n\n"
        if log_path:
            msg += f"Full error log saved to:\n{log_path}\n\n"
        msg += (
            "Common fixes:\n"
            "• Install Microsoft Visual C++ Redistributable 2015-2022\n"
            "• Install iTunes (for Apple Mobile Device Support)\n"
            "• Try running as Administrator\n\n"
            "Report issues at:\nhttps://github.com/unluckybob/mirance/issues"
        )

        show_error_dialog("MIRANCE — Startup Error", msg)
        sys.exit(1)
