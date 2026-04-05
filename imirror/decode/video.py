"""
Hardware-Accelerated Video Decoder.

Decodes H.264/HEVC video frames using FFmpeg via PyAV with
GPU acceleration (DXVA2 or D3D11VA on Windows).

Used by the Valeria Stream backend (Phase 2) to decode the
H.264 video stream from the iPhone at minimal latency.

The decoder chain:
  H.264 NALUs → PyAV Codec (DXVA2) → GPU Texture → numpy array

For Phase 1 (screenshot backend), this module is not used since
screenshots arrive as pre-decoded PNG images.
"""

import logging
from typing import Optional
from enum import Enum

import numpy as np

from imirror.config import config, DecoderType

logger = logging.getLogger(__name__)


class HardwareAccelStatus(Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNTESTED = "untested"


class VideoDecoder:
    """
    H.264/HEVC video decoder with hardware acceleration.

    Wraps PyAV (FFmpeg) to provide:
    - Hardware-accelerated decode via DXVA2 (Windows)
    - Automatic fallback to software decode
    - Frame format conversion to RGB numpy arrays
    """

    def __init__(self):
        self._codec_context = None
        self._hw_accel: HardwareAccelStatus = HardwareAccelStatus.UNTESTED
        self._initialized = False
        self._frame_count = 0

    @property
    def is_initialized(self) -> bool:
        """Whether the decoder has been successfully initialized."""
        return self._initialized

    def initialize(self, codec_name: str = "h264",
                   width: int = 0, height: int = 0,
                   extradata: Optional[bytes] = None) -> bool:
        """Initialize the decoder.

        Args:
            codec_name: "h264" or "hevc"
            width: Frame width (0 = auto-detect from stream)
            height: Frame height (0 = auto-detect from stream)
            extradata: SPS/PPS NALUs from CVRP packet
        """
        try:
            import av

            # Try hardware-accelerated decoder first
            if config.decoder_type != DecoderType.SOFTWARE:
                if self._try_hw_init(codec_name, width, height, extradata):
                    return True

            # Fallback to software
            if config.decoder_fallback_to_software or config.decoder_type == DecoderType.SOFTWARE:
                return self._init_software(codec_name, width, height, extradata)

            return False

        except ImportError:
            logger.error("PyAV not installed — cannot decode video")
            return False

    def _try_hw_init(self, codec_name: str, width: int, height: int,
                     extradata: Optional[bytes]) -> bool:
        """Try to initialize hardware-accelerated decoder."""
        try:
            import av

            hw_type = {
                DecoderType.HARDWARE_DXVA2: "dxva2",
                DecoderType.HARDWARE_D3D11: "d3d11va",
            }.get(config.decoder_type, "dxva2")

            codec = av.codec.Codec(codec_name, "r")
            ctx = av.codec.CodecContext.create(codec)

            # Try to enable hardware acceleration
            if hasattr(ctx, 'hwaccel'):
                ctx.hwaccel = hw_type

            if width > 0 and height > 0:
                ctx.width = width
                ctx.height = height

            if extradata:
                ctx.extradata = extradata

            ctx.open()
            self._codec_context = ctx
            self._hw_accel = HardwareAccelStatus.AVAILABLE
            self._initialized = True
            logger.info("Hardware decoder initialized (%s, %s)", codec_name, hw_type)
            return True

        except Exception as e:
            logger.info("Hardware decode not available (%s), will use software", e)
            self._hw_accel = HardwareAccelStatus.UNAVAILABLE
            return False

    def _init_software(self, codec_name: str, width: int, height: int,
                       extradata: Optional[bytes]) -> bool:
        """Initialize software decoder."""
        try:
            import av

            codec = av.codec.Codec(codec_name, "r")
            ctx = av.codec.CodecContext.create(codec)

            if width > 0 and height > 0:
                ctx.width = width
                ctx.height = height

            if extradata:
                ctx.extradata = extradata

            ctx.thread_type = "AUTO"
            ctx.thread_count = 0  # Auto

            ctx.open()
            self._codec_context = ctx
            self._initialized = True
            logger.info("Software decoder initialized (%s)", codec_name)
            return True

        except Exception as e:
            logger.error("Failed to initialize software decoder: %s", e)
            return False

    def decode_frame(self, h264_data: bytes) -> Optional[np.ndarray]:
        """Decode an H.264 frame to RGB numpy array.

        Args:
            h264_data: Raw H.264 NAL unit data

        Returns:
            numpy array (H, W, 3) uint8 RGB, or None if decode failed
        """
        if not self._initialized or not self._codec_context:
            return None

        try:
            import av

            packet = av.Packet(h264_data)
            frames = self._codec_context.decode(packet)

            for frame in frames:
                self._frame_count += 1

                # Convert to RGB
                rgb_frame = frame.reformat(format="rgb24")
                array = rgb_frame.to_ndarray()

                return array

            return None  # No frame produced (e.g., buffering B-frames)

        except Exception as e:
            logger.debug("Decode error: %s", e)
            return None

    def flush(self) -> list[np.ndarray]:
        """Flush any buffered frames from the decoder."""
        if not self._initialized or not self._codec_context:
            return []

        try:
            frames = []
            for frame in self._codec_context.decode(None):
                rgb_frame = frame.reformat(format="rgb24")
                frames.append(rgb_frame.to_ndarray())
            return frames
        except Exception:
            return []

    def close(self) -> None:
        """Close the decoder and release resources."""
        if self._codec_context:
            try:
                self._codec_context.close()
            except Exception:
                pass
            self._codec_context = None
        self._initialized = False
        logger.debug("Video decoder closed (%d frames decoded)", self._frame_count)

    @property
    def is_hardware_accelerated(self) -> bool:
        return self._hw_accel == HardwareAccelStatus.AVAILABLE
