"""
Screen Recording & Screenshots.

Records the mirrored iPhone screen to MP4/MKV files and captures
individual screenshots to PNG/JPEG. Uses PyAV for muxing the
H.264 stream directly without re-encoding (zero quality loss).

Features:
  - Direct H.264 mux (no re-encode, preserves original quality)
  - Optional audio recording
  - Screenshot capture from the latest decoded frame
  - Auto-naming with timestamps
  - Recording status tracking
"""

import logging
import os
import time
import threading
from datetime import datetime
from typing import Optional
from enum import Enum

import numpy as np

from imirror.config import config

logger = logging.getLogger(__name__)


class RecordingState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    STOPPING = "stopping"
    ERROR = "error"


class ScreenRecorder:
    """
    Records the iPhone mirror stream to a video file.

    Accepts raw H.264 NAL units from the Valeria session and muxes
    them directly into an MP4/MKV container using PyAV. This means
    zero quality loss — the recording is the exact same H.264 stream
    the iPhone sends.

    Usage:
        recorder = ScreenRecorder()
        recorder.start()
        # For each video frame:
        recorder.feed_video(h264_data, is_keyframe)
        # For each audio sample:
        recorder.feed_audio(pcm_data)
        recorder.stop()
    """

    def __init__(self):
        self._state = RecordingState.IDLE
        self._container = None
        self._video_stream = None
        self._audio_stream = None
        self._output_path: Optional[str] = None
        self._start_time: float = 0.0
        self._frame_count: int = 0
        self._lock = threading.Lock()
        self._first_keyframe_received = False
        self._first_pts_ns: Optional[int] = None  # For PTS calculation

    @property
    def state(self) -> RecordingState:
        return self._state

    @property
    def is_recording(self) -> bool:
        return self._state == RecordingState.RECORDING

    @property
    def output_path(self) -> Optional[str]:
        return self._output_path

    @property
    def duration_seconds(self) -> float:
        if not self.is_recording:
            return 0.0
        return time.monotonic() - self._start_time

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def start(self, output_path: Optional[str] = None) -> bool:
        """Start recording to a file.

        Args:
            output_path: Full path for output file. If None, auto-generates
                        a timestamped filename in the configured output dir.

        Returns:
            True if recording started successfully.
        """
        if self._state == RecordingState.RECORDING:
            logger.warning("Already recording")
            return False

        try:
            import av

            # Generate output path if not provided
            if output_path is None:
                ext = config.recording_format.value
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"MIRROR4FREE_{timestamp}.{ext}"
                os.makedirs(config.recording_output_dir, exist_ok=True)
                output_path = os.path.join(config.recording_output_dir, filename)

            self._output_path = output_path

            # Open output container
            fmt = config.recording_format.value
            self._container = av.open(output_path, mode="w", format=fmt)

            # Add video stream — copy mode (no re-encoding)
            self._video_stream = self._container.add_stream("h264", rate=30)
            self._video_stream.codec_context.time_base = "1/90000"

            # Add audio stream if enabled
            if config.recording_audio_enabled:
                self._audio_stream = self._container.add_stream("pcm_s16le",
                                                                 rate=config.audio_sample_rate)
                self._audio_stream.codec_context.channels = config.audio_channels

            self._start_time = time.monotonic()
            self._frame_count = 0
            self._first_keyframe_received = False
            self._first_pts_ns = None
            self._state = RecordingState.RECORDING

            logger.info("Recording started: %s", output_path)
            return True

        except Exception as e:
            logger.error("Failed to start recording: %s", e)
            self._state = RecordingState.ERROR
            return False

    def set_video_format(self, width: int, height: int,
                         extradata: Optional[bytes] = None) -> None:
        """Set video codec parameters on the stream.

        Must be called before the first keyframe arrives so the MP4
        container header has correct width/height and SPS/PPS extradata.
        Safe to call multiple times — only the first call has effect.
        """
        if self._video_stream is None:
            return
        try:
            ctx = self._video_stream.codec_context
            if width > 0:
                ctx.width = width
            if height > 0:
                ctx.height = height
            if extradata:
                ctx.extradata = extradata
            logger.debug("Video format set: %dx%d, extradata=%s",
                        width, height, f"{len(extradata)}B" if extradata else "none")
        except Exception as e:
            logger.debug("Could not set video format params: %s", e)

    def stop(self) -> Optional[str]:
        """Stop recording and close the file.

        Returns:
            Path to the saved recording, or None if not recording.
        """
        if self._state != RecordingState.RECORDING:
            return None

        self._state = RecordingState.STOPPING

        with self._lock:
            try:
                if self._container:
                    self._container.close()
                    self._container = None
            except Exception as e:
                logger.error("Error closing recording: %s", e)

        path = self._output_path
        duration = time.monotonic() - self._start_time

        self._state = RecordingState.IDLE
        self._video_stream = None
        self._audio_stream = None

        logger.info("Recording saved: %s (%.1fs, %d frames)",
                    path, duration, self._frame_count)
        return path

    def feed_video(self, h264_data: bytes, is_keyframe: bool,
                   timestamp_ns: int = 0) -> None:
        """Feed an H.264 frame to the recorder.

        The recording must start on a keyframe — non-keyframes before
        the first keyframe are silently dropped.

        Args:
            h264_data: Annex B H.264 NAL unit data.
            is_keyframe: Whether this is an IDR keyframe.
            timestamp_ns: Device presentation timestamp in nanoseconds
                          (from CMSampleBuffer). Used for accurate PTS.
                          Falls back to frame-count PTS if 0.
        """
        if self._state != RecordingState.RECORDING:
            return

        # Wait for first keyframe to start actual muxing
        if not self._first_keyframe_received:
            if not is_keyframe:
                return
            self._first_keyframe_received = True

        with self._lock:
            try:
                import av

                if self._video_stream is None or self._container is None:
                    return

                packet = av.Packet(h264_data)
                packet.stream = self._video_stream

                # Calculate PTS: prefer actual device timestamps for correct timing.
                # Using the CMSampleBuffer PTS eliminates encoder jitter and handles
                # variable-rate streams (e.g. 60→30 FPS on orientation change).
                if timestamp_ns > 0:
                    if self._first_pts_ns is None:
                        self._first_pts_ns = timestamp_ns
                    relative_ns = timestamp_ns - self._first_pts_ns
                    pts = int(relative_ns * 90000 / 1_000_000_000)  # ns → 90kHz
                else:
                    # Fallback: assume constant 30 FPS (timebase = 90kHz)
                    pts = int(self._frame_count * 90000 / 30)

                packet.pts = pts
                packet.dts = pts
                packet.is_keyframe = is_keyframe

                self._container.mux(packet)
                self._frame_count += 1

            except Exception as e:
                logger.debug("Recording mux error: %s", e)

    def feed_audio(self, pcm_data: bytes) -> None:
        """Feed PCM audio data to the recorder."""
        if self._state != RecordingState.RECORDING:
            return
        if not self._first_keyframe_received:
            return
        if self._audio_stream is None:
            return

        with self._lock:
            try:
                import av

                if self._container is None:
                    return

                # Create audio frame from PCM data
                audio_array = np.frombuffer(pcm_data, dtype=np.int16)
                audio_array = audio_array.reshape(-1, config.audio_channels)

                frame = av.AudioFrame.from_ndarray(
                    audio_array.T,  # PyAV expects (channels, samples)
                    format="s16",
                    layout="stereo" if config.audio_channels == 2 else "mono",
                )
                frame.sample_rate = config.audio_sample_rate

                for pkt in self._audio_stream.encode(frame):
                    self._container.mux(pkt)

            except Exception as e:
                logger.debug("Audio recording error: %s", e)


class ScreenshotSaver:
    """Saves individual screenshots from the mirror stream."""

    @staticmethod
    def save_screenshot(frame: np.ndarray,
                        output_path: Optional[str] = None) -> Optional[str]:
        """Save the current frame as an image file.

        Args:
            frame: RGB numpy array (H, W, 3)
            output_path: Full path for output file. If None, auto-generates.

        Returns:
            Path to saved screenshot, or None on failure.
        """
        try:
            from PIL import Image

            if frame is None or frame.size == 0:
                logger.warning("No frame available for screenshot")
                return None

            if output_path is None:
                ext = config.screenshot_format
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                filename = f"MIRROR4FREE_{timestamp}.{ext}"
                os.makedirs(config.screenshot_output_dir, exist_ok=True)
                output_path = os.path.join(config.screenshot_output_dir, filename)

            img = Image.fromarray(frame, "RGB")

            if config.screenshot_format == "jpg":
                img.save(output_path, "JPEG", quality=config.screenshot_quality)
            else:
                img.save(output_path, "PNG")

            logger.info("Screenshot saved: %s (%dx%d)",
                       output_path, frame.shape[1], frame.shape[0])
            return output_path

        except Exception as e:
            logger.error("Failed to save screenshot: %s", e)
            return None
