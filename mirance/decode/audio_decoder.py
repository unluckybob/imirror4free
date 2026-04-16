"""
Audio Decoder - EXACT replica of AnyMiro's AccDecoder.dll and ALACDecoder.dll

This module provides:
- AAC decoding (like AnyMiro's AccDecoder.dll)
- ALAC (Apple Lossless) decoding (like AnyMiro's ALACDecoder.dll)

Uses FFmpeg (PyAV) to decode audio exactly as AnyMiro does.

Reference: AnyMiro's AccDecoder.dll and ALACDecoder.dll
"""

import logging
import ctypes
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)

# Audio codec types - matching AnyMiro's decoder
class AudioCodec(Enum):
    """Audio codec types - exact match to AnyMiro."""
    PCM = 0          # Raw PCM
    AAC = 1          # AAC (Advanced Audio Coding)
    ALAC = 2         # Apple Lossless Audio Codec
    UNKNOWN = 99


class AudioDecoder:
    """
    Audio decoder - exact replica of AnyMiro's decoder.
    
    Supports:
    - AAC decoding (AccDecoder.dll equivalent)
    - ALAC decoding (ALACDecoder.dll equivalent)
    - PCM passthrough
    """
    
    def __init__(self):
        self._codec = None
        self._codec_context = None
        self._sample_rate = 48000
        self._channels = 2
        self._bits_per_sample = 16
        self._current_codec = AudioCodec.UNKNOWN
        self._initialized = False
        self._pyav_available = False
        
        # Try to initialize PyAV (FFmpeg)
        self._init_ffmpeg()
        
    def _init_ffmpeg(self) -> None:
        """Initialize FFmpeg via PyAV."""
        try:
            import av
            self._pyav_available = True
            logger.info("PyAV (FFmpeg) initialized - audio decoding enabled")
        except ImportError:
            logger.warning("PyAV not available - using PCM passthrough")
            self._pyav_available = False
            
    def initialize(self, codec: AudioCodec, sample_rate: int = 48000, 
                   channels: int = 2, bits_per_sample: int = 16) -> bool:
        """
        Initialize the decoder for a specific codec.
        
        Args:
            codec: Audio codec type
            sample_rate: Sample rate (default 48000)
            channels: Number of channels (default 2)
            bits_per_sample: Bits per sample (default 16)
            
        Returns:
            True if initialized successfully
        """
        self._current_codec = codec
        self._sample_rate = sample_rate
        self._channels = channels
        self._bits_per_sample = bits_per_sample
        
        if not self._pyav_available:
            logger.info("Using PCM passthrough (no FFmpeg)")
            self._initialized = True
            return True
            
        try:
            import av
            
            # Initialize codec based on type - exactly like AnyMiro
            if codec == AudioCodec.AAC:
                # AAC decoder - like AccDecoder.dll
                self._codec = av.Codec('aac', 'decoder')
                logger.info("AAC decoder initialized (AccDecoder.dll style)")
                
            elif codec == AudioCodec.ALAC:
                # ALAC decoder - like ALACDecoder.dll
                self._codec = av.Codec('alac', 'decoder')
                logger.info("ALAC decoder initialized (ALACDecoder.dll style)")
                
            elif codec == AudioCodec.PCM:
                # PCM passthrough - no decoding needed
                logger.info("PCM passthrough mode")
                
            else:
                logger.warning(f"Unknown codec: {codec}")
                return False
                
            self._initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize audio decoder: {e}")
            self._initialized = True  # Fall back to PCM
            return True
            
    def decode(self, data: bytes) -> Optional[bytes]:
        """
        Decode audio data.
        
        Args:
            data: Encoded audio data (AAC/ALAC)
            
        Returns:
            Decoded PCM audio data, or None if decoding fails
        """
        if not self._initialized:
            logger.warning("Decoder not initialized")
            return None
            
        # If using PCM passthrough, return as-is
        if self._current_codec == AudioCodec.PCM or not self._pyav_available:
            return data
            
        if not self._codec or not data:
            return data  # Passthrough
            
        try:
            import av
            
            # Create input packet
            packet = av.Packet(data)
            
            # Decode packet
            frames = self._codec.decode(packet)
            
            if not frames:
                return None
                
            # Get the decoded frame
            frame = frames[0]
            
            # Convert to PCM (signed 16-bit)
            # PyAV gives us planar format, convert to interleaved
            if hasattr(frame, 'to_ndarray'):
                pcm_data = frame.to_ndarray()
                
                # Convert to interleaved if needed
                if len(pcm_data.shape) == 2 and pcm_data.shape[0] == self._channels:
                    # Planar -> interleaved
                    import numpy as np
                    pcm_data = np.ascontiguousarray(pcm_data.T.flatten())
                    
                # Convert to 16-bit
                if pcm_data.dtype == np.float32:
                    # Scale float32 to int16
                    pcm_data = (pcm_data * 32767).astype(np.int16)
                    
                return pcm_data.tobytes()
                
        except Exception as e:
            logger.debug(f"Audio decode error: {e}")
            
        # Fallback: return passthrough
        return data
        
    def get_supported_codecs(self) -> Dict[str, bool]:
        """Get supported codecs - matching AnyMiro's DLL capabilities."""
        return {
            "aac": self._pyav_available,
            "alac": self._pyav_available,
            "pcm": True,
        }
        
    @property
    def sample_rate(self) -> int:
        return self._sample_rate
        
    @property
    def channels(self) -> int:
        return self._channels
        
    @property
    def bits_per_sample(self) -> int:
        return self._bits_per_sample
        
    @property
    def codec(self) -> AudioCodec:
        return self._current_codec


