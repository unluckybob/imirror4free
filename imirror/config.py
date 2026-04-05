"""
Application Configuration — All tunable settings.

Centralizes every tunable value so nothing is hardcoded in
implementation files. Settings are organized by subsystem.
"""

from enum import Enum
import os
import json
import logging

logger = logging.getLogger(__name__)

# Config file location
_CONFIG_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "IMIRROR4FREE")
_CONFIG_FILE = os.path.join(_CONFIG_DIR, "settings.json")


class CaptureBackendType(Enum):
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


class RecordingFormat(Enum):
    """Output format for screen recording."""
    MP4 = "mp4"
    MKV = "mkv"


class _Config:
    """Global configuration singleton."""

    def __init__(self):
        # ── Capture backend ─────────────────────────────────────────
        self.capture_backend = CaptureBackendType.AUTO

        # ── Screenshot backend (Phase 1) ────────────────────────────
        self.screenshot_target_fps: int = 15

        # ── Valeria stream backend ──────────────────────────────────
        # USB bulk I/O tuning
        self.usb_read_size: int = 65536          # Bytes per bulk read
        self.usb_read_timeout_ms: int = 100      # Timeout per read (ms)
        self.usb_write_timeout_ms: int = 500     # Timeout per write (ms)

        # Protocol tuning
        self.need_packet_interval: float = 0.016  # Send NEED every 16ms (~60fps)

        # Connection health monitoring
        self.usb_health_timeout_s: float = 10.0   # Seconds of silence = lost

        # ── Video decoder ───────────────────────────────────────────
        self.decoder_type = DecoderType.AUTO
        self.decoder_fallback_to_software: bool = True
        self.decoder_low_delay: bool = True       # Minimize decode latency
        self.decoder_thread_count: int = 0        # 0 = auto

        # ── Audio ───────────────────────────────────────────────────
        self.audio_enabled: bool = True
        self.audio_sample_rate: int = 48000
        self.audio_channels: int = 2
        self.audio_volume: float = 1.0            # 0.0 to 1.0
        self.audio_buffer_ms: int = 80            # Ring buffer size in ms
        self.audio_muted: bool = False

        # ── Rendering ──────────────────────────────────────────────
        self.vsync: bool = True
        self.render_interpolation: str = "linear"  # "linear" or "nearest"

        # ── Recording ──────────────────────────────────────────────
        self.recording_format: RecordingFormat = RecordingFormat.MP4
        self.recording_video_bitrate: int = 8_000_000     # 8 Mbps
        self.recording_audio_enabled: bool = True
        self.recording_output_dir: str = os.path.join(
            os.path.expanduser("~"), "Videos", "IMIRROR4FREE"
        )
        self.screenshot_output_dir: str = os.path.join(
            os.path.expanduser("~"), "Pictures", "IMIRROR4FREE"
        )
        self.screenshot_format: str = "png"       # "png" or "jpg"
        self.screenshot_quality: int = 95         # JPEG quality 1-100

        # ── GUI ─────────────────────────────────────────────────────
        self.window_title: str = "IMIRROR4FREE"
        self.default_window_width: int = 400
        self.default_window_height: int = 870
        self.always_on_top: bool = False
        self.show_fps_overlay: bool = False
        self.start_fullscreen: bool = False
        self.minimize_to_tray: bool = False
        self.remember_window_position: bool = True

    def save(self) -> None:
        """Save current settings to disk."""
        try:
            os.makedirs(_CONFIG_DIR, exist_ok=True)
            data = {}
            for key, value in self.__dict__.items():
                if isinstance(value, Enum):
                    data[key] = value.value
                else:
                    data[key] = value
            with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug("Settings saved to %s", _CONFIG_FILE)
        except Exception as e:
            logger.warning("Failed to save settings: %s", e)

    def load(self) -> None:
        """Load settings from disk."""
        if not os.path.exists(_CONFIG_FILE):
            return
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            enum_fields = {
                "capture_backend": CaptureBackendType,
                "decoder_type": DecoderType,
                "recording_format": RecordingFormat,
            }

            for key, value in data.items():
                if hasattr(self, key):
                    if key in enum_fields:
                        try:
                            setattr(self, key, enum_fields[key](value))
                        except ValueError:
                            pass
                    else:
                        setattr(self, key, value)

            logger.debug("Settings loaded from %s", _CONFIG_FILE)
        except Exception as e:
            logger.warning("Failed to load settings: %s", e)


# Global config instance
config = _Config()
