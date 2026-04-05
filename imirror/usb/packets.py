"""
Valeria Protocol Packet Definitions.

This module implements the packet codec for Apple's proprietary USB AV streaming
protocol (internally called "Valeria" by Apple). This protocol is what QuickTime
and tools like AnyMiro use for high-quality screen mirroring over USB.

Protocol reference: https://github.com/danielpaulus/quicktime_video_hack/blob/master/doc/technical_documentation.md

Packet types:
- PING: Connection handshake
- SYNC: Synchronous request/reply (CWPA, AFMT, CVRP, CLOK, TIME, SKEW, OG, STOP)
- ASYN: Asynchronous data (FEED=video, EAT!=audio, NEED, SPRP, SRAT, TBAS, TJMP)
- RPLY: Reply to SYNC packets
"""

import struct
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import logging

logger = logging.getLogger(__name__)


# ─── Magic constants (little-endian) ────────────────────────────────

class Magic:
    """4-byte magic identifiers used throughout the protocol."""
    PING = b"ping"      # 0x676E6970
    SYNC = b"sync"      # 0x636E7973
    ASYN = b"asyn"      # 0x6E797361
    RPLY = b"rply"      # 0x796C7072

    # SYNC subtypes
    CWPA = b"cwpa"      # Create audio clock
    AFMT = b"afmt"      # Audio format description
    CVRP = b"cvrp"      # Create video clock + format description
    CLOK = b"clok"      # Create clock
    TIME = b"time"      # Time request
    SKEW = b"skew"      # Clock skew
    OG   = b"og! "      # Unknown, reply with zeros
    STOP = b"stop"      # Stop clock

    # ASYN subtypes
    FEED = b"feed"      # H.264 video CMSampleBuffer
    EAT  = b"eat!"      # Audio CMSampleBuffer
    NEED = b"need"      # Request more video frames
    SPRP = b"sprp"      # Set property
    SRAT = b"srat"      # Set rate and anchor
    TBAS = b"tbas"      # Set timebase
    TJMP = b"tjmp"      # Time jump
    HPD1 = b"hpd1"      # Start video streaming
    HPD0 = b"hpd0"      # Stop video streaming
    HPA1 = b"hpa1"      # Start audio streaming
    HPA0 = b"hpa0"      # Stop audio streaming
    RELS = b"rels"      # Clock released

    # Dictionary/serialization
    DICT = b"dict"      # Dictionary
    KEYV = b"keyv"      # Key-value pair
    STRK = b"strk"      # String key
    STRV = b"strv"      # String value
    BULV = b"bulv"      # Boolean value
    DATV = b"datv"      # Data (byte array) value
    NMBV = b"nmbv"      # NSNumber value
    FDSC = b"fdsc"      # CMFormatDescription
    SBUF = b"sbuf"      # CMSampleBuffer
    IDXK = b"idxk"      # Index key (integer key dict)


class PacketType(Enum):
    """Top-level packet types."""
    PING = "ping"
    SYNC = "sync"
    ASYN = "asyn"
    RPLY = "rply"


@dataclass
class Packet:
    """Base packet structure."""
    length: int
    packet_type: PacketType
    clock_ref: bytes        # 8 bytes
    subtype: bytes          # 4 bytes
    payload: bytes          # remaining bytes

    @property
    def correlation_id(self) -> Optional[bytes]:
        """Extract 8-byte correlation ID from SYNC packets."""
        if self.packet_type == PacketType.SYNC and len(self.payload) >= 8:
            return self.payload[:8]
        return None


@dataclass
class VideoFrame:
    """Decoded video frame from a FEED packet."""
    data: bytes             # Raw H.264 NAL units (Annex B format)
    timestamp_ns: int       # Presentation timestamp in nanoseconds
    is_keyframe: bool       # Whether this is an IDR frame
    width: int = 0
    height: int = 0


