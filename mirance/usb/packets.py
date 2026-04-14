"""
v2.4 Protocol Packet Builder & Parser.
All magic bytes are REVERSED on wire (ASYN→nysa, SYNC→cnys, etc.)
"""
import struct
from enum import Enum
from typing import Optional

# Import from root config.py (v2.4 latency values)
from config import (
    DEFAULT_DISPLAY_WIDTH, DEFAULT_DISPLAY_HEIGHT,
    AUDIO_BUFFER_AHEAD_INTERVAL, AUDIO_SCREEN_LATENCY
)

# ─── Packet Types ──────────────────────────────────────────────
class PacketType(Enum):
    """v2.4 packet type identifiers."""
    PING = 1
    SYNC = 2
    ASYN = 3
    RPLY = 4
    CWPA = 5
    AFMT = 6
    CVRP = 7
    CLOK = 8
    TIME = 9
    SKEW = 10

# ─── Wire-Endian Magic Bytes (v2.4 §A2.1 / §I7) ──────────────────
class Magic:
    PING = b"gnip"
    SYNC = b"cnys"
    ASYN = b"nysa"
    RPLY = b"ylpr"
    CWPA = b"apwc"
    AFMT = b"tmfa"
    CVRP = b"prvc"
    CLOK = b"kolc"
    TIME = b"emit"
    SKEW = b"weks"
    OG   = b"\x00\x00GO"
    STOP = b"pots"
    FEED = b"deef"
    EAT  = b"!tae"
    NEED = b"deen"
    HPD1 = b"1dph"
    HPA1 = b"1aph"
    HPD0 = b"0dph"
    HPA0 = b"0aph"
    RELS = b"sler"
    # CoreMedia serialization tags (LE FourCC)
    DICT = b"tcid"
    KEYV = b"vyek"
    STRK = b"krts"
    STRV = b"vrts"
    BULV = b"vlub"
    DATV = b"vtad"
    NMBV = b"vbmn"
    FDSC = b"csdf"
    SBUF = b"fubs"

# ─── Packet Builders ──────────────────────────────────────────────

def build_ping() -> bytes:
    return struct.pack("<I4sII", 16, Magic.PING, 1, 0)

def build_rply(correlation_id: bytes, value: int) -> bytes:
    """Standard 28-byte RPLY (CWPA/CVRP/CLOK/SKEW/OG/STOP)"""
    return struct.pack("<I4s8sIQ", 28, Magic.RPLY, correlation_id, 0, value)

def build_skew_reply(correlation_id: bytes, skew_ratio: float) -> bytes:
    """v2.4 §A9: 28-byte SKEW reply with float64 skew ratio at bytes 20-27."""
    return struct.pack("<I4s8sd", 28, Magic.RPLY, correlation_id, 0, skew_ratio)

def build_time_reply(correlation_id: bytes, value_ns: int) -> bytes:
    """v2.4 §A8: 44-byte TIME reply with CMTime (flags=0)"""
    # CMTime: value(8) + timescale(4) + flags(4) + epoch(8)
    cmtime = struct.pack("<QIIQ", value_ns, 1_000_000_000, 0, 0)  # flags=0, NOT 1
    return struct.pack("<I4s8sI", 44, Magic.RPLY, correlation_id, 0) + cmtime

def build_afmt_rply(connection_id: bytes, tag: bytes) -> bytes:
    """v2.4 §A10: 62-byte AFMT-RPLY (42-byte payload + 20-byte header)"""
    payload = (
        b"tcid\x22\x00\x00\x00"  # dict tag + size 34
        b"vyek\x0d\x00\x00\x00"  # keyv + key size 13
        b"krtsError"             # strk + "Error"
        b"\x0d\x00\x00\x00"      # value size 13
        b"vbmn\x03\x00\x00\x00\x00\x00\x00\x00"  # nmbv u32 = 0
    )
    return b"ylpr" + connection_id + tag + len(payload).to_bytes(4, "little") + payload

def build_asyn_hpd1() -> bytes:
    """v2.4 §A6: HPD1 with 2560×1440 DisplaySize (EmptyCFType=1 header)"""
    w = struct.pack("<d", float(DEFAULT_DISPLAY_WIDTH))
    h = struct.pack("<d", float(DEFAULT_DISPLAY_HEIGHT))
    
    size_dict = (
        b"tcid\x2a\x00\x00\x00"  # dict size 42
        b"vyek\x13\x00\x00\x00"  # key size 19
        b"krtsWidthvrts\x08\x00\x00\x00" + w +
        b"vyek\x14\x00\x00\x00"  # key size 20
        b"krtsHeightvrts\x08\x00\x00\x00" + h
    )
    
    main = (
        b"tcid\x5a\x00\x00\x00"  # dict size 90
        b"vyek\x0b\x00\x00\x00"  # key size 11
        b"krtsValeriavlub\x01"   # True = enable 4:4:4 chroma (better quality)
        b"vyek\x1b\x00\x00\x00"  # key size 27
        b"krtsHEVCDecoderSupports444vlub\x01"
        b"vyek\x0d\x00\x00\x00"  # key size 13
        b"krtsDisplaySize" + size_dict
    )
    
    pkt_len = 20 + len(main)
    # Header uses EmptyCFType (0x1)
    return struct.pack("<I4sQ4s", pkt_len, Magic.ASYN, 1, Magic.HPD1) + main

