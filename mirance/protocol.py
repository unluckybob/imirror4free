"""
iPhone USB QuickTime Mirroring Protocol Implementation

Based on: iPhone_USB_Mirror_Dev_Guide.md (April 2026)
PCAP source: anym_capture.pcapng (29,324 frames)

Key details:
- USB QuickTime mode activation (control transfer 0x52)
- REVERSED magic bytes on wire
- Handshake state machine (PING → CWPA → HPD1 → CVRP → HPA1 → CLOK → TIME → AFMT → SKEW → OG)
- Flow control (NEED after every FEED)
- HEVC decoding with VPS/SPS/PPS extraction
"""

import struct
from enum import IntEnum
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass


# =============================================================================
# CONSTANTS - REVERSED magic bytes (stored reversed on wire!)
# =============================================================================

class PacketType(IntEnum):
    """All packet type codes - NOTE: stored REVERSED on wire!"""
    ASYN = 0x6173796E  # 'asyn' → 6E 79 73 61 (nysa on wire)
    SYNC = 0x73796E63  # 'sync' → 63 6E 79 73 (cnys on wire)
    RPLY = 0x72706C79  # 'rply' → 79 6C 70 72 (ylpr on wire)
    HPD0 = 0x68706431  # 'hpd1' → 31 64 70 68 (1dph on wire) - Disable display
    HPD1 = 0x68706431  # 'hpd1' → 31 64 70 68 (1dph on wire) - Enable display
    HPA0 = 0x68706131  # 'hpa1' → 31 61 70 68 (1aph on wire) - Disable audio
    HPA1 = 0x68706131  # 'hpa1' → 31 61 70 68 (1aph on wire) - Enable audio
    AFMT = 0x61666D74  # 'afmt' → 74 6D 66 61 (tmfa on wire)
    CVRP = 0x63767270  # 'cvrp' → 70 72 76 63 (prvc on wire)
    FEED = 0x64656566  # 'feed' → 66 65 65 64 (feed on wire) - Video frame
    EAT  = 0x65617421  # '!tae' → 21 74 61 65 (!tae on wire) - Audio data
    NEED = 0x6465656E  # 'need' → 6E 65 65 64 (neee on wire) - Flow control
    PING = 0x70696E67  # 'ping' → 70 6E 69 67 (gnip on wire)
    CWPA = 0x70617763  # 'cwpa' → 63 77 70 61 (cwap on wire)
    CLOK = 0x6F6B6F6C  # 'clok' → 6C 6F 6B 6F (loko on wire)
    TIME = 0x74696D65  # 'time' → 65 6D 69 74 (emit on wire)
    SKEW = 0x736B6577  # 'skew' → 77 65 6B 73 (weks on wire)
    OG  = 0x006F6700  # 'og\\x00' → 00 67 6F 00 (og on wire)


# Chunk size and pending reads for low latency
CHUNK_SIZE = 4096
PENDING_READS = 5

# Buffer settings (pcap-confirmed)
DEFAULT_BUFFER_AHEAD_MS = 73
MIN_BUFFER_AHEAD_MS = 40
MAX_BUFFER_AHEAD_MS = 73
SCREEN_LATENCY_MS = 40


# =============================================================================
# WIRE FORMAT HELPERS
# =============================================================================

def packet_type_to_wire(pt: PacketType) -> bytes:
    """Convert PacketType to 4-byte wire format (little-endian uint32)"""
    return struct.pack('<I', int(pt))


def wire_to_packet_type(data: bytes) -> Optional[PacketType]:
    """Convert 4-byte wire format to PacketType"""
    if len(data) < 4:
        return None
    value = struct.unpack_from('<I', data)[0]
    try:
        return PacketType(value)
    except ValueError:
        return None


def read_packet(stream) -> Tuple[PacketType, bytes]:
    """
    Read a length-prefixed packet from stream.
    Returns (packet_type, payload)
    
    Wire format:
    - 4 bytes LE: total length (includes the 4-byte header!)
    - Followed by payload
    """
    # Read 4-byte length prefix
    header = stream.read(4)
    if len(header) < 4:
        raise EOFError("Incomplete length header")
    
    total_length = struct.unpack_from('<I', header)[0]
    payload_length = total_length - 4
    
    # Read payload
    payload = stream.read(payload_length)
    if len(payload) < payload_length:
        raise EOFError(f"Incomplete packet: expected {payload_length}, got {len(payload)}")
    
    # First 4 bytes of payload is packet type
    packet_type = wire_to_packet_type(payload[:4])
    packet_payload = payload[4:]
    
    return packet_type, packet_payload


