"""
Valeria Protocol Session Handler.

Manages the Valeria protocol state machine for AV streaming.
This is a pure protocol handler — it receives parsed packets and
produces response bytes. USB I/O is handled by endpoint.py and
the streaming thread in stream.py.

Protocol flow:
1. PING handshake
2. SYNC negotiations (CWPA, AFMT, CVRP, CLOK, TIME, SKEW)
3. Build start/stop streaming commands (HPD1/HPA1/HPD0/HPA0)
4. Route FEED (video) and EAT! (audio) to callbacks

Reference: https://github.com/danielpaulus/quicktime_video_hack
"""

import logging
import struct
import threading
import time
from typing import Optional, Callable
from enum import Enum
from dataclasses import dataclass, field

from imirror.usb.packets import (
    Magic, PacketType, Packet, VideoFrame, AudioSample,
    build_ping, build_rply, build_rply_with_clock,
    build_rply_with_dict_error, build_asyn_need,
    build_asyn_hpd1, build_asyn_hpa1, build_asyn_hpd0,
    build_asyn_hpa0, build_cmtime, extract_h264_from_feed,
    extract_pcm_from_eat, extract_sps_pps_from_cvrp,
    parse_cmsamplebuffer, avcc_to_annex_b, extract_sps_pps_from_fdsc,
)

logger = logging.getLogger(__name__)


class HandshakeState(Enum):
    """Tracks the protocol handshake progress."""
    WAITING_PING = "waiting_ping"
    PING_DONE = "ping_done"
    NEGOTIATING = "negotiating"     # Handling SYNC messages
    READY = "ready"                 # All negotiations complete, can start streaming


@dataclass
class SessionStats:
    """Thread-safe session statistics."""
    frames_received: int = 0
    audio_samples_received: int = 0
    bytes_received: int = 0
    keyframes_received: int = 0
    decode_errors: int = 0
    last_frame_time: float = 0.0
    session_start_time: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def uptime_seconds(self) -> float:
        if self.session_start_time <= 0:
            return 0.0
        return time.monotonic() - self.session_start_time

    @property
    def average_fps(self) -> float:
        uptime = self.uptime_seconds
        if uptime <= 0:
            return 0.0
        return self.frames_received / uptime

    @property
    def bandwidth_mbps(self) -> float:
        uptime = self.uptime_seconds
        if uptime <= 0:
            return 0.0
        return (self.bytes_received * 8) / (uptime * 1_000_000)

    def record_frame(self, size: int, is_keyframe: bool) -> None:
        with self._lock:
            self.frames_received += 1
            self.bytes_received += size
            self.last_frame_time = time.monotonic()
            if is_keyframe:
                self.keyframes_received += 1

    def record_audio(self) -> None:
        with self._lock:
            self.audio_samples_received += 1

    def record_decode_error(self) -> None:
        with self._lock:
            self.decode_errors += 1

    def snapshot(self) -> dict:
        """Return a snapshot of current stats for the UI."""
        with self._lock:
            return {
                "frames": self.frames_received,
                "keyframes": self.keyframes_received,
                "audio_samples": self.audio_samples_received,
                "bytes": self.bytes_received,
                "decode_errors": self.decode_errors,
                "uptime": self.uptime_seconds,
                "avg_fps": self.average_fps,
                "bandwidth_mbps": self.bandwidth_mbps,
            }


