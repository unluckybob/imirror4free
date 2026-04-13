"""v2.4 Protocol Packet Builder & Parser (All magics reversed on wire)"""
import struct
from typing import Optional

class Magic:
    # Top-level (LE uint32 → appears reversed as bytes)
    PING = b"gnip"; SYNC = b"cnys"; ASYN = b"nysa"; RPLY = b"ylpr"
    # SYNC sub-types
    CWPA = b"apwc"; AFMT = b"tmfa"; CVRP = b"prvc"; CLOK = b"kolc"
    TIME = b"emit"; SKEW = b"weks"; OG = b"\x20\x21og"; STOP = b"pots"
    # ASYN sub-types
    FEED = b"deef"; EAT = b"!tae"; NEED = b"deen"
    HPD1 = b"1dph"; HPA1 = b"1aph"; HPD0 = b"0dph"; HPA0 = b"0aph"
    # CoreMedia serialization tags
    DICT = b"tcid"; KEYV = b"vyek"; STRK = b"krts"; STRV = b"vrts"
    BULV = b"vlub"; DATV = b"vtad"; NMBV = b"vbmn"

def build_ping() -> bytes:
    return struct.pack("<I4sII", 16, Magic.PING, 1, 0)

def build_rply_28(correlation_id: bytes, value: int) -> bytes:
    """Standard 28-byte RPLY (CWPA/CVRP/CLOK/SKEW/OG/STOP)"""
    return struct.pack("<I4s8sIQ", 28, Magic.RPLY, correlation_id, 0, value)

def build_time_reply(correlation_id: bytes, value_ns: int) -> bytes:
    """v2.4 §A8: 44-byte TIME reply with CMTime (flags=0)"""
    # CMTime: value(8) + timescale(4) + flags(4) + epoch(8)
    cmtime = struct.pack("<QIIQ", value_ns, 1_000_000_000, 0, 0)
    return struct.pack("<I4s8sI", 44, Magic.RPLY, correlation_id, 0) + cmtime

def build_afmt_rply(connection_id: bytes, tag: bytes) -> bytes:
    """v2.4 §A10: 62-byte AFMT-RPLY (42-byte payload + 20-byte header)"""
    payload = (b"tcid\x22\x00\x00\x00vyek\x0d\x00\x00\x00krtsError"
               b"\x0d\x00\x00\x00vbmn\x03\x00\x00\x00\x00\x00\x00\x00")
    return b"ylpr" + connection_id + tag + struct.pack("<I", len(payload)) + payload

def build_hpd1(clock_ref: bytes) -> bytes:
    """v2.4 §A6: HPD1 with 2560×1440 DisplaySize"""
    w = struct.pack("<d", 2560.0); h = struct.pack("<d", 1440.0)
    size_dict = (b"tcid\x2a\x00\x00\x00vyek\x13\x00\x00\x00krtsWidthvrts\x08\x00\x00\x00" + w +
                 b"vyek\x14\x00\x00\x00krtsHeightvrts\x08\x00\x00\x00" + h)
    main = (b"tcid\x5a\x00\x00\x00vyek\x0b\x00\x00\x00krtsValeriavlub\x01"
            b"vyek\x1b\x00\x00\x00krtsHEVCDecoderSupports444vlub\x01"
            b"vyek\x0d\x00\x00\x00krtsDisplaySize" + size_dict)
    return struct.pack("<I4s8s4s", 20+len(main), Magic.ASYN, clock_ref, Magic.HPD1) + main

def build_hpa1(audio_clock_ref: bytes) -> bytes:
    """v2.4 §A7: HPA1 with exact LPCM audio config"""
    asbd = struct.pack("<dIIIIII20x", 48000.0, 0x6C70636D, 0x0C, 4, 1, 4, 2, 16)
    d = (b"tcid\x6a\x00\x00\x00vyek\x10\x00\x00\x00krtsBufferAheadIntervalnmbv\x06"
         + struct.pack("<d", 0.073) +
         b"vyek\x0f\x00\x00\x00krtsdeviceUIDvrts\x07\x00\x00\x00Valeria"
         b"vyek\x0e\x00\x00\x00krtsScreenLatencynmbv\x06" + struct.pack("<d", 0.040)
         b"vyek\x40\x00\x00\x00krtsformatsdatv\x38\x00\x00\x00" + asbd
         b"vyek\x13\x00\x00\x00krtsEDIDAC3Supportvlub\x00"
         b"vyek\x10\x00\x00\x00krtsdeviceNamevrts\x07\x00\x00\x00Valeria")
    return struct.pack("<I4s8s4s", 20+len(d), Magic.ASYN, audio_clock_ref, Magic.HPA1) + d

def build_need(clock_ref: bytes) -> bytes:
    return struct.pack("<I4s8s4s", 20, Magic.ASYN, clock_ref, Magic.NEED)

def build_hpd0() -> bytes:
    return struct.pack("<I4s8s4s", 20, Magic.ASYN, b"\x01\x00\x00\x00\x00\x00\x00\x00", Magic.HPD0)

def build_hpa0(audio_clock_ref: bytes) -> bytes:
    return struct.pack("<I4s8s4s", 20, Magic.ASYN, audio_clock_ref, Magic.HPA0)

def avcc_to_annexb(avcc_ bytes) -> Optional[bytes]:
    out, i = bytearray(), 0
    while i + 4 <= len(avcc_data):
        n = struct.unpack_from(">I", avcc_data, i)[0]; i += 4
        if n < 1 or i + n > len(avcc_data): break
        out.extend(b"\x00\x00\x00\x01" + avcc_data[i:i+n]); i += n
    return bytes(out) if out else None

def parse_frame_length(data: bytes) -> tuple[Optional[int], bytes]:
    if len(data) < 4: return None, data
    total = struct.unpack_from("<I", data, 0)[0]
    return (total, data[4:total], data[total:]) if total <= len(data) else (None, data)
