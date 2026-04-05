"""
Valeria Protocol — Apple's USB AV Streaming Protocol.

This is the Phase 2 capture backend that communicates directly with the iPhone
over USB bulk endpoints to receive H.264 video and PCM audio streams.

Protocol flow:
1. Send USB control request to enable hidden QT configuration
2. iPhone disconnects and reconnects with additional USB endpoints
3. Claim the AV bulk endpoints
4. Perform PING handshake
5. Handle SYNC messages (CWPA, AFMT, CVRP, CLOK, TIME, SKEW)
6. Send ASYN HPD1/HPA1 to start streaming
7. Receive FEED (video) and EAT! (audio) packets
8. Send NEED packets to keep video flowing

Windows notes:
- Requires iTunes installed (Apple Mobile Device Support provides usbmuxd)
- May require WinUSB driver via Zadig for raw USB access
- The hidden QT config adds 2 extra bulk endpoints for AV data

Reference: https://github.com/danielpaulus/quicktime_video_hack
"""

import logging
import struct
import threading
import time
from typing import Optional, Callable

from imirror.usb.packets import (
    Magic, PacketType, Packet, VideoFrame, AudioSample,
    read_packet, build_ping, build_rply_with_clock,
    build_rply_with_dict_error, build_asyn_need,
    build_asyn_hpd1, build_asyn_hpa1, build_asyn_hpd0,
    build_asyn_hpa0, build_cmtime, extract_h264_from_feed,
)

logger = logging.getLogger(__name__)

# USB constants for the Valeria protocol
APPLE_VENDOR_ID = 0x05AC
QT_CONFIG_CONTROL_REQUEST = 0x52
QT_CONFIG_SUBCLASS = 0x2A
USBMUX_SUBCLASS = 0xFE


