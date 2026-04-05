"""
Audio Playback (Phase 2).

Plays PCM audio received from the iPhone via the Valeria protocol.
Audio comes as 48kHz stereo LPCM in EAT! packets.

Status: Phase 2 — Framework ready, playback TBD.
"""

import logging
import threading
from typing import Optional
from collections import deque

import numpy as np

from imirror.config import config

logger = logging.getLogger(__name__)


class AudioPlayer:
    """
    Plays PCM audio from the iPhone through the PC speakers.

    Uses sounddevice for low-latency audio output.
    Buffers a small amount of audio to smooth out USB jitter.
    """

    def __init__(self):
        self._stream = None
        self._buffer: deque = deque(maxlen=100)
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> bool:
        """Start the audio output stream."""
        if not config.audio_enabled:
            logger.info("Audio disabled in config")
            return False

        try:
            import sounddevice as sd

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
            logger.info("🔊 Audio output started (%dHz, %dch)",
                       config.audio_sample_rate, config.audio_channels)
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

    def feed(self, pcm_data: bytes) -> None:
        """Feed PCM audio data from EAT! packets."""
        if not self._running:
            return
        with self._lock:
            self._buffer.append(pcm_data)

    def _audio_callback(self, outdata: np.ndarray, frames: int,
                        time_info, status) -> None:
        """Sounddevice callback — fills output buffer."""
        with self._lock:
            if self._buffer:
                chunk = self._buffer.popleft()
                # Convert bytes to int16 numpy array
                audio = np.frombuffer(chunk, dtype=np.int16)
                # Reshape to (frames, channels)
                try:
                    audio = audio.reshape(-1, config.audio_channels)
                    if len(audio) >= frames:
                        outdata[:] = audio[:frames]
                    else:
                        outdata[:len(audio)] = audio
                        outdata[len(audio):] = 0
                except ValueError:
                    outdata[:] = 0
            else:
                # No data available — output silence
                outdata[:] = 0