@dataclass
class AudioSample:
    """Decoded audio from an EAT! packet."""
    data: bytes             # Raw PCM audio data (extracted from CMSampleBuffer)
    timestamp_ns: int       # Presentation timestamp
    sample_rate: int = 48000
    channels: int = 2


# ─── Packet reading ─────────────────────────────────────────────────

# Valid top-level magic → PacketType mapping
_MAGIC_TO_TYPE = {
    Magic.SYNC: PacketType.SYNC,
    Magic.ASYN: PacketType.ASYN,
    Magic.RPLY: PacketType.RPLY,
}


def read_packet(data: bytes) -> Optional[Packet]:
    """Parse a raw packet from bytes.

    Packet structure:
        [4 bytes: length][4 bytes: magic][8 bytes: clock_ref][4 bytes: subtype][payload...]

    Returns None if data is incomplete or has unrecognized magic bytes.
    """
    if len(data) < 4:
        return None

    length = struct.unpack_from("<I", data, 0)[0]
    if len(data) < length:
        return None

    magic = data[4:8]

    # PING packets are simpler
    if magic == Magic.PING:
        return Packet(
            length=length,
            packet_type=PacketType.PING,
            clock_ref=data[8:16] if len(data) >= 16 else b"\x00" * 8,
            subtype=b"ping",
            payload=data[16:length] if len(data) > 16 else b"",
        )

    # All other packets: magic + clock_ref(8) + subtype(4) + payload
    if length < 20:
        return None

    clock_ref = data[8:16]
    subtype = data[16:20]
    payload = data[20:length]

    ptype = _MAGIC_TO_TYPE.get(magic)
    if ptype is None:
        # Unrecognized magic — don't silently misroute
        return None

    return Packet(
        length=length,
        packet_type=ptype,
        clock_ref=clock_ref,
        subtype=subtype,
        payload=payload,
    )


# ─── Packet building ────────────────────────────────────────────────

def build_ping() -> bytes:
    """Build a PING response packet."""
    length = 16
    return struct.pack("<I", length) + Magic.PING + b"\x00" * 4 + struct.pack("<I", 1)


def build_rply(correlation_id: bytes, payload: bytes = b"") -> bytes:
    """Build a RPLY packet with the given correlation ID and payload."""
    # RPLY: [length][rply][correlation_id(8)][payload]
    total_length = 4 + 4 + 8 + len(payload)
    return (
        struct.pack("<I", total_length)
        + Magic.RPLY
        + correlation_id
        + payload
    )


def build_rply_with_clock(correlation_id: bytes, error: int, clock_ref: bytes) -> bytes:
    """Build a RPLY with error code and clock reference."""
    payload = struct.pack("<I", error) + clock_ref
    return build_rply(correlation_id, payload)


def build_rply_with_dict_error(correlation_id: bytes, error: int = 0) -> bytes:
    """Build a RPLY with a dictionary containing an Error key."""
    # Build dict: {"Error": NSNumber(error)}
    error_dict = build_dict_with_error(error)
    payload = struct.pack("<I", 0) + error_dict
    return build_rply(correlation_id, payload)


def build_asyn_need(device_clock_ref: bytes) -> bytes:
    """Build an ASYN NEED packet to request more video frames."""
    length = 20  # 4 + 4 + 8 + 4
    return (
        struct.pack("<I", length)
        + Magic.ASYN
        + device_clock_ref
        + Magic.NEED
    )


def build_asyn_hpd1(clock_ref: bytes = b"\x01" + b"\x00" * 7) -> bytes:
    """Build ASYN HPD1 — tell device to start video streaming."""
    length = 20
    return (
        struct.pack("<I", length)
        + Magic.ASYN
        + clock_ref
        + Magic.HPD1
    )


def build_asyn_hpa1(device_audio_clock_ref: bytes) -> bytes:
    """Build ASYN HPA1 — tell device to start audio streaming."""
    length = 20
    return (
        struct.pack("<I", length)
        + Magic.ASYN
        + device_audio_clock_ref
        + Magic.HPA1
    )