def build_asyn_hpa1(audio_clock_ref: bytes) -> bytes:
    """v2.4 §A7: HPA1 with exact LPCM audio config"""
    # 56-byte ASBD struct
    asbd = struct.pack("<dIIIIII20x",
        48000.0, 0x6C70636D, 0x0C, 4, 1, 4, 2, 16
    )
    
    buf_ahead = struct.pack("<d", AUDIO_BUFFER_AHEAD_INTERVAL)
    screen_lat = struct.pack("<d", AUDIO_SCREEN_LATENCY)
    
    d = (
        b"tcid\x6a\x00\x00\x00"  # dict size 106
        b"vyek\x10\x00\x00\x00"  # key size 16
        b"krtsBufferAheadIntervalnmbv\x06" + buf_ahead +
        b"vyek\x0f\x00\x00\x00"  # key size 15
        b"krtsdeviceUIDvrts\x07\x00\x00\x00Valeria"
        b"vyek\x0e\x00\x00\x00"  # key size 14
        b"krtsScreenLatencynmbv\x06" + screen_lat +
        b"vyek\x40\x00\x00\x00"  # key size 64
        b"krtsformatsdatv\x38\x00\x00\x00" + asbd +
        b"vyek\x13\x00\x00\x00"  # key size 19
        b"krtsEDIDAC3Supportvlub\x00"
        b"vyek\x10\x00\x00\x00"  # key size 16
        b"krtsdeviceNamevrts\x07\x00\x00\x00Valeria"
    )
    
    pkt_len = 20 + len(d)
    return struct.pack("<I4sQ4s", pkt_len, Magic.ASYN, struct.unpack("<Q", audio_clock_ref)[0], Magic.HPA1) + d

def build_asyn_need(cvrp_device_ref: bytes) -> bytes:
    """20-byte NEED flow-control packet"""
    return struct.pack("<I4sQ4s", 20, Magic.ASYN, struct.unpack("<Q", cvrp_device_ref)[0], Magic.NEED)

def build_asyn_hpd0() -> bytes:
    return struct.pack("<I4sQ4s", 20, Magic.ASYN, 1, Magic.HPD0)

def build_asyn_hpa0(audio_clock_ref: bytes) -> bytes:
    return struct.pack("<I4sQ4s", 20, Magic.ASYN, struct.unpack("<Q", audio_clock_ref)[0], Magic.HPA0)

# ─── AVCC → Annex-B Conversion ────────────────────────────────────
# ─── Data Structures ──────────────────────────────────────────────
class Packet:
    """Parsed USB packet with header + payload."""
    
    def __init__(self, packet_type: PacketType, magic: bytes, correlation_id: bytes, payload: bytes):
        self.packet_type = packet_type
        self.magic = magic
        self.correlation_id = correlation_id
        self.payload = payload
    
    @property
    def data(self) -> bytes:
        return self.payload
    
    def __repr__(self):
        return f"Packet({self.packet_type}, len={len(self.payload)})"


class VideoFrame:
    """Decoded H.264 video frame."""
    
    def __init__(self, data: bytes, timestamp: float, key_frame: bool = False):
        self.data = data
        self.timestamp = timestamp
        self.key_frame = key_frame
        self.width = 0
        self.height = 0
    
    def __repr__(self):
        return f"VideoFrame({self.width}x{self.height}, ts={self.timestamp:.3f}, key={self.key_frame})"


class AudioSample:
    """PCM audio sample."""
    
    def __init__(self, data: bytes, timestamp: float, sample_rate: int = 48000, channels: int = 2):
        self.data = data
        self.timestamp = timestamp
        self.sample_rate = sample_rate
        self.channels = channels
    
    def __repr__(self):
        return f"AudioSample({len(self.data)} bytes, ts={self.timestamp:.3f})"


# ─── Packet Reader ──────────────────────────────────────────────
def read_packet(data: bytes) -> Optional[Packet]:
    """Parse incoming USB packet."""
    if len(data) < 16:
        return None
    
    # Read header: length(4) + magic(4) + correlation(8)
    length = struct.unpack("<I", data[0:4])[0]
    magic = data[4:8]
    correlation = data[8:16]
    payload = data[16:16+length-20] if length > 20 else b""
    
    # Map magic to packet type
    pkt_type = PacketType.PING  # default
    for pt in PacketType:
        if getattr(Magic, pt.name, b"") == magic:
            pkt_type = pt
            break
    
    return Packet(pkt_type, magic, correlation, payload)


def avcc_to_annexb(avcc_data: bytes) -> Optional[bytes]:
    out = bytearray()
    pos = 0
    while pos + 4 <= len(avcc_data):
        nalu_len = struct.unpack_from(">I", avcc_data, pos)[0]  # Note the ">"
        pos += 4
        if nalu_len < 1 or pos + nalu_len > len(avcc_data):
            break
        out.extend(b"\x00\x00\x00\x01")
        out.extend(avcc_data[pos:pos+nalu_len])
        pos += nalu_len
    return bytes(out) if out else None
