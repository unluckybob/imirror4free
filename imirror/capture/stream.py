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
        self._init_error: Optional[str] = None
        self._error_type: str = StreamError.GENERIC

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
            # Phase 1: Initialize USB connection
            if not self._init_usb():
                return

            # Phase 2: Create protocol session
            from imirror.usb.valeria import ValeriaSession
            self._session = ValeriaSession()
            self._session.on_video_frame(self._on_video_frame)
            self._session.on_audio_sample(self._on_audio_sample)

            # Phase 3: Initialize video decoder (configured after CVRP handshake)
            from imirror.decode.video import VideoDecoder
            self._decoder = VideoDecoder()

            # Phase 4: Initialize audio player
            from imirror.decode.audio import AudioPlayer
            self._audio = AudioPlayer()
            self._audio.start()

            # Phase 5: Run the protocol packet loop
            self._protocol_loop()

        except Exception as e:
            logger.exception("Valeria stream loop crashed: %s", e)
            self._signal_error(f"Stream error: {e}")
        finally:
            self._running = False
            self._handshake_done.set()  # Unblock start() if still waiting
            self._cleanup()

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
            if not self._endpoint.wait_for_reenumeration(timeout=15.0):
                self._signal_error(
                    "iPhone didn't reconnect after AV mode enable. "
                    "Try unplugging and replugging your iPhone.",
                    StreamError.DRIVER_REPLUG,
                )
                return False
        else:
            logger.info("USB: QT AV configuration already active")

        # Step 4: Claim the AV bulk endpoints
        if not self._endpoint.claim_av_endpoints():
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
                continue
            except usb.core.USBError as e:
                if self._running:
                    logger.error("USB read error: %s", e)
                    self._signal_error(f"USB error: {e}")
                return

            # ── Parse complete packets ──────────────────────────────
            while len(read_buffer) >= 4:
                pkt_len = struct.unpack_from("<I", read_buffer, 0)[0]

                if pkt_len < 4 or pkt_len > 16 * 1024 * 1024:
                    logger.warning(
                        "Invalid packet length %d — flushing buffer (%d bytes)",
                        pkt_len, len(read_buffer)
                    )
                    read_buffer.clear()
                    break

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

                # After receiving a FEED packet, immediately send NEED
                if (self._streaming_started
                        and packet.packet_type == PacketType.ASYN
                        and packet.subtype == Magic.FEED):
                    try:
                        need_pkt = self._session.build_need_packet()
                        self._endpoint.write(need_pkt)
                        last_need_time = time.monotonic()
                    except usb.core.USBError:
                        pass

                # ── Track handshake progress ────────────────────────
                if packet.packet_type == PacketType.PING:
                    logger.info("PING handshake complete")
                    self._handshake_done.set()

                elif packet.packet_type == PacketType.SYNC:
                    if packet.subtype == Magic.CVRP:
                        logger.info("CVRP received — video format negotiated")

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

                        if not self._streaming_started:
                            self._start_streaming()

                    elif packet.subtype == Magic.CWPA:
                        logger.info("CWPA received — audio clock negotiated")

                    elif packet.subtype == Magic.AFMT:
                        logger.info("AFMT received — audio format accepted")

            # ── Send NEED packets to keep video flowing ─────────────
            if self._streaming_started:
                now = time.monotonic()
                if now - last_need_time >= need_interval:
                    try:
                        need_pkt = self._session.build_need_packet()
                        self._endpoint.write(need_pkt)
                        last_need_time = now
                    except usb.core.USBError:
                        pass

    def _start_streaming(self) -> None:
        """Send HPD1 + HPA1 commands to start video and audio streaming."""
        if self._streaming_started:
            return

        logger.info("Sending start streaming commands (HPD1 + HPA1)...")

        try:
            packets = self._session.build_start_streaming_packets()
            for pkt in packets:
                self._endpoint.write(pkt)
                time.sleep(0.01)

            self._streaming_started = True
            logger.info("🎬 Streaming started — receiving video frames")

        except Exception as e:
            logger.error("Failed to start streaming: %s", e)
            self._signal_error(f"Failed to start streaming: {e}")

    # ─── Frame/audio callbacks ──────────────────────────────────────

    def _on_video_frame(self, video_frame: VideoFrame) -> None:
        """Handle a video frame from ValeriaSession — decode and emit."""
        if not self._decoder or not self._running:
            return

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
