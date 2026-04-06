"""
Valeria Stream Capture Backend — PHASE 2 COMPLETE.

Uses Apple's Valeria protocol to receive a true H.264 video stream
and PCM audio from the iPhone over USB bulk endpoints. This is the
high-performance backend delivering 30-60 FPS at native resolution
with minimal latency — the same protocol QuickTime Player uses.

Architecture:
    USB Bulk IN → Packet Parser → ValeriaSession → VideoDecoder → CapturedFrame
    USB Bulk OUT ← Response Builder ← ValeriaSession

Streaming lifecycle:
    1. Check driver status (Phase 2: auto-detect WinUSB availability)
    2. Initialize USB endpoints (find iPhone, enable QT config, claim AV interface)
    3. PING handshake
    4. SYNC negotiations (CWPA → audio clock, AFMT → audio format,
       CVRP → video clock + H.264 format, CLOK/TIME/SKEW → clock sync)
    5. Send HPD1 + HPA1 to start video + audio
    6. Continuous loop:
       - Read packets from USB bulk IN
       - Route through ValeriaSession protocol handlers
       - Decode H.264 FEED frames via PyAV (hardware accelerated)
       - Emit CapturedFrame to renderer
       - Feed PCM EAT! samples to AudioPlayer
       - Send NEED packets to keep video flowing
    7. Clean shutdown (HPA0 + HPD0, release endpoints)

Prerequisites:
    - WinUSB mirror driver installed (auto-installed by IMIRROR4FREE)
    - pyusb + libusb-package (bundled in requirements.txt)
"""

import logging
import struct
import threading
import time
from typing import Optional
from collections import deque

import numpy as np

from imirror.capture.base import CaptureBackend, CapturedFrame
from imirror.config import config
from imirror.usb.packets import (
    Magic, PacketType, Packet, VideoFrame, AudioSample,
    read_packet,
)

logger = logging.getLogger(__name__)


# ─── Error codes for GUI integration ───────────────────────────────

class StreamError:
    """Error types for actionable GUI feedback."""
    DRIVER_NEEDED = "driver_needed"
    DRIVER_REPLUG = "driver_replug"
    NO_DEVICE = "no_device"
    QT_CONFIG_FAILED = "qt_config_failed"
    CLAIM_FAILED = "claim_failed"
    CONNECTION_LOST = "connection_lost"
    GENERIC = "generic"