def build_asyn_hpd0() -> bytes:
    """Build ASYN HPD0 — tell device to stop video streaming."""
    length = 20
    return (
        struct.pack("<I", length)
        + Magic.ASYN
        + b"\x01" + b"\x00" * 7
        + Magic.HPD0
    )


def build_asyn_hpa0(device_audio_clock_ref: bytes) -> bytes:
    """Build ASYN HPA0 — tell device to stop audio streaming."""
    length = 20
    return (
        struct.pack("<I", length)
        + Magic.ASYN
        + device_audio_clock_ref
        + Magic.HPA0
    )


# ─── Serialization helpers ──────────────────────────────────────────

def build_dict_with_error(error: int = 0) -> bytes:
    """Build a serialized dictionary: {"Error": NSNumber(error)}."""
    # Key: "Error"
    key_str = b"Error"
    key_data = struct.pack("<I", 4 + 4 + len(key_str)) + Magic.STRK + key_str

    # Value: NSNumber uint32
    value_data = struct.pack("<I", 4 + 4 + 4) + Magic.NMBV + struct.pack("<II", 3, error)

    # KeyValue pair
    kv_data = key_data + value_data
    kv_wrapped = struct.pack("<I", 4 + 4 + len(kv_data)) + Magic.KEYV + kv_data

    # Dict wrapper
    dict_data = kv_wrapped
    return struct.pack("<I", 4 + 4 + len(dict_data)) + Magic.DICT + dict_data


def parse_cmtime(data: bytes, offset: int = 0) -> tuple[int, int]:
    """Parse a CMTime struct, returns (value_ns, timescale)."""
    if len(data) < offset + 24:
        return (0, 0)
    value = struct.unpack_from("<q", data, offset)[0]
    timescale = struct.unpack_from("<i", data, offset + 8)[0]
    if timescale > 0:
        ns = int(value * 1_000_000_000 / timescale)
    else:
        ns = 0
    return (ns, timescale)


def build_cmtime(nanoseconds: int) -> bytes:
    """Build a 24-byte CMTime struct from nanoseconds."""
    timescale = 1_000_000_000  # nanosecond precision
    flags = 1  # valid
    epoch = 0
    return struct.pack("<qiiq", nanoseconds, timescale, flags, epoch)


# ─── H.264 extraction from CMSampleBuffer ──────────────────────────

# Annex B start code used by standard H.264 decoders
_ANNEX_B_START_CODE = b"\x00\x00\x00\x01"

# Valid H.264 NAL unit types (used for heuristic detection)
_VALID_NAL_TYPES = frozenset({
    1,   # Non-IDR slice
    2,   # Slice data partition A
    3,   # Slice data partition B
    4,   # Slice data partition C
    5,   # IDR slice (keyframe)
    6,   # SEI (supplemental enhancement information)
    7,   # SPS (sequence parameter set)
    8,   # PPS (picture parameter set)
    9,   # Access unit delimiter
    10,  # End of sequence
    11,  # End of stream
    12,  # Filler data
})


def extract_h264_from_feed(payload: bytes) -> Optional[bytes]:
    """Extract H.264 NAL units from a FEED packet's CMSampleBuffer.

    The CMSampleBuffer wraps H.264 data in AVCC format (4-byte big-endian
    length prefix per NAL unit). This function finds the H.264 data and
    converts it to Annex B format (0x00000001 start codes) which is what
    standard decoders (FFmpeg/PyAV) expect.

    Strategy:
    1. Try to find AVCC-formatted NALUs by scanning for valid length+NAL patterns
    2. Fall back to returning raw data after 'sbuf' magic marker

    Args:
        payload: Raw FEED packet payload bytes.

    Returns:
        H.264 data in Annex B format, or None if extraction failed.
    """
    if len(payload) < 8:
        return None

    # Strategy 1: Find AVCC-formatted NAL units
    # Scan for a valid 4-byte-length + NAL header pattern
    annex_b = _try_avcc_to_annex_b(payload)
    if annex_b:
        return annex_b

    # Strategy 2: Look for Annex B start codes already in the data
    if _ANNEX_B_START_CODE in payload:
        # Data might already be in Annex B format — find the first start code
        idx = payload.find(_ANNEX_B_START_CODE)
        if idx >= 0:
            candidate = payload[idx:]
            if len(candidate) > 8:
                return bytes(candidate)

    # Strategy 3: Fall back to raw data after sbuf magic
    sbuf_idx = payload.find(Magic.SBUF)
    if sbuf_idx >= 0:
        # Skip the sbuf header (magic + length info)
        raw = payload[sbuf_idx + 4:]
        if raw:
            return bytes(raw)

    return None


