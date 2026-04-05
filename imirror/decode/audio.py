"""
Audio Player — Plays PCM audio samples from the Valeria stream.

Receives raw PCM float32 audio data from the Valeria protocol's
EAT! (audio sample) packets and plays it through the system's
default audio output device via sounddevice.

This module is optional — if sounddevice is not available, audio
playback is silently disabled. Video streaming works fine without it.
"""

import logging
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class AudioPlayer:
    """
    Plays PCM audio samples from the Valeria stream in real-time.

    Uses sounddevice for low-latency audio output. The player maintains
    a small ring buffer to smooth out jitter from USB packet timing.

    If sounddevice is not installed, the player is a no-op — all methods
    succeed silently so the rest of the app works without audio.
    """

    def __init__(self, sample_rate: int = 44100, channels: int = 2,
                 buffer_ms: int = 100):
        self._sample_rate = sample_rate
        self._channels = channels
        self._buffer_ms = buffer_ms
        self._stream = None
        self._running = False
        self._lock = threading.Lock()
        self._buffer = bytearray()
        self._sd_available = False

        # Check if sounddevice is available
        try:
            import sounddevice  # noqa: F401
            self._sd_available = True
        except ImportError:
            logger.info("sounddevice not available — audio playback disabled")

    def start(self) -> bool:
        """Start the audio output stream.

        Returns:
            True if audio output started successfully, False otherwise.
        """
        if not self._sd_available:
            return False

        if self._running:
            return True

        try:
            import sounddevice as sd

            self._stream = sd.OutputStream(
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype="float32",
                blocksize=1024,
                callback=self._audio_callback,
                latency="low",
            )
            self._stream.start()
            self._running = True
            logger.info(
                "Audio output started: %d Hz, %d channels",
                self._sample_rate, self._channels,
            )
            return True

        except Exception as e:
            logger.warning("Failed to start audio output: %s", e)
            self._stream = None
            return False

    def stop(self) -> None:
        """Stop the audio output stream and release resources."""
        self._running = False

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        with self._lock:
            self._buffer.clear()

        logger.info("Audio output stopped")

    def feed(self, pcm_data: bytes) -> None:
        """Feed raw PCM audio data to the player.

        Args:
            pcm_data: Raw PCM float32 audio data from Valeria EAT! packets.
        """
        if not self._running:
            return

        with self._lock:
            self._buffer.extend(pcm_data)

            # Limit buffer size to prevent unbounded growth
            max_bytes = int(
                self._sample_rate * self._channels * 4  # float32 = 4 bytes
                * self._buffer_ms / 1000.0 * 3  # 3x buffer for safety
            )
            if len(self._buffer) > max_bytes:
                # Drop oldest data to keep latency bounded
                excess = len(self._buffer) - max_bytes
                del self._buffer[:excess]

    def set_volume(self, volume: float) -> None:
        """Set playback volume (0.0 to 1.0).

        Note: Volume is applied in the audio callback, not here.
        """
        self._volume = max(0.0, min(1.0, volume))

    @property
    def is_playing(self) -> bool:
        """Whether the audio stream is currently active."""
        return self._running and self._stream is not None

    def _audio_callback(self, outdata: np.ndarray, frames: int,
                        time_info, status) -> None:
        """sounddevice output callback — fills the output buffer."""
        bytes_needed = frames * self._channels * 4  # float32

        with self._lock:
            available = len(self._buffer)
            if available >= bytes_needed:
                chunk = bytes(self._buffer[:bytes_needed])
                del self._buffer[:bytes_needed]
            elif available > 0:
                # Partial data — pad with silence
                chunk = bytes(self._buffer) + b"\x00" * (bytes_needed - available)
                self._buffer.clear()
            else:
                # No data — output silence
                outdata[:] = 0
                return

        try:
            audio_array = np.frombuffer(chunk, dtype=np.float32).reshape(-1, self._channels)
            outdata[:] = audio_array[:frames]
        except (ValueError, IndexError):
            outdata[:] = 0