def send_packet(stream, packet_type: PacketType, payload: bytes = b'') -> None:
    """Send a length-prefixed packet to stream"""
    # Build packet: packet_type (4 bytes) + payload
    full_payload = bytes(packet_type_to_wire(packet_type)) + payload
    
    # Add length prefix (includes the 4-byte header!)
    header = struct.pack('<I', len(full_payload) + 4)
    
    stream.write(header + full_payload)


# =============================================================================
# CMSampleBuffer PARSING (from fdsc block)
# =============================================================================

class CMSampleBuffer:
    """Parse CMSampleBuffer from FEED/EAT packets"""
    
    # Sub-block tags (little-endian)
    TAG_SBUF = 0x73627566  # 'sbuf'
    TAG_OPTS = 0x6F707473  # 'opts' - OutputPresentationTimestamp
    TAG_STIA = 0x73746961  # 'stia' - SampleTimingInfo array (3×CMTime per entry)
    TAG_SDAT = 0x73646174  # 'sdat' - raw NALU data (HEVC AVCC format)
    TAG_SATT = 0x73617474  # 'satt' - sample attachments dict
    TAG_SARY = 0x73617279  # 'sary' - secondary array
    TAG_SSIZ = 0x7373697A  # 'ssiz' - sample sizes array
    TAG_NSMP = 0x6E736D70  # 'nsmp' - number of samples
    TAG_FDSC = 0x66647363  # 'fdsc' - FormatDescription (contains 'form' tag)
    
    # 'form' tag (BIG-ENDIAN!)
    TAG_FORM = 0x666F726D
    
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0
        self._parsed = {}
    
    def read_tag(self) -> Tuple[int, int]:
        """Read tag and size (both 4 bytes each)"""
        if self.offset + 8 > len(self.data):
            return 0, 0
        tag = struct.unpack_from('>I', self.data, self.offset)[0]  # Big-endian!
        size = struct.unpack_from('>I', self.data, self.offset + 4)[0]  # Big-endian!
        return tag, size
    
    def find_fdsc_extradata(self) -> Optional[bytes]:
        """
        Find and extract VPS+SPS+PPS from fdsc block.
        This is needed to initialize the HEVC decoder.
        """
        self.offset = 0
        
        while self.offset < len(self.data) - 8:
            tag, size = self.read_tag()
            
            if tag == self.TAG_FDSC:
                # Found FormatDescription - now parse inner 'form' tag
                self.offset += 8  # Skip tag + size
                return self._parse_hvcc_from_form(size - 8)
            
            self.offset += 8 + size
        
        return None
    
    def _parse_hvcc_from_form(self, form_size: int) -> Optional[bytes]:
        """Parse hvcC (HEVCDecoderConfigurationRecord) from 'form' tag"""
        end = self.offset + form_size
        
        while self.offset < end - 8:
            tag, size = self.read_tag()
            
            if tag == 0x68766343:  # 'hvcC' (big-endian)
                # Found hvcC! Extract VPS+SPS+PPS
                return self._extract_param_sets(size - 8)
            
            self.offset += 8 + size
        
        return None
    
    def _extract_param_sets(self, size: int) -> bytes:
        """Extract VPS (32), SPS (33), PPS (34) NAL units from hvcC"""
        # hvcC structure:
        #   configurationVersion: 1 byte
        #   profile: 1 byte  
        #   ...
        #   numOfArrays: 1 byte
        #   arrays[]: each contains nalUnitType, numNalus, nalus[]
        
        # For simplicity, extract all parameter sets (types 32, 33, 34)
        result = bytearray()
        
        config_version = self.data[self.offset]
        self.offset += 1
        
        # Skip to numOfArrays
        self.offset += 19  # profile to lengthSizeMinusOne
        
        if self.offset >= size:
            return bytes(result)
        
        num_arrays = self.data[self.offset]
        self.offset += 1
        
        for _ in range(num_arrays):
            if self.offset + 3 > size:
                break
            
            nal_unit_type = self.data[self.offset] & 0x3F  # Lower 6 bits
            num_nalus = struct.unpack_from('>H', self.data, self.offset + 1)[0]
            self.offset += 3
            
            # Extract NAL units for VPS (32), SPS (33), PPS (34)
            if nal_unit_type in (32, 33, 34):
                for _ in range(num_nalus):
                    if self.offset + 2 > size:
                        break
                    nal_size = struct.unpack_from('>H', self.data, self.offset)[0]
                    self.offset += 2
                    
                    nal_data = self.data[self.offset:self.offset + nal_size]
                    self.offset += nal_size
                    
                    # Add NAL unit header (nal_unit_type in lower 6 bits of first byte)
                    result.extend(nal_data)
        
        return bytes(result)


# =============================================================================
# CMTime PARSING
# =============================================================================