def _try_avcc_to_annex_b(payload: bytes) -> Optional[bytes]:
    """Try to find and convert AVCC-formatted H.264 NALUs to Annex B.

    AVCC format: [4-byte big-endian length][NAL unit data][4-byte length][NAL...]
    Annex B format: [0x00000001][NAL unit data][0x00000001][NAL...]

    Scans the payload for the first valid AVCC NAL unit sequence,
    then converts all consecutive NALUs to Annex B.
    """
    # Scan for the start of AVCC data
    # We look for a 4-byte length followed by a valid NAL header
    for start_offset in range(len(payload) - 5):
        # Read potential 4-byte NALU length (big-endian)
        nalu_len = struct.unpack_from(">I", payload, start_offset)[0]

        # Length must be reasonable (1 byte to 5MB)
        if nalu_len < 1 or nalu_len > 5 * 1024 * 1024:
            continue

        # Must fit within remaining payload
        if start_offset + 4 + nalu_len > len(payload):
            continue

        # Check NAL header byte
        nal_header = payload[start_offset + 4]
        forbidden_bit = (nal_header >> 7) & 1
        nal_type = nal_header & 0x1F

        # forbidden_zero_bit must be 0, NAL type must be valid
        if forbidden_bit != 0:
            continue
        if nal_type not in _VALID_NAL_TYPES:
            continue

        # Found a valid starting point — convert all NALUs from here
        return _convert_avcc_stream(payload, start_offset)

    return None


def _convert_avcc_stream(payload: bytes, offset: int) -> Optional[bytes]:
    """Convert a sequence of AVCC NAL units starting at offset to Annex B."""
    result = bytearray()
    pos = offset

    while pos < len(payload) - 4:
        # Read 4-byte big-endian NALU length
        nalu_len = struct.unpack_from(">I", payload, pos)[0]
        pos += 4

        # Validate length
        if nalu_len < 1 or pos + nalu_len > len(payload):
            break

        # Validate NAL header
        nal_header = payload[pos]
        forbidden_bit = (nal_header >> 7) & 1
        nal_type = nal_header & 0x1F

        if forbidden_bit != 0 or nal_type not in _VALID_NAL_TYPES:
            break  # End of valid NALU sequence

        # Append Annex B start code + NALU data
        result.extend(_ANNEX_B_START_CODE)
        result.extend(payload[pos:pos + nalu_len])
        pos += nalu_len

    return bytes(result) if result else None


