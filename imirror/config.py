"""
Application Configuration — All tunable settings.

Centralizes every tunable value so nothing is hardcoded in
implementation files. Settings are organized by subsystem.
"""

from enum import Enum


class CaptureBackend(Enum):
    """Which capture backend to use."""
    AUTO = "auto"               # Try Valeria first, fall back to Screenshot
    VALERIA = "valeria"         # Force Valeria streaming (30-60 FPS)
    SCREENSHOT = "screenshot"   # Force screenshot capture (~10 FPS)


class DecoderType(Enum):
    """Video decoder selection."""
    AUTO = "auto"
    HARDWARE_DXVA2 = "dxva2"
    HARDWARE_D3D11 = "d3d11va"
    SOFTWARE = "software"


class _Config:
    """Global configuration singleton."""

    def __init__(self):
        # ── Capture backend ─────────────────────────────────────────
        self.capture_backend = CaptureBackend.AUTO

        # ── Screenshot backend (Phase 1) ────────────────────────────
        self.screenshot_target_fps: int = 15

        # ── Valeria stream backend (Phase 2) ────────────────────────
        # USB bulk I/O tuning
        self.usb_read_size: int = 65536         # Bytes per bulk read
        self.usb_read_timeout_ms: int = 100     # Timeout per read (ms)
        self.usb_write_timeout_ms: int = 500    # Timeout per write (ms)

        # Protocol tuning
        self.need_packet_interval: float = 0.033  # Send NEED every 33ms (~30fps)

        # Connection health monitoring
        self.usb_health_timeout_s: float = 10.0  # Seconds of silence = connection lost

        # ── Video decoder ───────────────────────────────────────────
        self.decoder_type = DecoderType.AUTO
        self.decoder_fallback_to_software: bool = True

        # ── Audio ───────────────────────────────────────────────────
        self.audio_enabled: bool = True
        self.audio_sample_rate: int = 48000
        self.audio_channels: int = 2

        # ── Rendering ──────────────────────────────────────────────
        self.vsync: bool = True
        self.render_interpolation: str = "linear"   # "linear" or "nearest"

        # ── GUI ─────────────────────────────────────────────────────
        self.window_title: str = "IMIRROR4FREE"
        self.default_window_width: int = 400
        self.default_window_height: int = 870
        self.always_on_top: bool = False
        self.show_fps_overlay: bool = False
        self.start_fullscreen: bool = False


# Global config instance
config = _Config()
