"""
Application configuration and constants.
"""

from dataclasses import dataclass, field
from enum import Enum


class CaptureBackend(Enum):
    """Available capture backends, ordered by quality."""
    SCREENSHOT = "screenshot"       # Phase 1: DVT screenshot loop (~10-15 fps)
    VALERIA_STREAM = "valeria"      # Phase 2: Valeria H.264 stream (30-60 fps)


class DecoderType(Enum):
    """Video decoder selection."""
    SOFTWARE = "software"           # libavcodec software decode
    HARDWARE_DXVA2 = "dxva2"        # Windows DXVA2 GPU decode
    HARDWARE_D3D11 = "d3d11va"      # Windows D3D11 GPU decode


@dataclass
class AppConfig:
    """Runtime configuration for IMIRROR4FREE."""

    # -- Window --
    window_title: str = "IMIRROR4FREE"
    default_width: int = 1280
    default_height: int = 720
    start_fullscreen: bool = False

    # -- Capture --
    capture_backend: CaptureBackend = CaptureBackend.SCREENSHOT
    auto_select_backend: bool = True    # Auto-pick best available backend

    # -- Screenshot backend --
    screenshot_target_fps: int = 15     # Target FPS for screenshot loop
    screenshot_jpeg_quality: int = 95   # JPEG quality if transcoding

    # -- Valeria backend (Phase 2) --
    valeria_prefer_hevc: bool = True    # Prefer HEVC over H.264 if available
    valeria_max_fps: int = 60           # Max FPS to request

    # -- Decoder --
    decoder_type: DecoderType = DecoderType.HARDWARE_DXVA2
    decoder_fallback_to_software: bool = True

    # -- Renderer --
    vsync: bool = True
    show_fps_overlay: bool = False
    render_interpolation: str = "linear"   # "nearest" or "linear"

    # -- Audio (Phase 2) --
    audio_enabled: bool = True
    audio_sample_rate: int = 48000
    audio_channels: int = 2

    # -- Performance --
    frame_queue_size: int = 3           # Max frames in decode→render queue
    drop_late_frames: bool = True       # Drop frames that arrive too late


# Global config instance
config = AppConfig()