class ValeriaSession:
    """
    Manages a Valeria AV streaming session with an iPhone.

    This class handles the full protocol lifecycle:
    - PING handshake
    - SYNC negotiations (CWPA, AFMT, CVRP, CLOK, TIME, SKEW)
    - Dispatching video frames (FEED) and audio samples (EAT!)
    - Building start/stop streaming commands
    - Clean shutdown
    """

    def __init__(self):
        # Handshake state tracking
        self._handshake_state = HandshakeState.WAITING_PING
        self._cwpa_received = False
        self._afmt_received = False
        self._cvrp_received = False

        # Protocol state — clock references
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

        # Video format info (populated from CVRP)
        self._sps: Optional[bytes] = None
        self._pps: Optional[bytes] = None
        self._video_width: int = 0
        self._video_height: int = 0

        # Frame callbacks
        self._on_video_frame: Optional[Callable[[VideoFrame], None]] = None
        self._on_audio_sample: Optional[Callable[[AudioSample], None]] = None

        # Thread-safe stats
        self.stats = SessionStats()

    # ─── Callback registration ──────────────────────────────────────

    def on_video_frame(self, callback: Callable[[VideoFrame], None]) -> None:
        """Register callback for video frames."""
        self._on_video_frame = callback

    def on_audio_sample(self, callback: Callable[[AudioSample], None]) -> None:
        """Register callback for audio samples."""
        self._on_audio_sample = callback

    # ─── State queries ──────────────────────────────────────────────

    @property
    def handshake_state(self) -> HandshakeState:
        return self._handshake_state

    @property
    def is_ready_to_stream(self) -> bool:
        return self._cvrp_received

    @property
    def video_format(self) -> dict:
        return {
            "width": self._video_width,
            "height": self._video_height,
            "has_sps": self._sps is not None,
            "has_pps": self._pps is not None,
        }

    @property
    def is_healthy(self) -> bool:
        """Check if we've received data recently."""
        if self.stats.last_frame_time <= 0:
            return True  # Haven't started streaming yet
        return (time.monotonic() - self.stats.last_frame_time) < 10.0

    # ─── Clock management ───────────────────────────────────────────

    def _generate_clock_ref(self) -> bytes:
        with self._clock_lock:
            self._clock_counter += 1
            ref = struct.pack("<Q", 0x7F00A66CE20CB000 + self._clock_counter * 0x10)
            return ref

    def _get_current_cmtime_ns(self) -> int:
        return time.monotonic_ns() - self._start_time_ns

    # ─── Protocol handlers ──────────────────────────────────────────

    def handle_packet(self, packet: Packet) -> Optional[bytes]:
        """Process an incoming packet and return response bytes (if needed)."""
        if packet.packet_type == PacketType.PING:
            return self._handle_ping(packet)
        elif packet.packet_type == PacketType.SYNC:
            return self._handle_sync(packet)
        elif packet.packet_type == PacketType.ASYN:
            self._handle_asyn(packet)
            return None
        return None

    def _handle_ping(self, packet: Packet) -> bytes:
        logger.info("PING received — sending PING response")
        self._start_time_ns = time.monotonic_ns()
        self.stats.session_start_time = time.monotonic()
        self._handshake_state = HandshakeState.PING_DONE
        return build_ping()

    def _handle_sync(self, packet: Packet) -> Optional[bytes]:
        subtype = packet.subtype
        corr_id = packet.correlation_id

        if not corr_id:
            logger.warning("SYNC packet without correlation ID")
            return None

        if self._handshake_state == HandshakeState.PING_DONE:
            self._handshake_state = HandshakeState.NEGOTIATING

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
        if len(packet.payload) >= 16:
            self._device_audio_clock_ref = packet.payload[8:16]
        else:
            self._device_audio_clock_ref = packet.payload[8:] if len(packet.payload) > 8 else b"\x00" * 8

        self._local_audio_clock_ref = self._generate_clock_ref()
        self._cwpa_received = True

        logger.info("CWPA: Device audio clock=%s, our clock=%s",
                     self._device_audio_clock_ref.hex(),
                     self._local_audio_clock_ref.hex())

        return build_rply_with_clock(corr_id, 0, self._local_audio_clock_ref)

    def _handle_afmt(self, packet: Packet, corr_id: bytes) -> bytes:
        self._afmt_received = True
        logger.info("AFMT: Audio format received (48kHz LPCM)")
        return build_rply_with_dict_error(corr_id, error=0)

    def _handle_cvrp(self, packet: Packet, corr_id: bytes) -> bytes:
        if len(packet.payload) >= 16:
            self._device_video_clock_ref = packet.payload[8:16]

        self._local_video_clock_ref = self._generate_clock_ref()
        self._cvrp_received = True

        logger.info("CVRP: Device video clock=%s, our clock=%s",
                     self._device_video_clock_ref.hex(),
                     self._local_video_clock_ref.hex())

        # Extract SPS/PPS from the format description
        sps, pps = extract_sps_pps_from_cvrp(packet.payload)
        if sps:
            self._sps = sps
            logger.info("SPS extracted: %d bytes (profile=%d, level=%d)",
                       len(sps), sps[1] if len(sps) > 1 else 0,
                       sps[3] if len(sps) > 3 else 0)
        if pps:
            self._pps = pps
            logger.info("PPS extracted: %d bytes", len(pps))

        self._handshake_state = HandshakeState.READY
        logger.info("Handshake complete — ready to stream")

        return build_rply_with_clock(corr_id, 0, self._local_video_clock_ref)

    def _handle_clok(self, packet: Packet, corr_id: bytes) -> bytes:
        self._local_clock_ref = self._generate_clock_ref()
        logger.debug("CLOK: Created clock %s", self._local_clock_ref.hex())
        return build_rply_with_clock(corr_id, 0, self._local_clock_ref)

    def _handle_time(self, packet: Packet, corr_id: bytes) -> bytes:
        current_ns = self._get_current_cmtime_ns()
        cmtime = build_cmtime(current_ns)
        logger.debug("TIME: Sending %d ns", current_ns)
        payload = struct.pack("<I", 0) + cmtime
        return build_rply(corr_id, payload)

    def _handle_skew(self, packet: Packet, corr_id: bytes) -> bytes:
        logger.debug("SKEW: Reporting 48000.0 (aligned)")
        payload = struct.pack("<Id", 0, 48000.0)
        return build_rply(corr_id, payload)

    def _handle_og(self, packet: Packet, corr_id: bytes) -> bytes:
        return build_rply(corr_id, b"\x00" * 8)

    def _handle_stop(self, packet: Packet, corr_id: bytes) -> bytes:
        logger.info("STOP: Stopping clock")
        return build_rply(corr_id, b"\x00" * 8)

    def _handle_asyn(self, packet: Packet) -> None:
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
        parsed = parse_cmsamplebuffer(packet.payload)
        if not parsed or not parsed.sample_data:
            # Fallback to old method
            h264_data = extract_h264_from_feed(packet.payload)
        else:
            # Update SPS/PPS from FormatDescription if present (keyframe)
            if parsed.has_format_description and parsed.format_description_bytes:
                sps, pps = extract_sps_pps_from_fdsc(parsed.format_description_bytes)
                if sps:
                    self._sps = sps
                    logger.debug("Updated SPS from FEED FormatDescription (%d bytes)", len(sps))
                if pps:
                    self._pps = pps
                    logger.debug("Updated PPS from FEED FormatDescription (%d bytes)", len(pps))

            h264_data = avcc_to_annex_b(parsed.sample_data)

        if h264_data and self._on_video_frame:
            # Detect keyframes by checking for IDR NAL type (5)
            is_keyframe = False
            if len(h264_data) > 4:
                for i in range(min(len(h264_data) - 4, 256)):  # Only scan first 256 bytes
                    if h264_data[i:i+4] == b"\x00\x00\x00\x01":
                        nal_type = h264_data[i+4] & 0x1F if i + 4 < len(h264_data) else 0
                        if nal_type == 5:  # IDR
                            is_keyframe = True
                            break

            # Prepend SPS/PPS to keyframes for decoder robustness
            if is_keyframe and self._sps and self._pps:
                sps_pps = (
                    b"\x00\x00\x00\x01" + self._sps
                    + b"\x00\x00\x00\x01" + self._pps
                )
                if self._sps not in h264_data[:128]:
                    h264_data = sps_pps + h264_data

            # Record stats
            self.stats.record_frame(len(h264_data), is_keyframe)

            frame = VideoFrame(
                data=h264_data,
                timestamp_ns=self._get_current_cmtime_ns(),
                is_keyframe=is_keyframe,
                width=self._video_width,
                height=self._video_height,
            )
            self._on_video_frame(frame)

    def _handle_eat(self, packet: Packet) -> None:
        if self._on_audio_sample:
            pcm_data = extract_pcm_from_eat(packet.payload)
            if pcm_data:
                self.stats.record_audio()
                sample = AudioSample(
                    data=pcm_data,
                    timestamp_ns=self._get_current_cmtime_ns(),
                )
                self._on_audio_sample(sample)

    # ─── Session control ────────────────────────────────────────────

    def build_start_streaming_packets(self) -> list[bytes]:
        packets = []
        # HPD1 now includes display capabilities dict
        packets.append(build_asyn_hpd1(
            clock_ref=b"\x01" + b"\x00" * 7,
            width=1920, height=1080,
        ))
        if self._device_audio_clock_ref != b"\x00" * 8:
            # HPA1 now includes audio configuration dict
            packets.append(build_asyn_hpa1(self._device_audio_clock_ref))
        if self._device_video_clock_ref != b"\x00" * 8:
            packets.append(build_asyn_need(self._device_video_clock_ref))
        return packets

    def build_need_packet(self) -> bytes:
        return build_asyn_need(self._device_video_clock_ref)

    def build_stop_streaming_packets(self) -> list[bytes]:
        packets = []
        if self._device_audio_clock_ref != b"\x00" * 8:
            packets.append(build_asyn_hpa0(self._device_audio_clock_ref))
        packets.append(build_asyn_hpd0())
        return packets

    def get_decoder_extradata(self) -> Optional[bytes]:
        if not self._sps or not self._pps:
            return None
        return (
            b"\x00\x00\x00\x01" + self._sps +
            b"\x00\x00\x00\x01" + self._pps
        )

    def reset(self) -> None:
        """Reset the session for a fresh connection."""
        self._handshake_state = HandshakeState.WAITING_PING
        self._cwpa_received = False
        self._afmt_received = False
        self._cvrp_received = False
        self._device_audio_clock_ref = b"\x00" * 8
        self._device_video_clock_ref = b"\x00" * 8
        self._sps = None
        self._pps = None
        self._clock_counter = 0
        self.stats = SessionStats()
        logger.info("Session reset")
