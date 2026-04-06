"""
Valeria Protocol Packet Definitions.

This module implements the packet codec for Apple's proprietary USB AV streaming
protocol (internally called "Valeria" by Apple). This protocol is what QuickTime
uses for high-quality screen mirroring over USB.

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


@dataclass
class ParsedCMSampleBuffer:
    """Parsed CMSampleBuffer from a FEED or EAT! packet.

    Represents the structured contents of Apple's CMSampleBuffer binary format,
    extracted by iterating the TLV sections (sbuf → opts/sdat/fdsc/nsmp/etc.).

    Attributes:
        sample_data: Raw media bytes from the ``sdat`` section (H.264 AVCC or PCM).
        pts_value: Presentation timestamp value from the ``opts`` CMTime.
        pts_timescale: Presentation timestamp timescale from the ``opts`` CMTime.
        has_format_description: Whether an ``fdsc`` section was found (keyframes).
        format_description_bytes: Raw ``fdsc`` bytes including the section header.
        num_samples: Number of samples from the ``nsmp`` section.
    """
    sample_data: Optional[bytes] = None
    pts_value: int = 0
    pts_timescale: int = 0
    has_format_description: bool = False
    format_description_bytes: Optional[bytes] = None
    num_samples: int = 0
    sample_rate: int = 0
    channels: int = 0
    bits_per_channel: int = 0


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


def read_packets_from_buffer(data: bytes) -> tuple[list[Packet], bytes]:
    """Parse as many complete packets as possible from a byte buffer.

    Returns:
        Tuple of (list of parsed packets, remaining unparsed bytes).
    """
    packets = []
    offset = 0

    while offset < len(data) - 3:
        remaining = data[offset:]
        if len(remaining) < 4:
            break

        length = struct.unpack_from("<I", remaining, 0)[0]
        if length < 4 or length > 10 * 1024 * 1024:  # sanity: max 10MB
            # Corrupted length — skip 1 byte and try to re-sync
            offset += 1
            continue

        if len(remaining) < length:
            break  # Incomplete packet — wait for more data

        pkt = read_packet(remaining[:length])
        if pkt:
            packets.append(pkt)
        offset += length

    return packets, data[offset:]


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


def build_asyn_hpd1(
    clock_ref: bytes = b"\x01" + b"\x00" * 7,
    width: int = 1920,
    height: int = 1080,
) -> bytes:
    """Build ASYN HPD1 — tell device to start video streaming with display capabilities.

    Sends a capabilities dictionary that tells the iPhone the receiver's display
    resolution and codec support. Without this dict, the iPhone may default to
    the lowest resolution or refuse to start streaming.

    The protocol expects a capabilities dictionary::

        {
            "Valeria": True,
            "HEVCDecoderSupports444": True,
            "DisplaySize": {"Width": <float>, "Height": <float>},
        }

    Args:
        clock_ref: 8-byte clock reference (default: ``0x01`` padded).
        width: Advertised display width in pixels.
        height: Advertised display height in pixels.

    Returns:
        Complete ASYN HPD1 packet bytes.
    """
    # Build DisplaySize sub-dict
    display_size = _serialize_dict({
        "Width": ("nsnumber_f64", float(width)),
        "Height": ("nsnumber_f64", float(height)),
    })

    # Build main capabilities dict
    cap_dict = _serialize_dict({
        "Valeria": ("bool", True),
        "HEVCDecoderSupports444": ("bool", True),
        "DisplaySize": ("dict", display_size),
    })

    length = 20 + len(cap_dict)
    return (
        struct.pack("<I", length)
        + Magic.ASYN
        + clock_ref
        + Magic.HPD1
        + cap_dict
    )


def build_asyn_hpa1(device_audio_clock_ref: bytes) -> bytes:
    """Build ASYN HPA1 — tell device to start audio streaming with configuration.

    Sends an audio configuration dictionary containing the AudioStreamBasicDescription
    and playback parameters. Without this dict, the iPhone may not send audio or
    may use an unexpected format.

    The protocol expects an audio configuration dictionary::

        {
            "BufferAheadInterval": 0.073,
            "deviceUID": "Valeria",
            "ScreenLatency": 0.04,
            "formats": <ASBD bytes>,
            "EDIDAC3Support": 0,
            "deviceName": "Valeria",
        }

    Args:
        device_audio_clock_ref: 8-byte device audio clock reference from CWPA.

    Returns:
        Complete ASYN HPA1 packet bytes.
    """
    # AudioStreamBasicDescription (40 bytes base + 16 bytes extra = 56 bytes)
    # The extended ASBD is 56 bytes: the standard 40-byte ASBD struct followed
    # by SampleRate repeated twice as float64. The iPhone expects this
    # extended format.
    asbd = struct.pack("<dIIIIIIII",
        48000.0,      # SampleRate (float64)
        0x6C70636D,   # FormatID = "lpcm"
        12,           # FormatFlags (kLinearPCMFormatFlagIsSignedInteger | kLinearPCMFormatFlagIsPacked)
        4,            # BytesPerPacket
        1,            # FramesPerPacket
        4,            # BytesPerFrame
        2,            # ChannelsPerFrame
        16,           # BitsPerChannel
        0,            # Reserved
    )
    # Append SampleRate twice as float64 (extended ASBD format)
    asbd += struct.pack("<dd", 48000.0, 48000.0)

    # Audio configuration dict
    audio_config = _serialize_dict({
        "BufferAheadInterval": ("nsnumber_f64", 0.073),
        "deviceUID": ("string", "Valeria"),
        "ScreenLatency": ("nsnumber_f64", 0.04),
        "formats": ("data", asbd),
        "EDIDAC3Support": ("nsnumber_u32", 0),
        "deviceName": ("string", "Valeria"),
    })

    length = 20 + len(audio_config)
    return (
        struct.pack("<I", length)
        + Magic.ASYN
        + device_audio_clock_ref
        + Magic.HPA1
        + audio_config
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

def _serialize_dict(entries: dict) -> bytes:
    """Serialize a dictionary in Valeria's binary DICT format.

    Produces the wire format::

        DICT: [4: totalLength LE32][4: "dict" magic]
          KEYV*: [4: kvLength LE32][4: "keyv" magic]
            STRK: [4: keyLength LE32][4: "strk" magic][N: UTF-8 key]
            VALUE: one of BULV, NMBV, STRV, DATV, or nested DICT

    Args:
        entries: Ordered mapping of ``{key_name: (type_tag, value)}``.
            Supported type tags:

            - ``"bool"``  → BULV (1 byte: 0x00 or 0x01)
            - ``"string"`` → STRV (UTF-8 encoded)
            - ``"data"``   → DATV (raw bytes)
            - ``"dict"``   → nested DICT (already-serialized bytes)
            - ``"nsnumber_u32"`` → NMBV type 0x03, uint32
            - ``"nsnumber_u64"`` → NMBV type 0x04, uint64
            - ``"nsnumber_f64"`` → NMBV type 0x06, float64

    Returns:
        Serialized DICT bytes including the outer DICT header.
    """
    kv_bytes = bytearray()

    for key_name, (value_type, value) in entries.items():
        # Serialize key: STRK = [length LE32]["strk" magic][UTF-8 key string]
        key_encoded = key_name.encode("utf-8")
        key_data = struct.pack("<I", 8 + len(key_encoded)) + Magic.STRK + key_encoded

        # Serialize value based on type
        if value_type == "bool":
            # BULV: [4: 9 LE32][4: "bulv"][1: bool byte]
            val_data = struct.pack("<I", 9) + Magic.BULV + (b"\x01" if value else b"\x00")
        elif value_type == "string":
            # STRV: [4: length LE32][4: "strv"][N: UTF-8 string]
            s = value.encode("utf-8")
            val_data = struct.pack("<I", 8 + len(s)) + Magic.STRV + s
        elif value_type == "data":
            # DATV: [4: length LE32][4: "datv"][N: raw bytes]
            val_data = struct.pack("<I", 8 + len(value)) + Magic.DATV + value
        elif value_type == "nsnumber_u32":
            # NMBV: [4: 13 LE32][4: "nmbv"][1: 0x03][4: uint32 LE]
            nmbv_payload = b"\x03" + struct.pack("<I", value)
            val_data = struct.pack("<I", 8 + len(nmbv_payload)) + Magic.NMBV + nmbv_payload
        elif value_type == "nsnumber_u64":
            # NMBV: [4: 17 LE32][4: "nmbv"][1: 0x04][8: uint64 LE]
            nmbv_payload = b"\x04" + struct.pack("<Q", value)
            val_data = struct.pack("<I", 8 + len(nmbv_payload)) + Magic.NMBV + nmbv_payload
        elif value_type == "nsnumber_f64":
            # NMBV: [4: 17 LE32][4: "nmbv"][1: 0x06][8: float64 LE]
            nmbv_payload = b"\x06" + struct.pack("<d", value)
            val_data = struct.pack("<I", 8 + len(nmbv_payload)) + Magic.NMBV + nmbv_payload
        elif value_type == "dict":
            # Nested DICT — value is already-serialized bytes
            val_data = value
        else:
            raise ValueError(f"Unknown value type: {value_type}")

        # Wrap in KEYV: [length LE32]["keyv" magic][key_data][val_data]
        kv_content = key_data + val_data
        kv_wrapped = struct.pack("<I", 8 + len(kv_content)) + Magic.KEYV + kv_content
        kv_bytes.extend(kv_wrapped)

    # Wrap everything in DICT: [length LE32]["dict" magic][keyv pairs...]
    return struct.pack("<I", 8 + len(kv_bytes)) + Magic.DICT + bytes(kv_bytes)


def build_dict_with_error(error: int = 0) -> bytes:
    """Build a serialized dictionary: ``{"Error": NSNumber(error)}``.

    Fixed implementation: NSNumber uses a 1-byte type specifier (0x03 for uint32),
    not a 4-byte integer as was previously emitted.
    """
    # Key: "Error"
    key_str = b"Error"
    key_data = struct.pack("<I", 8 + len(key_str)) + Magic.STRK + key_str

    # Value: NSNumber uint32
    # [8-byte header (length + "nmbv")][1-byte type specifier][4-byte value]
    # Total = 13 bytes, so length field = 13
    nsnumber_payload = b"\x03" + struct.pack("<I", error)  # 5 bytes
    value_data = struct.pack("<I", 8 + len(nsnumber_payload)) + Magic.NMBV + nsnumber_payload

    # KeyValue pair
    kv_data = key_data + value_data
    kv_wrapped = struct.pack("<I", 8 + len(kv_data)) + Magic.KEYV + kv_data

    # Dict wrapper
    dict_data = kv_wrapped
    return struct.pack("<I", 8 + len(dict_data)) + Magic.DICT + dict_data


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


# ─── CMSampleBuffer parsing ────────────────────────────────────────

def parse_cmsamplebuffer(payload: bytes) -> Optional[ParsedCMSampleBuffer]:
    """Parse a CMSampleBuffer from a FEED or EAT! packet payload.

    Apple's CMSampleBuffer binary format wraps media data in a TLV structure::

        [4: totalLength LE32][4: "sbuf" magic]
        Section*:
          [4: sectionLength LE32][4: sectionMagic (4 bytes)][data...]

    Known sections:
      - ``sdat`` — SampleData (the actual H.264 AVCC or raw PCM bytes)
      - ``opts`` — OutputPresentationTimestamp (24-byte CMTime)
      - ``fdsc`` — FormatDescription (SPS/PPS on keyframes)
      - ``nsmp`` — NumSamples (uint32 count)
      - ``stia`` — SampleTimingInfoArray
      - ``ssiz`` — SampleSizes
      - ``satt`` — SampleAttachments
      - ``sary`` — CreateIfNecessary

    Args:
        payload: Raw FEED or EAT! packet payload bytes.

    Returns:
        A :class:`ParsedCMSampleBuffer` with the extracted fields, or ``None``
        if the payload does not start with a valid ``sbuf`` header.
    """
    if len(payload) < 8:
        return None

    # Parse outer sbuf container: [4: length LE32][4: "sbuf" bytes]
    total_len = struct.unpack_from("<I", payload, 0)[0]
    magic = payload[4:8]
    if magic != Magic.SBUF:
        return None

    result = ParsedCMSampleBuffer()
    pos = 8  # After sbuf header

    while pos + 8 <= len(payload):
        section_len = struct.unpack_from("<I", payload, pos)[0]
        section_magic = payload[pos + 4:pos + 8]

        if section_len < 8 or pos + section_len > len(payload):
            break

        data_start = pos + 8
        data_len = section_len - 8

        if section_magic == b"opts":
            # OutputPresentationTimestamp: 24-byte CMTime at offset 0 within section data
            if data_len >= 24:
                result.pts_value = struct.unpack_from("<q", payload, data_start)[0]
                result.pts_timescale = struct.unpack_from("<i", payload, data_start + 8)[0]

        elif section_magic == b"sdat":
            # SampleData — the actual H.264 AVCC or raw PCM bytes
            result.sample_data = payload[data_start:data_start + data_len]

        elif section_magic == Magic.FDSC:
            # FormatDescription — present on keyframes, contains SPS/PPS
            result.has_format_description = True
            result.format_description_bytes = payload[pos:pos + section_len]

        elif section_magic == b"nsmp":
            # NumSamples
            if data_len >= 4:
                result.num_samples = struct.unpack_from("<I", payload, data_start)[0]

        # Log unknown sections for protocol debugging
        else:
            section_name = section_magic.decode('ascii', errors='replace')
            logger.debug("CMSampleBuffer: skipping section '%s' (%d bytes)", section_name, data_len)

        pos += section_len

    return result


def avcc_to_annex_b(avcc_data: bytes) -> Optional[bytes]:
    """Convert AVCC-formatted H.264 data to Annex B format.

    AVCC format (used inside CMSampleBuffer ``sdat``)::

        [4-byte BE length][NAL unit][4-byte BE length][NAL unit]...

    Annex B format (used by standard decoders like FFmpeg/PyAV)::

        [0x00000001][NAL unit][0x00000001][NAL unit]...

    This is a simple, deterministic conversion — no heuristic scanning needed
    because the input is already the isolated ``sdat`` section.

    Args:
        avcc_data: Raw AVCC-encoded bytes from the ``sdat`` section.

    Returns:
        H.264 data in Annex B format, or ``None`` if no valid NAL units found.
    """
    result = bytearray()
    pos = 0

    while pos + 4 <= len(avcc_data):
        nalu_len = struct.unpack_from(">I", avcc_data, pos)[0]
        pos += 4

        if nalu_len < 1 or pos + nalu_len > len(avcc_data):
            break

        result.extend(_ANNEX_B_START_CODE)
        result.extend(avcc_data[pos:pos + nalu_len])
        pos += nalu_len

    return bytes(result) if result else None


# ─── H.264 extraction from CMSampleBuffer ──────────────────────────

# Annex B start code used by standard H.264 decoders
_ANNEX_B_START_CODE = b"\x00\x00\x00\x01"


def extract_h264_from_feed(payload: bytes) -> Optional[bytes]:
    """Extract H.264 NAL units from a FEED packet's CMSampleBuffer.

    Uses structured CMSampleBuffer parsing to locate the ``sdat`` section,
    then performs a clean AVCC → Annex B conversion.

    Args:
        payload: Raw FEED packet payload bytes.

    Returns:
        H.264 data in Annex B format, or None if extraction failed.
    """
    parsed = parse_cmsamplebuffer(payload)
    if parsed and parsed.sample_data:
        annex_b = avcc_to_annex_b(parsed.sample_data)
        if annex_b:
            return annex_b
        logger.warning("AVCC→Annex B conversion failed for %d bytes of sdat", len(parsed.sample_data))
    else:
        logger.debug("No CMSampleBuffer/sdat found in FEED payload (%d bytes)", len(payload))
    return None



def extract_sps_pps_from_cvrp(payload: bytes) -> tuple[Optional[bytes], Optional[bytes]]:
    """Extract SPS and PPS NAL units from a CVRP packet's format description.

    The CVRP packet contains a CMFormatDescription which includes the
    H.264 decoder configuration record (avcC atom).

    Returns:
        Tuple of (sps_bytes, pps_bytes), either may be None if not found.
    """
    # Look for FDSC (format description) marker
    fdsc_idx = payload.find(Magic.FDSC)
    if fdsc_idx < 0:
        search_region = payload
    else:
        search_region = payload[fdsc_idx:]

    sps, pps = _try_parse_avcc_record(search_region)

    if sps:
        logger.info("Found SPS (%d bytes)", len(sps))
    if pps:
        logger.info("Found PPS (%d bytes)", len(pps))

    return (sps, pps)


def _try_parse_avcc_record(data: bytes) -> tuple[Optional[bytes], Optional[bytes]]:
    """Try to parse an AVCC decoder configuration record.

    AVCC format:
        [1: version=1][1: profile][1: compat][1: level]
        [1: NALU length size - 1 (masked with 0x03)]
        [1: SPS count (masked with 0x1F)]
        For each SPS: [2: SPS length (BE)][SPS data]
        [1: PPS count]
        For each PPS: [2: PPS length (BE)][PPS data]
    """
    sps = None
    pps = None

    # Scan for avcC start: version byte = 1, followed by reasonable profile
    for i in range(len(data) - 10):
        if data[i] != 1:
            continue

        profile = data[i + 1]
        # Valid H.264 profiles: Baseline(66), Main(77), High(100), etc.
        if profile not in (66, 77, 88, 100, 110, 122, 244):
            continue

        compat = data[i + 2]
        level = data[i + 3]

        # Level should be reasonable (1.0 to 6.2 → 10 to 62)
        if level < 10 or level > 62:
            continue

        # NALU length size
        nalu_length_size = (data[i + 4] & 0x03) + 1
        if nalu_length_size not in (1, 2, 4):
            continue

        # SPS count
        sps_count = data[i + 5] & 0x1F
        if sps_count < 1 or sps_count > 4:
            continue

        pos = i + 6
        # Read SPS entries
        for _ in range(sps_count):
            if pos + 2 > len(data):
                break
            sps_len = struct.unpack_from(">H", data, pos)[0]
            pos += 2
            if sps_len < 4 or pos + sps_len > len(data):
                break
            # Verify it's actually an SPS (NAL type 7)
            if (data[pos] & 0x1F) == 7:
                sps = bytes(data[pos:pos + sps_len])
            pos += sps_len

        if pos >= len(data):
            continue

        # PPS count
        pps_count = data[pos] if pos < len(data) else 0
        pos += 1

        for _ in range(pps_count):
            if pos + 2 > len(data):
                break
            pps_len = struct.unpack_from(">H", data, pos)[0]
            pos += 2
            if pps_len < 4 or pos + pps_len > len(data):
                break
            # Verify it's actually a PPS (NAL type 8)
            if (data[pos] & 0x1F) == 8:
                pps = bytes(data[pos:pos + pps_len])
            pos += pps_len

        if sps or pps:
            return (sps, pps)

    return (None, None)


def extract_sps_pps_from_fdsc(fdsc_bytes: bytes) -> tuple[Optional[bytes], Optional[bytes]]:
    """Extract SPS and PPS from a FormatDescription section in a CMSampleBuffer.

    On keyframes, the FEED CMSampleBuffer contains an ``fdsc`` section with the
    full CMFormatDescription, which includes the AVCC decoder configuration record
    containing updated SPS and PPS NAL units.

    This enables dynamic SPS/PPS updates (e.g. resolution changes) that the
    initial CVRP handshake cannot cover.

    Args:
        fdsc_bytes: Raw ``fdsc`` bytes **including** the section header
            (i.e. ``[4: length LE32][4: "fdsc" magic][data...]``).

    Returns:
        Tuple of ``(sps_bytes, pps_bytes)``, either may be ``None`` if not found.
    """
    return _try_parse_avcc_record(fdsc_bytes)


# ─── PCM audio extraction from CMSampleBuffer ──────────────────────

def extract_pcm_from_eat(payload: bytes) -> Optional[bytes]:
    """Extract raw PCM audio data from an EAT! packet's CMSampleBuffer.

    Uses structured CMSampleBuffer parsing to locate the ``sdat`` section
    containing raw PCM samples.

    Args:
        payload: Raw EAT! packet payload bytes.

    Returns:
        Raw PCM audio bytes (int16 stereo), or None if extraction failed.
    """
    parsed = parse_cmsamplebuffer(payload)
    if parsed and parsed.sample_data:
        frame_size = 4  # stereo int16 (2 channels × 2 bytes)
        aligned = (len(parsed.sample_data) // frame_size) * frame_size
        if aligned > 0:
            return parsed.sample_data[:aligned]
        logger.warning("PCM data too small for alignment: %d bytes", len(parsed.sample_data))
    else:
        logger.debug("No CMSampleBuffer/sdat found in EAT! payload (%d bytes)", len(payload))
    return None