@dataclass
class CMTime:
    """CMTime structure (24 bytes)"""
    value: int      # uint64 LE - numerator
    timescale: int  # uint32 LE - usually 1,000,000,000 (nanoseconds)
    flags: int      # uint32 LE - 0x0 = valid
    epoch: int      # uint64 LE - usually 0
    
    @staticmethod
    def parse(data: bytes) -> 'CMTime':
        if len(data) < 24:
            return CMTime(0, 0, 0, 0)
        return CMTime(
            value=struct.unpack_from('<Q', data, 0)[0],
            timescale=struct.unpack_from('<I', data, 8)[0],
            flags=struct.unpack_from('<I', data, 12)[0],
            epoch=struct.unpack_from('<Q', data, 16)[0]
        )
    
    def seconds(self) -> float:
        if self.timescale == 0:
            return 0.0
        return self.value / self.timescale


# =============================================================================
# HANDHAKE STATE MACHINE
# =============================================================================

class HandshakeState:
    """Track handshake state"""
    PING_ECHOED = 0
    CWPA_SENT = 1
    HPD1_SENT = 2
    CVRP_RECEIVED = 3
    HPA1_SENT = 4
    CLOK_SENT = 5
    TIME_SENT = 6
    AFMT_SENT = 7
    SKEW_RECEIVED = 8
    OG_SENT = 9
    STREAMING = 10


class HandshakeHandler:
    """
    Handle the QuickTime mirroring handshake sequence.
    
    Sequence:
    1. PING → echo back
    2. CWPA → reply with deviceClockRef + 1000
    3. HPD1 → send TWICE with DisplaySize (e.g., 2560×1440)
    4. CVRP → reply with cwpa_clockRef + 0x1000AF
    5. HPA1 → 48kHz LPCM, BufferAhead=73ms, ScreenLatency=40ms
    6. CLOK → reply with cvrp_clockRef + 0x10000
    7. TIME → reply with current host CMTime
    8. AFMT → reply with exact 62-byte wire bytes
    9. SKEW → echo + apply drift correction
    10. OG → reply with 32-byte packet (0x01 payload)
    """
    
    def __init__(self):
        self.state = HandshakeState.PING_ECHOED
        self.device_clock_ref = 0
        self.cwpa_clock_ref = 0
        self.cvrp_clock_ref = 0
        self.display_width = 2560
        self.display_height = 1440
        self.valeria = False  # False = 4:2:0 NV12, True = 4:4:4 AYUV
    
    def handle_packet(self, packet_type: PacketType, payload: bytes) -> Optional[bytes]:
        """Handle incoming packet and return response payload if any"""
        
        if packet_type == PacketType.PING:
            # Just echo back
            self.state = HandshakeState.PING_ECHOED
            return b''
        
        elif packet_type == PacketType.CWPA:
            # Store device clock ref, respond with +1000
            if len(payload) >= 4:
                self.device_clock_ref = struct.unpack_from('<I', payload, 0)[0]
                self.cwpa_clock_ref = self.device_clock_ref + 1000
            self.state = HandshakeState.CWPA_SENT
            return struct.pack('<I', self.cwpa_clock_ref)
        
        elif packet_type == PacketType.CVRP:
            # Store cvrp clock ref, respond with +0x1000AF
            if len(payload) >= 4:
                self.cvrp_clock_ref = struct.unpack_from('<I', payload, 0)[0]
                response = self.cwpa_clock_ref + 0x1000AF
            self.state = HandshakeState.CVRP_RECEIVED
            return struct.pack('<I', response)
        
        elif packet_type == PacketType.CLOK:
            # Respond with +0x10000
            if len(payload) >= 4:
                clok_ref = struct.unpack_from('<I', payload, 0)[0]
                response = self.cvrp_clock_ref + 0x10000
            self.state = HandshakeState.CLOK_SENT
            return struct.pack('<I', response)
        
        elif packet_type == PacketType.TIME:
            # Return current host time as CMTime
            self.state = HandshakeState.TIME_SENT
            return self._create_cmtime_payload()
        
        elif packet_type == PacketType.SKEW:
            # Echo back + note for drift correction
            self.state = HandshakeState.SKEW_RECEIVED
            return payload  # Echo
        
        elif packet_type == PacketType.OG:
            # Respond with 32-byte packet (0x01 payload)
            self.state = HandshakeState.OG_SENT
            return struct.pack('<I', 1) + b'\x00' * 28
        
        return None
    
    def get_hpd1_payload(self) -> bytes:
        """Get HPD1 (Enable Display) payload"""
        # DisplaySize (uint32 × 2) + some flags
        # The exact format needs to be confirmed from pcap
        return struct.pack('<II', self.display_width, self.display_height)
    
    def get_hpa1_payload(self) -> bytes:
        """Get HPA1 (Enable Audio) payload with ASBD"""
        # HPA1 packet includes Audio Stream Basic Description (ASBD)
        # 48kHz LPCM, Stereo, 16-bit
        
        payload = bytearray()
        
        # Sample rate (double, LE): 48000.0
        payload.extend(struct.pack('<d', 48000.0))
        
        # 'lpcm' (0x6C70636D)
        payload.extend(b'lpcm')
        
        # mFormatFlags: 0x0C (SignedInt | Packed)
        payload.extend(struct.pack('<I', 0x0C))
        
        # mBytesPerPacket = 4
        payload.extend(struct.pack('<I', 4))
        
        # mFramesPerPacket = 1
        payload.extend(struct.pack('<I', 1))
        
        # mBytesPerFrame = 4
        payload.extend(struct.pack('<I', 4))
        
        # mChannelsPerFrame = 2
        payload.extend(struct.pack('<I', 2))
        
        # mBitsPerChannel = 16
        payload.extend(struct.pack('<I', 16))
        
        # Reserved (16 bytes)
        payload.extend(b'\x00' * 16)
        
        # BufferAheadInterval (73ms) and ScreenLatency (40ms)
        # These might be in a different format/location
        payload.extend(struct.pack('<I', DEFAULT_BUFFER_AHEAD_MS))
        payload.extend(struct.pack('<I', SCREEN_LATENCY_MS))
        
        return bytes(payload)
    
    def get_afmt_payload(self) -> bytes:
        """Get AFMT response payload (62 bytes, pcap-confirmed)"""
        # Exact 62-byte wire bytes from pcap - this is critical!
        # For now, return a placeholder that matches the expected structure
        payload = bytearray(62)
        
        # Sample rate (double, LE): 48000.0
        payload[0:8] = struct.pack('<d', 48000.0)
        
        # 'lpcm'
        payload[8:12] = b'lpcm'
        
        # mFormatFlags
        payload[12:16] = struct.pack('<I', 0x0C)
        
        # mBytesPerPacket
        payload[16:20] = struct.pack('<I', 4)
        
        # mFramesPerPacket  
        payload[20:24] = struct.pack('<I', 1)
        
        # mBytesPerFrame
        payload[24:28] = struct.pack('<I', 4)
        
        # mChannelsPerFrame
        payload[28:32] = struct.pack('<I', 2)
        
        # mBitsPerChannel
        payload[32:36] = struct.pack('<I', 16)
        
        return bytes(payload)
    
    def _create_cmtime_payload(self) -> bytes:
        """Create CMTime payload for TIME response"""
        import time
        now = int(time.time() * 1_000_000_000)  # nanoseconds
        return struct.pack('<QIIQ', now, 1_000_000_000, 0, 0)


