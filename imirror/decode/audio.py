"""
Audio Playback with Ring Buffer.

Plays PCM audio received from the iPhone via the Valeria protocol.
Audio comes as 48kHz stereo LPCM in EAT! packets.

Features:
  - Lock-free ring buffer for jitter smoothing
  - Volume control and mute
  - Buffer underrun/overrun handling
  - Proper chunk alignment for sounddevice callback
"""

import logging
import threading
from typing import Optional

import numpy as np

from imirror.config import config

logger = logging.getLogger(__name__)


class RingBuffer:
    """Lock-free-ish ring buffer for audio samples.

    Uses a numpy array as backing store with atomic-ish read/write
    positions. Designed for single-producer single-consumer pattern
    (audio feed thread writes, sounddevice callback reads).
    """

    def __init__(self, capacity_frames: int, channels: int = 2):
        self._capacity = capacity_frames
        self._channels = channels
        self._buffer = np.zeros((capacity_frames, channels), dtype=np.int16)
        self._write_pos = 0
        self._read_pos = 0
        self._lock = threading.Lock()

    @property
    def available(self) -> int:
        """Number of frames available to read."""
        with self._lock:
            diff = self._write_pos - self._read_pos
            if diff < 0:
                diff += self._capacity
            return diff

    @property
    def free_space(self) -> int:
        """Number of frames that can be written."""
        return self._capacity - self.available - 1

    def write(self, data: np.ndarray) -> int:
        """Write audio frames to the ring buffer.

        Args:
            data: numpy array of shape (frames, channels), dtype int16

        Returns:
            Number of frames actually written.
        """
        frames_to_write = min(len(data), self.free_space)
        if frames_to_write <= 0:
            return 0

        with self._lock:
            wp = self._write_pos
            # Check if write wraps around
            end = wp + frames_to_write
            if end <= self._capacity:
                self._buffer[wp:end] = data[:frames_to_write]
            else:
                first = self._capacity - wp
                self._buffer[wp:self._capacity] = data[:first]
                self._buffer[:frames_to_write - first] = data[first:frames_to_write]
            self._write_pos = end % self._capacity

        return frames_to_write

    def read(self, frames: int) -> np.ndarray:
        """Read audio frames from the ring buffer.

        Args:
            frames: Number of frames to read.

        Returns:
            numpy array of shape (frames, channels). Pads with zeros if
            not enough data available.
        """
        avail = self.available
        frames_to_read = min(frames, avail)

        result = np.zeros((frames, self._channels), dtype=np.int16)

        if frames_to_read <= 0:
            return result

        with self._lock:
            rp = self._read_pos
            end = rp + frames_to_read
            if end <= self._capacity:
                result[:frames_to_read] = self._buffer[rp:end]
            else:
                first = self._capacity - rp
                result[:first] = self._buffer[rp:self._capacity]
                result[first:frames_to_read] = self._buffer[:frames_to_read - first]
            self._read_pos = end % self._capacity

        return result

    def clear(self) -> None:
        """Clear the buffer."""
        with self._lock:
            self._read_pos = 0
            self._write_pos = 0


class AudioPlayer:
    """
    Plays PCM audio from the iPhone through the PC speakers.

    Uses sounddevice for low-latency audio output with a ring buffer
    to smooth out USB jitter. Supports volume control and muting.
    """

    def __init__(self):
        self._stream = None
        self._ring_buffer: Optional[RingBuffer] = None
        self._running = False
        self._underrun_count = 0
        self._overrun_count = 0
        self._frames_played = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def buffer_fill_ms(self) -> float:
        """Current buffer fill level in milliseconds."""
        if self._ring_buffer is None:
            return 0.0
        return (self._ring_buffer.available / config.audio_sample_rate) * 1000

    def start(self) -> bool:
        """Start the audio output stream."""
        if not config.audio_enabled:
            logger.info("Audio disabled in config")
            return False

        try:
            import sounddevice as sd

            # Calculate ring buffer size in frames
            buffer_frames = int(config.audio_sample_rate * config.audio_buffer_ms / 1000)
            self._ring_buffer = RingBuffer(
                capacity_frames=buffer_frames,
                channels=config.audio_channels,
            )

            self._stream = sd.OutputStream(
                samplerate=config.audio_sample_rate,
                channels=config.audio_channels,
                dtype="int16",
                callback=self._audio_callback,
                blocksize=1024,
                latency="low",
            )
            self._stream.start()
            self._running = True
            logger.info("Audio output started (%dHz, %dch, buffer=%dms)",
                       config.audio_sample_rate, config.audio_channels,
                       config.audio_buffer_ms)
            return True

        except Exception as e:
            logger.warning("Audio output not available: %s", e)
            return False

    def stop(self) -> None:
        """Stop audio output."""
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._ring_buffer:
            self._ring_buffer.clear()
        logger.info("Audio stopped (played=%d, underruns=%d, overruns=%d)",
                    self._frames_played, self._underrun_count, self._overrun_count)

    def feed(self, pcm_data: bytes) -> None:
        """Feed PCM audio data from EAT! packets."""
        if not self._running or self._ring_buffer is None:
            return

        if config.audio_muted:
            return

        try:
            # Convert bytes to int16 numpy array
            audio = np.frombuffer(pcm_data, dtype=np.int16).copy()

            # Reshape to (frames, channels)
            audio = audio.reshape(-1, config.audio_channels)

            # Apply volume
            if config.audio_volume < 1.0:
                audio = (audio * config.audio_volume).astype(np.int16)

            written = self._ring_buffer.write(audio)
            if written < len(audio):
                self._overrun_count += 1

        except ValueError:
            pass  # Reshape failed — wrong alignment

    def _audio_callback(self, outdata: np.ndarray, frames: int,
                        time_info, status) -> None:
        """Sounddevice callback — fills output buffer from ring buffer."""
        if self._ring_buffer is None or not self._running:
            outdata[:] = 0
            return

        data = self._ring_buffer.read(frames)
        outdata[:] = data
        self._frames_played += frames

        # Track underruns (buffer was empty)
        if self._ring_buffer.available == 0 and self._frames_played > 0:
            self._underrun_count += 1

    def set_volume(self, volume: float) -> None:
        """Set playback volume (0.0 to 1.0)."""
        config.audio_volume = max(0.0, min(1.0, volume))

    def set_muted(self, muted: bool) -> None:
        """Toggle mute."""
        config.audio_muted = muted
