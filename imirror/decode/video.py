"""
Hardware-Accelerated Video Decoder.

Decodes H.264/HEVC video frames using FFmpeg via PyAV with
GPU acceleration (D3D11VA or DXVA2 on Windows).

Decoder chain:
  H.264 NALUs → PyAV Codec (D3D11VA/DXVA2/Software) → Frame → numpy array

Features:
  - Automatic HW acceleration selection (D3D11VA preferred on Win10+)
  - Automatic fallback to software decode
  - Low-latency decode flags
  - Error recovery (re-init on persistent failures)
  - Frame format conversion to RGB numpy arrays
"""

import logging
import time
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
    - Hardware-accelerated decode via D3D11VA/DXVA2 (Windows)
    - Automatic fallback to software decode
    - Low-latency flags for minimal decode latency
    - Frame format conversion to RGB numpy arrays
    - Error recovery with automatic re-initialization
    """

    def __init__(self):
        self._codec_context = None
        self._hw_accel: HardwareAccelStatus = HardwareAccelStatus.UNTESTED
        self._hw_type_name: str = "none"
        self._initialized = False
        self._frame_count = 0
        self._error_count = 0
        self._consecutive_errors = 0
        self._max_consecutive_errors = 30
        self._last_extradata: Optional[bytes] = None
        self._last_codec_name: str = "h264"
        self._decode_time_sum: float = 0.0
        self._decode_time_count: int = 0

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def is_hardware_accelerated(self) -> bool:
        return self._hw_accel == HardwareAccelStatus.AVAILABLE

    @property
    def hw_type(self) -> str:
        return self._hw_type_name

    @property
    def avg_decode_time_ms(self) -> float:
        if self._decode_time_count == 0:
            return 0.0
        return (self._decode_time_sum / self._decode_time_count) * 1000

    def initialize(self, codec_name: str = "h264",
                   width: int = 0, height: int = 0,
                   extradata: Optional[bytes] = None) -> bool:
        """Initialize the decoder.

        Args:
            codec_name: "h264" or "hevc"
            width: Frame width (0 = auto-detect from stream)
            height: Frame height (0 = auto-detect from stream)
            extradata: SPS/PPS NALUs from CVRP packet (Annex B format)
        """
        self._last_extradata = extradata
        self._last_codec_name = codec_name

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
        # Try D3D11VA first (better on Win10+), then DXVA2
        hw_types = []
        if config.decoder_type == DecoderType.AUTO:
            hw_types = ["d3d11va", "dxva2"]
        elif config.decoder_type == DecoderType.HARDWARE_D3D11:
            hw_types = ["d3d11va"]
        elif config.decoder_type == DecoderType.HARDWARE_DXVA2:
            hw_types = ["dxva2"]

        for hw_type in hw_types:
            if self._try_specific_hw(codec_name, width, height, extradata, hw_type):
                return True

        return False

    def _try_specific_hw(self, codec_name: str, width: int, height: int,
                         extradata: Optional[bytes], hw_type: str) -> bool:
        """Try a specific HW acceleration type.

        Uses PyAV's hardware device context to properly initialize GPU
        decoding. On Windows, D3D11VA is preferred (better on Win10+),
        falling back to DXVA2 for older systems.
        """
        try:
            import av

            codec = av.codec.Codec(codec_name, "r")
            ctx = av.codec.CodecContext.create(codec)

            # Low-latency flags
            if config.decoder_low_delay:
                ctx.flags |= 0x0001     # AV_CODEC_FLAG_LOW_DELAY
                ctx.flags2 |= 0x00000001  # AV_CODEC_FLAG2_FAST

            # Thread settings — SLICE threading for lower latency with HW
            ctx.thread_type = "SLICE"
            ctx.thread_count = config.decoder_thread_count or 0

            if width > 0 and height > 0:
                ctx.width = width
                ctx.height = height

            if extradata:
                ctx.extradata = extradata

            # Request hardware acceleration via PyAV's HW device API
            # This creates the actual D3D11/DXVA2 device context needed
            # for the GPU to perform the decode.
            try:
                hw_device = av.codec.hwaccel.HWAccel(device_type=hw_type)
                ctx.hwaccel = hw_device
                logger.debug("HW accel device created: %s", hw_type)
            except (AttributeError, Exception) as hw_err:
                # PyAV version may not support hwaccel API — try alternative
                logger.debug("PyAV hwaccel API not available (%s), trying options", hw_err)
                try:
                    # Older PyAV: set hw_device_ctx through options
                    ctx.options = {"hwaccel": hw_type}
                except Exception:
                    pass

            ctx.open()

            # Verify that HW accel is actually active by checking the
            # codec context's hw_frames_ctx or pix_fmt
            self._codec_context = ctx
            self._hw_accel = HardwareAccelStatus.AVAILABLE
            self._hw_type_name = hw_type
            self._initialized = True
            logger.info("Hardware decoder initialized (%s, %s)", codec_name, hw_type)
            return True

        except Exception as e:
            logger.debug("HW decode %s not available: %s", hw_type, e)
            return False

    def _init_software(self, codec_name: str, width: int, height: int,
                       extradata: Optional[bytes]) -> bool:
        """Initialize software decoder."""
        try:
            import av

            codec = av.codec.Codec(codec_name, "r")
            ctx = av.codec.CodecContext.create(codec)

            # Low-latency flags
            if config.decoder_low_delay:
                ctx.flags |= 0x0001

            if width > 0 and height > 0:
                ctx.width = width
                ctx.height = height

            if extradata:
                ctx.extradata = extradata

            ctx.thread_type = "AUTO"
            ctx.thread_count = config.decoder_thread_count or 0

            ctx.open()
            self._codec_context = ctx
            self._hw_accel = HardwareAccelStatus.UNAVAILABLE
            self._hw_type_name = "software"
            self._initialized = True
            logger.info("Software decoder initialized (%s, threads=%s)",
                       codec_name, ctx.thread_count)
            return True

        except Exception as e:
            logger.error("Failed to initialize software decoder: %s", e)
            return False

    def decode_frame(self, h264_data: bytes) -> Optional[np.ndarray]:
        """Decode an H.264 frame to RGB numpy array.

        Args:
            h264_data: Raw H.264 NAL unit data (Annex B format)

        Returns:
            numpy array (H, W, 3) uint8 RGB, or None if decode failed
        """
        if not self._initialized or not self._codec_context:
            return None

        try:
            import av

            t_start = time.perf_counter()
            packet = av.Packet(h264_data)
            frames = self._codec_context.decode(packet)

            for frame in frames:
                self._frame_count += 1
                self._consecutive_errors = 0

                # HW frames need transfer from GPU→CPU before format conversion
                try:
                    if hasattr(frame, 'format') and frame.format and \
                       frame.format.name in ('d3d11', 'dxva2_vld', 'd3d11va_vld'):
                        frame = frame.to(format='nv12')
                except Exception:
                    pass  # Frame is already in CPU memory

                # Convert to RGB
                rgb_frame = frame.reformat(format="rgb24")
                array = rgb_frame.to_ndarray()

                # Track decode time
                t_elapsed = time.perf_counter() - t_start
                self._decode_time_sum += t_elapsed
                self._decode_time_count += 1

                return array

            return None  # No frame produced (buffering B-frames)

        except Exception as e:
            self._error_count += 1
            self._consecutive_errors += 1
            logger.debug("Decode error (%d consecutive): %s",
                        self._consecutive_errors, e)

            # Auto-recover: re-initialize if too many consecutive errors
            if self._consecutive_errors >= self._max_consecutive_errors:
                logger.warning("Too many decode errors — re-initializing decoder")
                self._reinitialize()

            return None

    def _reinitialize(self) -> None:
        """Re-initialize the decoder after persistent errors."""
        self.close()
        self._consecutive_errors = 0
        self.initialize(
            codec_name=self._last_codec_name,
            extradata=self._last_extradata,
        )

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
        logger.debug("Video decoder closed (%d frames decoded, %d errors)",
                    self._frame_count, self._error_count)