def extract_sps_pps_from_cvrp(payload: bytes) -> tuple[Optional[bytes], Optional[bytes]]:
    """Extract SPS and PPS NAL units from a CVRP packet's format description.

    The CVRP packet contains a CMFormatDescription which includes the
    H.264 decoder configuration record (SPS/PPS).

    Returns:
        Tuple of (sps_bytes, pps_bytes), either may be None if not found.
    """
    sps = None
    pps = None

    # Look for FDSC (format description) marker
    fdsc_idx = payload.find(Magic.FDSC)
    if fdsc_idx < 0:
        return (None, None)

    # Scan for NAL units within the format description
    search_region = payload[fdsc_idx:]

    # Look for SPS (NAL type 7) and PPS (NAL type 8) in AVCC format
    pos = 0
    while pos < len(search_region) - 5:
        # Check for AVCC length-prefixed NALUs
        try:
            nalu_len = struct.unpack_from(">I", search_region, pos)[0]
            if 2 <= nalu_len <= 256 and pos + 4 + nalu_len <= len(search_region):
                nal_header = search_region[pos + 4]
                nal_type = nal_header & 0x1F

                if nal_type == 7 and sps is None:
                    sps = bytes(search_region[pos + 4: pos + 4 + nalu_len])
                elif nal_type == 8 and pps is None:
                    pps = bytes(search_region[pos + 4: pos + 4 + nalu_len])

                if sps and pps:
                    break

                pos += 4 + nalu_len
                continue
        except struct.error:
            pass

        pos += 1

    if sps:
        logger.info("Found SPS (%d bytes)", len(sps))
    if pps:
        logger.info("Found PPS (%d bytes)", len(pps))

    return (sps, pps)


# ─── PCM audio extraction from CMSampleBuffer ──────────────────────

def extract_pcm_from_eat(payload: bytes) -> Optional[bytes]:
    """Extract raw PCM audio data from an EAT! packet's CMSampleBuffer.

    EAT! packets wrap PCM audio in a CMSampleBuffer. The PCM data is
    the raw sample bytes after the buffer metadata.

    The CMSampleBuffer structure for audio typically contains:
    - Timing info (CMTime presentation timestamp)
    - Format description reference
    - Raw PCM sample data

    Strategy:
    1. Look for 'sbuf' marker and extract data after the header
    2. Heuristic: find the largest contiguous region that looks like PCM
       (aligned to sample frame size: channels * bytes_per_sample)

    Args:
        payload: Raw EAT! packet payload bytes.

    Returns:
        Raw PCM audio bytes (int16 stereo), or None if extraction failed.
    """
    if len(payload) < 16:
        return None

    # Strategy 1: Look for sbuf marker
    sbuf_idx = payload.find(Magic.SBUF)
    if sbuf_idx >= 0 and sbuf_idx + 8 < len(payload):
        # Read the sbuf length (4 bytes before the magic, or 4 bytes after)
        # The sbuf container: [4: length][4: "sbuf"][data...]
        if sbuf_idx >= 4:
            sbuf_len = struct.unpack_from("<I", payload, sbuf_idx - 4)[0]
            data_start = sbuf_idx + 4  # After "sbuf" magic
            data_end = sbuf_idx - 4 + sbuf_len
            if data_end <= len(payload) and data_end > data_start:
                pcm = payload[data_start:data_end]
                # Ensure alignment to stereo int16 frame size (4 bytes)
                frame_size = 4  # 2 channels * 2 bytes per sample (int16)
                aligned_len = (len(pcm) // frame_size) * frame_size
                if aligned_len > 0:
                    return bytes(pcm[:aligned_len])

        # Fallback: take everything after sbuf magic
        raw = payload[sbuf_idx + 4:]
        frame_size = 4
        aligned_len = (len(raw) // frame_size) * frame_size
        if aligned_len > 0:
            return bytes(raw[:aligned_len])

    # Strategy 2: Skip known headers and extract remaining data
    # EAT! payload typically has ~64-128 bytes of metadata then PCM data
    # Look for the point where structured data ends and raw samples begin
    # Heuristic: find a block that's aligned to audio frame boundaries
    min_pcm_offset = 32  # Metadata is at least this many bytes
    frame_size = 4  # stereo int16

    if len(payload) > min_pcm_offset + frame_size:
        # Try progressively from the payload, looking for aligned data
        # The PCM data is usually the largest portion of the packet
        raw = payload[min_pcm_offset:]
        aligned_len = (len(raw) // frame_size) * frame_size
        if aligned_len >= frame_size * 64:  # At least 64 frames (~1.3ms at 48kHz)
            return bytes(raw[:aligned_len])

    return None