class ValeriaSession:
    """
    Manages a Valeria AV streaming session with an iPhone.

    This class handles the full lifecycle:
    - Enabling the hidden QT USB configuration
    - Protocol handshake (PING, SYNC exchanges)
    - Receiving and dispatching video/audio frames
    - Clean shutdown

    Status: Phase 2 — In Development
    Currently provides the protocol framework. Full USB endpoint
    communication requires platform-specific USB driver setup.
    """

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Protocol state
        self._device_audio_clock_ref: bytes = b"\x00" * 8
        self._device_video_clock_ref: bytes = b"\x00" * 8
        self._local_audio_clock_ref: bytes = b"\x00" * 8
        self._local_video_clock_ref: bytes = b"\x00" * 8
        self._local_clock_ref: bytes = b"\x00" * 8

        # Clock counter for generating unique refs
        self._clock_counter = 0
        self._clock_lock = threading.Lock()

        # Session start time for CMTime calculations
        self._start_time_ns = 0

        # Frame callbacks
        self._on_video_frame: Optional[Callable[[VideoFrame], None]] = None
        self._on_audio_sample: Optional[Callable[[AudioSample], None]] = None

        # Stats
        self.frames_received = 0
        self.bytes_received = 0

    def on_video_frame(self, callback: Callable[[VideoFrame], None]) -> None:
        """Register callback for video frames."""
        self._on_video_frame = callback

    def on_audio_sample(self, callback: Callable[[AudioSample], None]) -> None:
        """Register callback for audio samples."""
        self._on_audio_sample = callback

    def _generate_clock_ref(self) -> bytes:
        """Generate a unique 8-byte clock reference."""
        with self._clock_lock:
            self._clock_counter += 1
            # Use a combination of counter and memory-like address
            ref = struct.pack("<Q", 0x7F00A66CE20CB000 + self._clock_counter * 0x10)
            return ref

    def _get_current_cmtime_ns(self) -> int:
        """Get current time in nanoseconds since session start."""
        return time.monotonic_ns() - self._start_time_ns

    # ─── Protocol handlers ──────────────────────────────────────────

    def handle_packet(self, packet: Packet) -> Optional[bytes]:
        """Process an incoming packet and return response bytes (if needed).

        Returns:
            Response bytes to send back, or None if no response needed.
        """
        if packet.packet_type == PacketType.PING:
            return self._handle_ping(packet)
        elif packet.packet_type == PacketType.SYNC:
            return self._handle_sync(packet)
        elif packet.packet_type == PacketType.ASYN:
            self._handle_asyn(packet)
            return None
        return None

    def _handle_ping(self, packet: Packet) -> bytes:
        """Respond to PING with our own PING."""
        logger.info("🏓 PING received — sending PING response")
        self._start_time_ns = time.monotonic_ns()
        return build_ping()

    def _handle_sync(self, packet: Packet) -> Optional[bytes]:
        """Route SYNC packets to the appropriate handler."""
        subtype = packet.subtype
        corr_id = packet.correlation_id

        if not corr_id:
            logger.warning("SYNC packet without correlation ID")
            return None

        if subtype == Magic.CWPA:
            return self._handle_cwpa(packet, corr_id)
        elif subtype == Magic.AFMT:
            return self._handle_afmt(packet, corr_id)
        elif subtype == Magic.CVRP:
            return self._handle_cvrp(packet, corr_id)
        elif subtype == Magic.CLOK:
            return self._handle_clok(packet, corr_id)
        elif subtype == Magic.TIME:
            return self._handle_time(packet, corr_id)
        elif subtype == Magic.SKEW:
            return self._handle_skew(packet, corr_id)
        elif subtype == Magic.OG:
            return self._handle_og(packet, corr_id)
        elif subtype == Magic.STOP:
            return self._handle_stop(packet, corr_id)
        else:
            logger.debug("Unknown SYNC subtype: %s", subtype)
            return None

    def _handle_cwpa(self, packet: Packet, corr_id: bytes) -> bytes:
        """CWPA — Create audio clock. Device sends its audio clock ref, we reply with ours."""
        # Extract device audio clock ref (last 8 bytes of payload after corr_id)
        if len(packet.payload) >= 16:
            self._device_audio_clock_ref = packet.payload[8:16]
        else:
            self._device_audio_clock_ref = packet.payload[8:] if len(packet.payload) > 8 else b"\x00" * 8

        self._local_audio_clock_ref = self._generate_clock_ref()
        logger.info("🔊 CWPA: Device audio clock=%s, our clock=%s",
                     self._device_audio_clock_ref.hex(),
                     self._local_audio_clock_ref.hex())

        return build_rply_with_clock(corr_id, 0, self._local_audio_clock_ref)

    def _handle_afmt(self, packet: Packet, corr_id: bytes) -> bytes:
        """AFMT — Audio format description. Reply with zero error."""
        logger.info("🎵 AFMT: Audio format received (48kHz LPCM)")
        return build_rply_with_dict_error(corr_id, error=0)

    def _handle_cvrp(self, packet: Packet, corr_id: bytes) -> bytes:
        """CVRP — Create video clock. Contains H.264 format description with SPS/PPS."""
        # Extract device video clock ref
        if len(packet.payload) >= 16:
            self._device_video_clock_ref = packet.payload[8:16]

        self._local_video_clock_ref = self._generate_clock_ref()
        logger.info("📹 CVRP: Device video clock=%s, our clock=%s",
                     self._device_video_clock_ref.hex(),
                     self._local_video_clock_ref.hex())

        # TODO: Parse the CVRP dictionary to extract H.264 SPS/PPS NALUs
        # These are needed to initialize the hardware decoder

        return build_rply_with_clock(corr_id, 0, self._local_video_clock_ref)

    def _handle_clok(self, packet: Packet, corr_id: bytes) -> bytes:
        """CLOK — Create a new clock. Reply with our clock ref."""
        self._local_clock_ref = self._generate_clock_ref()
        logger.debug("🕐 CLOK: Created clock %s", self._local_clock_ref.hex())
        return build_rply_with_clock(corr_id, 0, self._local_clock_ref)

    def _handle_time(self, packet: Packet, corr_id: bytes) -> bytes:
        """TIME — Send current CMTime for our clock."""
        current_ns = self._get_current_cmtime_ns()
        cmtime = build_cmtime(current_ns)
        logger.debug("⏱️ TIME: Sending %d ns", current_ns)

        from imirror.usb.packets import build_rply
        payload = struct.pack("<I", 0) + cmtime
        return build_rply(corr_id, payload)

    def _handle_skew(self, packet: Packet, corr_id: bytes) -> bytes:
        """SKEW — Report clock skew. We report 48000.0 (perfectly aligned)."""
        logger.debug("📐 SKEW: Reporting 48000.0 (aligned)")
        from imirror.usb.packets import build_rply
        payload = struct.pack("<Id", 0, 48000.0)
        return build_rply(corr_id, payload)

    def _handle_og(self, packet: Packet, corr_id: bytes) -> bytes:
        """OG — Unknown purpose. Reply with 8 zero bytes."""
        from imirror.usb.packets import build_rply
        return build_rply(corr_id, b"\x00" * 8)

    def _handle_stop(self, packet: Packet, corr_id: bytes) -> bytes:
        """STOP — Stop our clock. Reply with 8 zero bytes."""
        logger.info("⏹️ STOP: Stopping clock")
        from imirror.usb.packets import build_rply
        return build_rply(corr_id, b"\x00" * 8)

    def _handle_asyn(self, packet: Packet) -> None:
        """Handle ASYN packets (video frames, audio samples, properties)."""
        subtype = packet.subtype

        if subtype == Magic.FEED:
            self._handle_feed(packet)
        elif subtype == Magic.EAT:
            self._handle_eat(packet)
        elif subtype == Magic.SPRP:
            logger.debug("SPRP: Set property received")
        elif subtype == Magic.SRAT:
            logger.debug("SRAT: Set rate/anchor received")
        elif subtype == Magic.TBAS:
            logger.debug("TBAS: Set timebase received")
        elif subtype == Magic.TJMP:
            logger.debug("TJMP: Time jump received")
        elif subtype == Magic.RELS:
            logger.debug("RELS: Clock released")

    def _handle_feed(self, packet: Packet) -> None:
        """FEED — H.264 video data in a CMSampleBuffer."""
        self.frames_received += 1
        self.bytes_received += len(packet.payload)

        h264_data = extract_h264_from_feed(packet.payload)
        if h264_data and self._on_video_frame:
            frame = VideoFrame(
                data=h264_data,
                timestamp_ns=self._get_current_cmtime_ns(),
                is_keyframe=self.frames_received == 1,  # Simplified detection
            )
            self._on_video_frame(frame)

    def _handle_eat(self, packet: Packet) -> None:
        """EAT! — PCM audio data in a CMSampleBuffer."""
        if self._on_audio_sample:
            sample = AudioSample(
                data=packet.payload,
                timestamp_ns=self._get_current_cmtime_ns(),
            )
            self._on_audio_sample(sample)

    # ─── Session control ────────────────────────────────────────────

    def build_start_streaming_packets(self) -> list[bytes]:
        """Build the packets needed to start AV streaming after handshake.

        Call this after receiving CVRP to begin the video/audio stream.
        Returns a list of packets to send in order.
        """
        packets = []
        packets.append(build_asyn_hpd1())
        if self._device_audio_clock_ref != b"\x00" * 8:
            packets.append(build_asyn_hpa1(self._device_audio_clock_ref))
        # Start sending NEED packets
        if self._device_video_clock_ref != b"\x00" * 8:
            packets.append(build_asyn_need(self._device_video_clock_ref))
        return packets

    def build_need_packet(self) -> bytes:
        """Build a NEED packet to request more video frames."""
        return build_asyn_need(self._device_video_clock_ref)

    def build_stop_streaming_packets(self) -> list[bytes]:
        """Build packets to cleanly stop streaming."""
        packets = []
        if self._device_audio_clock_ref != b"\x00" * 8:
            packets.append(build_asyn_hpa0(self._device_audio_clock_ref))
        packets.append(build_asyn_hpd0())
        return packets