class ValeriaStreamCapture(CaptureBackend):
    """
    High-performance capture backend using the Valeria USB AV protocol.

    Receives H.264 video frames directly from the iPhone over USB
    bulk endpoints, decodes them with hardware-accelerated FFmpeg,
    and delivers RGB pixel buffers to the renderer at 30-60 FPS.

    Falls back gracefully to the Screenshot backend if USB raw access
    is unavailable (e.g., WinUSB driver not installed).
    """

    def __init__(self):
        super().__init__()
        self._thread: Optional[threading.Thread] = None
        self._endpoint = None           # USBEndpoint
        self._session = None            # ValeriaSession
        self._decoder = None            # VideoDecoder
        self._audio = None              # AudioPlayer

        # FPS tracking
        self._frame_times: deque = deque(maxlen=120)

        # Protocol state
        self._handshake_done = threading.Event()
        self._streaming_started = False
        self._hpd1_hpa1_sent = False
        self._cvrp_received = False
        self._init_error: Optional[str] = None
        self._error_type: str = StreamError.GENERIC
        self._pending_need: bool = False

        # External callbacks for recording and lifecycle events
        self._on_raw_h264 = None       # Callable[[bytes, bool, int], None]
        self._on_raw_audio = None      # Callable[[bytes], None]
        self._on_stream_stopped = None # Callable[[], None]

    @property
    def name(self) -> str:
        return "Valeria Stream (H.264)"

    @property
    def max_fps(self) -> int:
        return 60

    @property
    def error_type(self) -> str:
        """The type of the last error (for GUI to show appropriate actions)."""
        return self._error_type

    @property
    def audio_player(self):
        """The AudioPlayer instance (for volume control), or None if not started."""
        return self._audio

    @property
    def video_format(self) -> dict:
        """Current video format info from the session (width, height, has_sps, has_pps)."""
        if self._session:
            return self._session.video_format
        return {}

    def on_raw_h264(self, callback) -> None:
        """Register callback for raw H.264 frames (before decode) — used for recording.
        Signature: callback(h264_data: bytes, is_keyframe: bool, timestamp_ns: int)
        """
        self._on_raw_h264 = callback

    def on_raw_audio(self, callback) -> None:
        """Register callback for raw PCM audio data — used for recording.
        Signature: callback(pcm_data: bytes)
        """
        self._on_raw_audio = callback

    def on_stream_stopped(self, callback) -> None:
        """Register callback fired when the stream thread exits (disconnect/error).
        Signature: callback()
        Called from the stream thread — use Qt signals for UI updates.
        """
        self._on_stream_stopped = callback

    def is_available(self) -> bool:
        """Check if raw USB access is available for Valeria streaming.

        Returns True if:
        - pyusb is installed
        - libusb backend is available
        - An Apple device is found on the USB bus AND accessible
        """
        try:
            from imirror.usb.endpoint import USBEndpoint
            endpoint = USBEndpoint()
            found = endpoint.find_iphone()
            if not found:
                logger.debug("Valeria: No Apple USB device found via pyusb")
                return False

            # Device found — Valeria is potentially available
            if endpoint.has_qt_config():
                logger.info("Valeria: QT AV configuration already active!")
            else:
                logger.info("Valeria: Apple device found — QT config can be enabled")
            return True

        except ImportError:
            logger.debug("Valeria: pyusb not installed")
            return False
        except Exception as e:
            logger.debug("Valeria: Not available — %s", e)
            return False

    def check_driver_ready(self) -> tuple[bool, str, str]:
        """Check if the WinUSB driver is ready for Valeria streaming.

        Returns:
            Tuple of (ready, message, error_type).
        """
        import platform

        if platform.system() != "Windows":
            return True, "Non-Windows platform — no driver needed", StreamError.GENERIC

        try:
            from imirror.usb.driver_installer import check_driver_status
            status = check_driver_status()

            if status.ready_to_stream:
                return True, "Driver ready", StreamError.GENERIC

            if not status.iphone_detected:
                return False, "No iPhone detected on USB", StreamError.NO_DEVICE

            if status.installed and not status.libusb_accessible:
                return (
                    False,
                    "Mirror driver installed but iPhone needs to be reconnected. "
                    "Please unplug and replug your iPhone.",
                    StreamError.DRIVER_REPLUG,
                )

            if not status.libusb_accessible:
                return (
                    False,
                    "Mirror driver not installed. Click 'Install Mirror Driver' "
                    "to enable USB screen mirroring.",
                    StreamError.DRIVER_NEEDED,
                )

        except ImportError:
            logger.debug("driver_installer not available — skipping driver check")

        # If we can't check, try anyway (might work on Linux/macOS)
        return True, "Driver check skipped", StreamError.GENERIC

    def start(self, device_udid: str) -> bool:
        """Start the Valeria stream capture.

        Launches the streaming thread which handles USB initialization,
        protocol handshake, and the main packet loop.

        Args:
            device_udid: iPhone UDID (for logging; USB uses bus-level addressing).

        Returns:
            True if streaming initialization succeeded.
        """
        if self._running:
            return True

        logger.info("Starting Valeria stream for device %s...", device_udid)

        self._running = True
        self._streaming_started = False
        self._handshake_done.clear()
        self._init_error = None
        self._error_type = StreamError.GENERIC

        self._thread = threading.Thread(
            target=self._stream_loop,
            name="valeria-stream",
            daemon=True,
        )
        self._thread.start()

        # Wait for handshake or early failure (up to 20s for QT config + PING)
        self._handshake_done.wait(timeout=20.0)

        if self._init_error:
            logger.error("Valeria start failed: %s", self._init_error)
            self._running = False
            return False

        if not self._running:
            return False

        return True

    def stop(self) -> None:
        """Stop the Valeria stream and clean up resources."""
        if not self._running:
            return

        logger.info("Stopping Valeria stream...")
        self._running = False

        # Send stop streaming commands if we were active
        if self._endpoint and self._endpoint.is_connected and self._session:
            try:
                for pkt in self._session.build_stop_streaming_packets():
                    self._endpoint.write(pkt, timeout=500)
                logger.info("Sent stop streaming commands")
            except Exception:
                pass

        # Wait for thread to finish
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

        self._cleanup()

    # ─── Main streaming loop ────────────────────────────────────────

    def _stream_loop(self) -> None:
        """Main streaming thread — full USB AV communication lifecycle."""
        try:
            # Pre-init audio concurrently with USB setup.
            # The iPhone sends PING immediately after the AV interface is claimed.
            # PortAudio device enumeration takes ~8 s; if we init audio *after*
            # claiming the interface, PING arrives during that window and is lost
            # (nobody reads the bulk-IN endpoint), so the iPhone never gets PONG,
            # stalls the endpoint, and we see [Errno 32] Pipe error ~3 min later.
            # Starting audio on a background thread means it is ready (or nearly
            # ready) by the time we finish the 8-15 s QT-enable + re-enum sequence,
            # so _protocol_loop() starts reading within milliseconds of the claim.
            _audio_ready = threading.Event()

            def _pre_init_audio():
                try:
                    if config.audio_enabled:
                        from imirror.decode.audio import AudioPlayer
                        self._audio = AudioPlayer(
                            sample_rate=config.audio_sample_rate,
                            channels=config.audio_channels,
                            buffer_ms=config.audio_buffer_ms,
                        )
                        self._audio.start()
                        logger.info(
                            "Audio player started: %d Hz, %d ch, %d ms buffer",
                            config.audio_sample_rate, config.audio_channels,
                            config.audio_buffer_ms,
                        )
                    else:
                        logger.info("Audio playback disabled in config")
                except Exception as _ae:
                    logger.warning("Audio pre-init failed: %s", _ae)
                finally:
                    _audio_ready.set()

            _audio_thread = threading.Thread(
                target=_pre_init_audio, daemon=True, name="audio-preinit"
            )
            _audio_thread.start()

            # Phase 1: Initialize USB connection (runs concurrently with audio)
            if not self._init_usb():
                _audio_ready.wait(timeout=15.0)  # let audio thread clean up
                return

            # Phase 2: Create protocol session
            from imirror.usb.valeria import ValeriaSession
            self._session = ValeriaSession()
            self._session.on_video_frame(self._on_video_frame)
            self._session.on_audio_sample(self._on_audio_sample)

            # Phase 3: Initialize video decoder (configured after CVRP handshake)
            from imirror.decode.video import VideoDecoder
            self._decoder = VideoDecoder()

            # Phase 4: Ensure audio is ready before entering the protocol loop.
            # USB setup typically takes 8-15 s so audio is usually done by now;
            # this join is a short (≤5 s) safety wait for slower machines.
            _audio_ready.wait(timeout=5.0)

            # Phase 5: Run the protocol packet loop
            self._protocol_loop()

        except Exception as e:
            logger.exception("Valeria stream loop crashed: %s", e)
            self._signal_error(f"Stream error: {e}")
        finally:
            self._running = False
            self._handshake_done.set()  # Unblock start() if still waiting
            self._cleanup()
            # Notify main_window that stream has ended (for reconnection support)
            if self._on_stream_stopped:
                try:
                    self._on_stream_stopped()
                except Exception:
                    pass

    def _init_usb(self) -> bool:
        """Initialize USB connection and claim AV endpoints.

        Returns True if USB is ready for protocol communication.
        """
        from imirror.usb.endpoint import USBEndpoint

        self._endpoint = USBEndpoint()

        # Step 1: Find iPhone on USB bus
        if not self._endpoint.find_iphone():
            self._signal_error(
                "No iPhone found on USB bus",
                StreamError.NO_DEVICE,
            )
            return False

        logger.info("USB: Found %s", self._endpoint.device_info)

        # Step 2: Enable QT AV configuration
        if not self._endpoint.has_qt_config():
            logger.info("USB: Enabling QT AV configuration...")
            if not self._endpoint.enable_qt_config():
                self._signal_error(
                    "Cannot enable AV mode. The mirror driver may need to be "
                    "installed. Click 'Install Mirror Driver' in the app, or "
                    "install WinUSB via Zadig (https://zadig.akeo.ie/).",
                    StreamError.DRIVER_NEEDED,
                )
                return False

            # Step 3: Wait for device to reconnect with AV endpoints
            if not self._endpoint.wait_for_reenumeration(timeout=30.0):
                self._signal_error(
                    "iPhone didn't reconnect after AV mode enable. "
                    "Try unplugging and replugging your iPhone.",
                    StreamError.DRIVER_REPLUG,
                )
                return False
        else:
            logger.info("USB: QT AV configuration already active")

        # Step 4: Claim the AV bulk endpoints
        _claimed = self._endpoint.claim_av_endpoints()

        if not _claimed and self._endpoint.has_qt_config():
            # QT config is active but claim still failed — this happens after a
            # [Errno 32] Pipe error where WinUSB loses its driver binding even
            # though the iPhone stays in Config 5.  Force a full QT re-enable:
            # resend the control transfer so the iPhone re-enumerates cleanly,
            # which gives WinUSB a completely fresh binding opportunity.
            logger.info(
                "USB: Claim failed with QT config active — forcing full QT "
                "re-enable to recover WinUSB binding..."
            )
            if self._endpoint.enable_qt_config():
                if self._endpoint.wait_for_reenumeration(timeout=30.0):
                    _claimed = self._endpoint.claim_av_endpoints()
                    if _claimed:
                        logger.info("USB: AV endpoints ready after forced re-enable")

        if not _claimed:
            self._signal_error(
                "Cannot claim AV endpoints — another program may be using them, "
                "or the mirror driver needs to be reinstalled.",
                StreamError.CLAIM_FAILED,
            )
            return False

        logger.info("USB: AV endpoints ready for streaming")
        return True

    def _protocol_loop(self) -> None:
        """Run the Valeria protocol communication loop."""
        import usb.core

        read_buffer = bytearray()
        last_need_time = 0.0
        last_data_time = time.monotonic()

        read_size = config.usb_read_size
        read_timeout = config.usb_read_timeout_ms
        need_interval = config.need_packet_interval
        health_timeout = config.usb_health_timeout_s

        logger.info("Valeria protocol loop starting...")

        # ── Wait for iPhone-initiated PING ────────────────────────────
        # Protocol analysis confirms the iPhone sends PING first.
        # The host must wait for the iPhone's PING and respond with its
        # own PING packet. Sending PING first can confuse the iPhone's
        # protocol state machine.
        logger.info("Waiting for iPhone PING to start handshake...")

        while self._running:
            # ── Read from USB ───────────────────────────────────────
            try:
                data = self._endpoint.read(size=read_size, timeout=read_timeout)
                if data:
                    read_buffer.extend(data)
                    last_data_time = time.monotonic()
            except usb.core.USBTimeoutError:
                if self._streaming_started:
                    silence = time.monotonic() - last_data_time
                    if silence > health_timeout:
                        logger.warning("No data from iPhone for %.0fs — connection lost", silence)
                        self._signal_error(
                            "Connection lost — no data from iPhone",
                            StreamError.CONNECTION_LOST,
                        )
                        return
                # NOTE: Do NOT 'continue' here — fall through to parse any
                # previously buffered data and send periodic NEED packets.
                # A timeout only means no NEW data arrived in this read cycle;
                # there may still be complete packets waiting in read_buffer.
            except usb.core.USBError as e:
                if self._running:
                    logger.error("USB read error: %s — attempting recovery", e)
                    # Try to recover from transient USB errors
                    if self._attempt_usb_recovery():
                        read_buffer.clear()
                        last_data_time = time.monotonic()
                        continue
                    self._signal_error(f"USB error: {e}", StreamError.CONNECTION_LOST)
                return

            # ── Parse complete packets ──────────────────────────────
            while len(read_buffer) >= 4:
                pkt_len = struct.unpack_from("<I", read_buffer, 0)[0]

                if pkt_len < 4 or pkt_len > 16 * 1024 * 1024:
                    logger.warning(
                        "Invalid packet length %d at buffer offset — skipping 4 bytes (%d in buffer)",
                        pkt_len, len(read_buffer)
                    )
                    # Skip 4 bytes and try to resync instead of flushing everything
                    del read_buffer[:4]
                    continue

                if len(read_buffer) < pkt_len:
                    break

                pkt_bytes = bytes(read_buffer[:pkt_len])
                del read_buffer[:pkt_len]

                packet = read_packet(pkt_bytes)
                if packet is None:
                    logger.debug("Failed to parse packet (%d bytes)", pkt_len)
                    continue

                response = self._session.handle_packet(packet)

                if response:
                    try:
                        self._endpoint.write(response)
                    except usb.core.USBError as e:
                        logger.error("Failed to send response: %s", e)

                # After receiving a FEED packet, send NEED to request next frame.
                # This creates a pull-based flow: one NEED per FEED received,
                # preventing the host from flooding the iPhone.
                if (self._streaming_started
                        and packet.packet_type == PacketType.ASYN
                        and packet.subtype == Magic.FEED):
                    try:
                        need_pkt = self._session.build_need_packet()
                        self._endpoint.write(need_pkt)
                        last_need_time = time.monotonic()
                        self._pending_need = False
                    except usb.core.USBError:
                        self._pending_need = True  # Retry on next loop

                # ── Track handshake progress ────────────────────────
                if packet.packet_type == PacketType.PING:
                    logger.info("PING handshake complete")
                    self._handshake_done.set()

                elif packet.packet_type == PacketType.SYNC:
                    if packet.subtype == Magic.CWPA:
                        logger.info("CWPA received — audio clock negotiated")
                        # Send HPD1 + HPA1 immediately after CWPA to reduce
                        # startup latency — the iPhone begins preparing
                        # streams while CVRP/CLOK/TIME/SKEW complete.
                        if not self._hpd1_hpa1_sent:
                            self._send_hpd1_hpa1()

                    elif packet.subtype == Magic.AFMT:
                        logger.info("AFMT received — audio format accepted")

                    elif packet.subtype == Magic.CVRP:
                        logger.info("CVRP received — video format negotiated")
                        self._cvrp_received = True

                        if self._decoder and not self._decoder.is_initialized:
                            extradata = self._session.get_decoder_extradata()
                            self._decoder.initialize(
                                codec_name="h264",
                                extradata=extradata,
                            )
                            if extradata:
                                logger.info("Decoder initialized with SPS/PPS extradata (%d bytes)", len(extradata))
                            else:
                                logger.warning("Decoder initialized WITHOUT SPS/PPS — may fail until keyframe")

                        # Protocol flow: NEED is sent after CLOK, not after CVRP.
                        # The iPhone sends CLOK right after CVRP, and only then
                        # expects the NEED request. Defer to CLOK handler below.
                        if not self._hpd1_hpa1_sent:
                            # Fallback if CWPA was missed — send everything now
                            self._start_streaming()

                    elif packet.subtype == Magic.CLOK:
                        logger.info("CLOK received — clock created")
                        # NEED is sent after the first CLOK that follows CVRP
                        # (protocol step 20). This is when the iPhone is fully
                        # ready to deliver video frames.
                        if self._cvrp_received and not self._streaming_started:
                            if self._hpd1_hpa1_sent:
                                self._start_streaming_need_only()
                            else:
                                self._start_streaming()

            # ── Periodic NEED keepalive ─────────────────────────────
            # Primary NEED is sent per-FEED above. This timer is a
            # keepalive: if no FEED arrived for a while, re-request.
            if self._streaming_started:
                now = time.monotonic()
                if now - last_need_time >= need_interval * 4:  # 64ms keepalive
                    try:
                        need_pkt = self._session.build_need_packet()
                        self._endpoint.write(need_pkt)
                        last_need_time = now
                    except usb.core.USBError:
                        pass

    def _send_hpd1_hpa1(self) -> None:
        """Send HPD1 + HPA1 commands early (after CWPA, before CVRP).

        These are sent immediately after the audio clock is negotiated,
        not after the video format is received. This lets the iPhone start
        preparing the AV streams while the remaining handshake completes,
        reducing startup latency.

        Note: The time.sleep(0.01) that existed between packets was removed.
        It added 10-20 ms of unnecessary startup latency — the iPhone handles
        back-to-back bulk OUT packets correctly with no inter-packet delay.
        """
        logger.info("Sending HPD1 + HPA1 (early, after CWPA)...")
        try:
            packets = self._session.build_hpd1_hpa1_packets()
            for pkt in packets:
                self._endpoint.write(pkt)
            self._hpd1_hpa1_sent = True
            logger.info("[STREAM] HPD1 + HPA1 sent — waiting for CVRP to send NEED")
        except Exception as e:
            logger.error("Failed to send HPD1/HPA1: %s", e)

    def _start_streaming_need_only(self) -> None:
        """Send NEED to request the first video frame (HPD1/HPA1 already sent).

        Called after CVRP when HPD1 + HPA1 were already dispatched during
        the CWPA phase.
        """
        if self._streaming_started:
            return

        logger.info("Sending NEED to request first video frame...")
        try:
            need_pkt = self._session.build_need_packet()
            self._endpoint.write(need_pkt)
            self._streaming_started = True
            logger.info("[STREAM] Streaming started — NEED sent, receiving video frames")
        except Exception as e:
            logger.error("Failed to send NEED: %s", e)
            self._signal_error(f"Failed to start streaming: {e}")

    def _start_streaming(self) -> None:
        """Send HPD1 + HPA1 + NEED commands to start streaming (fallback path).

        Used only if HPD1/HPA1 were not sent after CWPA (e.g. if CWPA was missed).
        The preferred flow sends HPD1/HPA1 early via _send_hpd1_hpa1().
        """
        if self._streaming_started:
            return

        logger.info("Sending start streaming commands (HPD1 + HPA1 + NEED)...")

        try:
            packets = self._session.build_start_streaming_packets()
            for pkt in packets:
                self._endpoint.write(pkt)

            self._hpd1_hpa1_sent = True
            self._streaming_started = True
            logger.info("[STREAM] Streaming started — receiving video frames")

        except Exception as e:
            logger.error("Failed to start streaming: %s", e)
            self._signal_error(f"Failed to start streaming: {e}")

    def _attempt_usb_recovery(self) -> bool:
        """Attempt to recover from a USB error by re-claiming endpoints.

        Returns True if recovery succeeded and the stream can continue.

        claim_av_endpoints() now guards set_configuration(5) internally —
        it only calls set_configuration() if has_qt_config() returns False.
        This means calling claim_av_endpoints() here is safe even when QT
        config is already active: it will skip the reset, find the interface,
        and claim it without disrupting the iPhone's Valeria state.
        If claiming fails (e.g. iPhone was unplugged and replugged, losing
        Config 5), we re-enable QT config and wait for re-enumeration.
        """
        logger.info("Attempting USB recovery...")
        try:
            # Release and re-claim endpoints
            if self._endpoint:
                try:
                    self._endpoint.close()
                except Exception:
                    pass

            time.sleep(1.0)  # Brief pause for USB bus to settle

            from imirror.usb.endpoint import USBEndpoint
            self._endpoint = USBEndpoint()

            if not self._endpoint.find_iphone():
                logger.error("USB recovery: iPhone not found")
                return False

            # claim_av_endpoints() calls set_configuration(5) first, so attempt
            # it directly.  If it fails (QT config lost due to device replug),
            # re-enable QT mode and wait for re-enumeration before retrying.
            if not self._endpoint.claim_av_endpoints():
                logger.info(
                    "USB recovery: AV endpoints not claimable "
                    "— re-enabling QT config..."
                )
                if not self._endpoint.enable_qt_config():
                    logger.error("USB recovery: Cannot re-enable QT config")
                    return False
                if not self._endpoint.wait_for_reenumeration(timeout=20.0):
                    logger.error("USB recovery: Re-enumeration timed out")
                    return False
                if not self._endpoint.claim_av_endpoints():
                    logger.error(
                        "USB recovery: Failed to claim endpoints after QT re-enable"
                    )
                    return False

            logger.info("USB recovery successful — resuming stream")
            # Reset session for fresh handshake
            if self._session:
                self._session.reset()
            self._streaming_started = False
            self._hpd1_hpa1_sent = False
            self._cvrp_received = False
            self._handshake_done.clear()
            return True

        except Exception as e:
            logger.error("USB recovery failed: %s", e)
            return False

    # ─── Frame/audio callbacks ──────────────────────────────────────

    def _on_video_frame(self, video_frame: VideoFrame) -> None:
        """Handle a video frame from ValeriaSession — decode and emit."""
        if not self._decoder or not self._running:
            return

        # Fire raw H.264 callback BEFORE decode (for recording — zero re-encode)
        if self._on_raw_h264:
            try:
                self._on_raw_h264(video_frame.data, video_frame.is_keyframe, video_frame.timestamp_ns)
            except Exception:
                pass

        rgb_array = self._decoder.decode_frame(video_frame.data)
        if rgb_array is None:
            return

        height, width = rgb_array.shape[:2]

        now = time.monotonic()
        self._frame_times.append(now)
        if len(self._frame_times) >= 2:
            elapsed = self._frame_times[-1] - self._frame_times[0]
            if elapsed > 0:
                self.fps = (len(self._frame_times) - 1) / elapsed

        # Note: frame_count is incremented by _emit_frame(), not here
        frame = CapturedFrame(
            pixels=rgb_array,
            width=width,
            height=height,
            timestamp=now,
            frame_number=self.frame_count,
        )
        self._emit_frame(frame)

    def _on_audio_sample(self, audio_sample: AudioSample) -> None:
        """Handle an audio sample from ValeriaSession — feed to speaker."""
        if self._audio and self._running:
            self._audio.feed(audio_sample.data)
        # Fire raw audio callback (for recording)
        if self._on_raw_audio and self._running:
            try:
                self._on_raw_audio(audio_sample.data)
            except Exception:
                pass

    # ─── Error handling ─────────────────────────────────────────────

    def _signal_error(self, reason: str, error_type: str = StreamError.GENERIC) -> None:
        """Signal an error to the GUI and set init_error for start() to detect."""
        logger.error("Valeria: %s", reason)
        self._init_error = reason
        self._error_type = error_type
        self._handshake_done.set()
        self._emit_capture_stopped(reason)

    # ─── Cleanup ────────────────────────────────────────────────────

    def _cleanup(self) -> None:
        """Release all resources."""
        if self._endpoint:
            try:
                self._endpoint.close()
            except Exception:
                pass
            self._endpoint = None

        if self._decoder:
            try:
                self._decoder.close()
            except Exception:
                pass
            self._decoder = None

        if self._audio:
            try:
                self._audio.stop()
            except Exception:
                pass
            self._audio = None

        self._session = None
        logger.info("Valeria: Resources cleaned up")