# =============================================================================
# USB QuickTime MODE ACTIVATION
# =============================================================================

def activate_quicktime_mode(device) -> None:
    """
    Send control transfer to switch iPhone into QuickTime mode.
    
    Control transfer:
    - bmRequestType: 0x40 (vendor | host-to-device | device)
    - bRequest: 0x52
    - wValue: 0x0000
    - wIndex: 0x0002 (interface 2 - QuickTime)
    - data: empty
    """
    device.ctrl_transfer(
        bmRequestType=0x40,
        bRequest=0x52,
        wValue=0x0000,
        wIndex=0x0002,
        data_or_wLength=b''
    )


def deactivate_quicktime_mode(device) -> None:
    """
    Send control transfer to disable QuickTime mode (on teardown).
    """
    device.ctrl_transfer(
        bmRequestType=0x40,
        bRequest=0x52,
        wValue=0x0000,
        wIndex=0x0000,  # Different from enable!
        data_or_wLength=b''
    )


def find_qt_interface(dev):
    """
    Find USB interface with subclass 0x2A (QuickTime).
    
    Returns: (device, interface) or (None, None)
    """
    import usb.core
    
    for cfg in dev:
        for intf in cfg:
            if (intf.bInterfaceClass == 0xFF and 
                intf.bInterfaceSubClass == 0x2A):
                return dev, intf
    
    return None, None


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'PacketType',
    'CHUNK_SIZE',
    'PENDING_READS',
    'DEFAULT_BUFFER_AHEAD_MS',
    'MIN_BUFFER_AHEAD_MS', 
    'MAX_BUFFER_AHEAD_MS',
    'SCREEN_LATENCY_MS',
    'packet_type_to_wire',
    'wire_to_packet_type', 
    'read_packet',
    'send_packet',
    'CMSampleBuffer',
    'CMTime',
    'HandshakeState',
    'HandshakeHandler',
    'activate_quicktime_mode',
    'deactivate_quicktime_mode',
    'find_qt_interface',
]