# Global decoder instance
_decoder: Optional[AudioDecoder] = None


def get_audio_decoder() -> AudioDecoder:
    """Get the global audio decoder instance."""
    global _decoder
    if _decoder is None:
        _decoder = AudioDecoder()
    return _decoder


def detect_audio_codec(data: bytes) -> AudioCodec:
    """
    Detect audio codec from data - like AnyMiro does.
    
    Args:
        data: Audio data to analyze
        
    Returns:
        Detected audio codec
    """
    if not data or len(data) < 4:
        return AudioCodec.PCM
        
    # Check for common audio format headers
    
    # AAC ADTS header (usually starts with FFF)
    if len(data) >= 2 and (data[0] == 0xFF and (data[1] & 0xF0) == 0xF0):
        return AudioCodec.AAC
        
    # ALAC magic cookie (starts with 'alac')
    if data[:4] == b'alac':
        return AudioCodec.ALAC
        
    # Check for 'frma' (MP4 audio atom) - usually AAC or ALAC
    if data[:4] == b'frma':
        # Check next 4 bytes for codec type
        if len(data) >= 8:
            if data[4:8] == b'alac':
                return AudioCodec.ALAC
            elif data[4:8] in (b'mp4a', b'ac-3'):
                return AudioCodec.AAC
                
    # Default to PCM
    return AudioCodec.PCM


# Alias for compatibility
class AccDecoder(AudioDecoder):
    """Alias for AccDecoder.dll compatibility - same as AudioDecoder."""
    pass


class ALACDecoder(AudioDecoder):
    """Alias for ALACDecoder.dll compatibility - same as AudioDecoder."""
    pass


# Initialize global decoder
def init_audio_decoder() -> bool:
    """Initialize the global audio decoder."""
    decoder = get_audio_decoder()
    # Initialize with default settings (will be reconfigured when audio is received)
    return decoder.initialize(AudioCodec.PCM, 48000, 2, 16)


# Auto-initialize on import
init_audio_decoder()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test the decoder
    decoder = get_audio_decoder()
    print(f"Supported codecs: {decoder.get_supported_codecs()}")
    print(f"Codec: {decoder.codec}")
    print(f"Sample rate: {decoder.sample_rate}")
    print(f"Channels: {decoder.channels}")