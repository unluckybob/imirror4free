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
    1. Check driver status (Phase 2: auto-detect libusb-win32 availability)
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
    - libusb-win32 mirror driver installed (auto-installed by MIRANCE)
    - pyusb + libusb-package (bundled in requirements.txt)
"""

import logging
import struct
import threading
import time
from typing import Optional
from collections import deque

import numpy as np

from mirance.capture.base import CaptureBackend, CapturedFrame
from mirance.config import config
from mirance.usb.packets import (
    Magic, PacketType, Packet, VideoFrame, AudioSample,
    read_packet, build_ping,
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
    is unavailable (e.g., libusb-win32 driver not installed).
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

        # usbmux keepalive session (required for CWPA after PING on Windows)
        self._usbmux = None            # UsbMuxSession

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
            from mirance.usb.endpoint import USBEndpoint
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
        """Check if the libusb-win32 driver is ready for Valeria streaming.
        
        Also attempts automatic driver installation if needed and can_auto_install is True.
        
        Returns:
            Tuple of (ready, message, error_type).
        """
        import platform

        if platform.system() != "Windows":
            return True, "Non-Windows platform — no driver needed", StreamError.GENERIC

        try:
            from mirance.usb.driver_installer import check_driver_status
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

            # Driver not installed - try auto-install
            logger.info("Driver not installed - attempting automatic installation...")
            install_result = self._auto_install_driver()
            if install_result.success:
                return (
                    True,
                    "Driver auto-installed. Please unplug and replug your iPhone, then try again.",
                    StreamError.DRIVER_REPLUG,
                )
            else:
                return (
                    False,
                    f"Mirror driver not installed. {install_result.message}",
                    StreamError.DRIVER_NEEDED,
                )

        except ImportError:
            logger.debug("driver_installer not available — skipping driver check")

        # If we can't check, try anyway (might work on Linux/macOS)
        return True, "Driver check skipped", StreamError.GENERIC

    def _auto_install_driver(self) -> 'DriverInstallResult':
        """Automatically install the libusb-win32 driver.
        
        Returns:
            DriverInstallResult with success status and message.
        """
        try:
            from mirance.usb.driver_installer import (
                check_driver_status, full_driver_setup, DriverInstallResult
            )
            
            # Check if already installed
            status = check_driver_status()
            if status.ready_to_stream:
                return DriverInstallResult(True, "Driver already ready")
            
            # Need iPhone detected to install
            if not status.iphone_detected:
                return DriverInstallResult(False, "No iPhone detected. Connect your iPhone first.")
            
            # Attempt automatic installation
            logger.info("Auto-installing libusb-win32 driver...")
            result = full_driver_setup()
            
            if result.success:
                logger.info("Driver auto-installed successfully")
            else:
                logger.warning(f"Driver auto-install failed: {result.message}")
            
            return result
            
        except Exception as e:
            logger.error(f"Driver auto-install error: {e}")
            return DriverInstallResult(False, f"Installation error: {e}")

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
                        from mirance.decode.audio import AudioPlayer
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
            from mirance.usb.valeria import ValeriaSession
            self._session = ValeriaSession()
            self._session.on_video_frame(self._on_video_frame)
            self._session.on_audio_sample(self._on_audio_sample)

            # Phase 3: Initialize video decoder (configured after CVRP handshake)
            from mirance.decode.video import VideoDecoder
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
        from mirance.usb.endpoint import USBEndpoint

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
                    "install the libusb-win32 mirror driver via 'Install Mirror Driver', or use Zadig (https://zadig.akeo.ie/) and select libusb-win32.",
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

        if not _claimed:
            # Claim failed — force a full QT re-enable regardless of whether
            # has_qt_config() is True or False.
            #
            # Two scenarios reach here:
            #
            # A) QT config active but claim returned Entity-not-found
            #    ([Errno 2]).  This happens after a [Errno 32] Pipe error where
            #    libusb-win32 loses its driver binding even though the iPhone stays in
            #    Config 5.
            #
            # B) "Optimistic" first-ever connection: QT was enabled and the
            #    device reappeared, but wait_for_reenumeration() hit its 15 s
            #    patience limit before has_qt_config() turned True.  Windows
            #    was still installing the libusb-win32 INF for Config 5's interfaces
            #    for the very first time (10–15 s).  claim_av_endpoints() then
            #    calls set_configuration(5) + 3 s wait, but that's not enough —
            #    the AV interface is still not visible.  A second QT enable
            #    after libusb-win32 has now fully bound the INF succeeds quickly.
            #
            # In both cases, resending the QT control transfer gives the iPhone
            # a fresh re-enumeration, and libusb-win32 re-binds cleanly.
            logger.info(
                "USB: Claim failed (QT config %s) — forcing full QT "
                "re-enable to recover libusb-win32 binding...",
                "active" if self._endpoint.has_qt_config() else "not yet visible",
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

        # ── Step 5: Start usbmux keepalive session ────────────────────
        # The iPhone Valeria firmware requires an active usbmuxd session on
        # Interface 0 (the USB multiplexer) before it will send CWPA after
        # the initial PING.  Without this, the PING handshake completes but
        # the iPhone stalls ~19 s later with [Errno 32] Pipe error — it is
        # waiting for a host usbmuxd connection that never arrives.
        #
        # UsbMuxSession claims Interface 0, sends a plist Hello, and drains
        # the IN endpoint in a background thread throughout streaming.
        try:
            from mirance.usb.usbmux import UsbMuxSession
            self._usbmux = UsbMuxSession(self._endpoint._dev)
            if self._usbmux.start():
                logger.info(
                    "USB: usbmux keepalive session started — "
                    "iPhone should now send CWPA after PING"
                )
                # Brief wait for the Hello exchange so the session is
                # established before the protocol loop starts reading.
                self._usbmux.wait_ready(timeout=2.0)
            else:
                logger.warning(
                    "USB: usbmux session could not start — "
                    "CWPA may not arrive after PING (Windows libusb-win32 timing)"
                )
                self._usbmux = None
        except Exception as _ue:
            logger.warning(
                "USB: usbmux session init failed (non-fatal): %s", _ue
            )
            self._usbmux = None

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

        # ── PING handshake ────────────────────────────────────────────
        # v2.4 §A5: iPhone SENDS FIRST PING, host echoes it back
        #   Frame 6644: host → iPhone  PING (10 00 00 00 67 6e 69 70 00 00 00 00 01 00 00 00)
        #   Frame 7003: iPhone → host  PING (echo, ~1 s later)
        #   Frame 7007: host → iPhone  PING (echo of echo via _handle_ping)
        #   Frame 7008: iPhone → host  SYNC(cwpa)  ← streaming begins
        #
        # Wait for iPhone's PING first, then echo it back.
        # The iPhone expects us to echo its PING before it sends CWPA.
        logger.info("Waiting for PING from iPhone...")
        
        # v2.4: Try reading first, but also be ready to send initial PING
        # The iPhone may need a brief moment after usbmux session is ready
        time.sleep(0.3)
        
        # Drain any pending data on IN endpoint
        try:
            drain = self._endpoint.read(size=512, timeout=1500)  # 1.5s to wait for PING
            if drain:
                logger.info(f"Received PING from iPhone ({len(drain)} bytes)")
                read_buffer = bytearray(drain)
                # We got PING - now echo it back
                try:
                    self._endpoint.write(build_ping())
                    logger.info("PING echo sent successfully")
                except Exception as _e:
                    logger.warning("PING echo failed: %s", _e)
        except Exception as _drain:
            read_buffer = bytearray()
            # No PING received - iPhone might be waiting for us to initiate
            # Try sending PING first (as pcap shows host initiates)
            logger.info("No PING from iPhone - sending initial PING...")
            try:
                self._endpoint.write(build_ping())
                logger.info("Initial PING sent successfully")
            except Exception as _e:
                logger.warning("Initial PING send failed: %s", _e)

        _ping_wait_start = time.monotonic()
        _ping_retry_sent = False
        _ping_complete_time: Optional[float] = None   # when PING handshake finished
        _cwpa_timeout = 30.0  # seconds to wait for CWPA after PING

        while self._running:
            # If we haven't received PING yet, wait for it
            # The iPhone sends PING first, we echo it back
            if (not self._streaming_started
                    and not self._handshake_done.is_set()
                    and not read_buffer):
                try:
                    data = self._endpoint.read(size=512, timeout=1000)
                    if data:
                        read_buffer.extend(data)
                        logger.info(f"Received data while waiting for PING ({len(data)} bytes)")
                except:
                    pass  # No data yet, continue
            
            # If we still haven't received PING after 5s, the iPhone might be
            # waiting for us to establish usbmux session first. Retry reading.
            if (not self._streaming_started
                    and not self._handshake_done.is_set()
                    and time.monotonic() - _ping_wait_start > 5.0):
                logger.info("No PING from iPhone after 5s — retrying read...")
                _ping_wait_start = time.monotonic()
            # ── CWPA watchdog ────────────────────────────────────────
            # If PING completed but iPhone sent no CWPA within 30 s, resend PING
            # to restart the handshake.  This handles the case where the first PING
            # was received but the CWPA window was missed (e.g. libusb0 discard).
            if (not self._streaming_started
                    and _ping_complete_time is not None
                    and time.monotonic() - _ping_complete_time > _cwpa_timeout):
                logger.warning(
                    "No CWPA from iPhone after %.0fs since PING — resending PING",
                    time.monotonic() - _ping_complete_time,
                )
                _ping_complete_time = None
                _ping_retry_sent = False
                _ping_wait_start = time.monotonic()
                try:
                    self._endpoint.write(build_ping())
                    logger.info("PING resent (CWPA watchdog)")
                except Exception as _we:
                    logger.warning("CWPA watchdog PING resend failed: %s", _we)

            # ── Read from USB ───────────────────────────────────────
            try:
                # During handshake (before streaming starts) use a small read
                # buffer so the iPhone's short PING packet (16 bytes) immediately
                # terminates the libusb-win32 bulk transfer.  Large URBs (1 MB) may
                # silently discard short-packet completions on some libusb-win32 builds,
                # which causes PING to be lost and the handshake to never start.
                # Once streaming is confirmed we switch to the full buffer size
                # for high-throughput video reads.
                # During handshake (before PING), use 4096-byte reads AND a long
                # timeout (5000ms) so the pending libusb-win32 URB stays open long enough
                # to capture the iPhone's 16-byte PING packet.
                #
                # With a 100ms timeout: if PING arrives as the timeout fires,
                # libusb-win32 cancels the pending read and DISCARDS the received bytes.
                # This is a ~50/50 race since iPhone sends PING ~100ms after claim.
                # With 5000ms: PING arrives well within the window every time.
                # (If PING doesn't arrive in 5s we treat it as a timeout and retry.)
                #
                # During streaming we go back to 100ms for responsive health checks.
                if not self._streaming_started:
                    _hs_read_size = 4096
                    # Pre-PING: 5 s window to catch the 16-byte PING response.
                    # Post-PING (waiting for CWPA): 15 s so CWPA is not discarded
                    # at the timeout boundary by libusb0-win32.
                    _hs_timeout = 5000 if not self._handshake_done.is_set() else 15000
                else:
                    _hs_read_size = read_size
                    _hs_timeout = read_timeout
                data = self._endpoint.read(size=_hs_read_size, timeout=_hs_timeout)
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
                    # libusb0-win32 raises USBError (not USBTimeoutError) for
                    # bulk read timeouts.  Detect by inspecting the error string
                    # so we don't trigger recovery on every normal 5/15-second
                    # handshake timeout — doing so corrupts the libusb0 handle
                    # and causes the "invalid interface -1" cascade seen in logs.
                    if 'timeout' in str(e).lower():
                        # Treat identically to USBTimeoutError — non-fatal.
                        if self._streaming_started:
                            silence = time.monotonic() - last_data_time
                            if silence > health_timeout:
                                logger.warning(
                                    "No data from iPhone for %.0fs — connection lost",
                                    silence,
                                )
                                self._signal_error(
                                    "Connection lost — no data from iPhone",
                                    StreamError.CONNECTION_LOST,
                                )
                                return
                        # During handshake: fall through to packet parse / CWPA watchdog
                    else:
                        logger.error("USB read error: %s — attempting recovery", e)
                        # Try to recover from transient USB errors
                        if self._attempt_usb_recovery():
                            read_buffer.clear()
                            last_data_time = time.monotonic()
                            # Reset PING state so we restart the handshake cleanly
                            _ping_retry_sent = False
                            _ping_complete_time = None
                            _ping_wait_start = time.monotonic()
                            try:
                                self._endpoint.write(build_ping())
                                logger.info("Resent PING after USB recovery")
                            except Exception as _rpe:
                                logger.warning("PING resend after recovery failed: %s", _rpe)
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
                    _ping_complete_time = time.monotonic()  # start CWPA watchdog

                elif packet.packet_type == PacketType.SYNC:
                    if packet.subtype == Magic.CWPA:
                        logger.info("CWPA received — audio clock negotiated")
                        # HPD1 + RPLY(cwpa) + HPD1 + HPA1 are returned directly
                        # from valeria._handle_cwpa() and written above.
                        # No separate send needed here.

                    elif packet.subtype == Magic.AFMT:
                        logger.info("AFMT received — audio format accepted")

                    elif packet.subtype == Magic.CVRP:
                        logger.info("CVRP received — video format negotiated")
                        self._cvrp_received = True

                        if self._decoder and not self._decoder.is_initialized:
                            extradata = self._session.get_decoder_extradata()
                            # v2.4 §D2: iPhone ALWAYS sends HEVC, never H.264
                            # CVRP avcC is legacy declaration - real stream is HEVC
                            codec_name = "hevc"
                            self._decoder.initialize(
                                codec_name=codec_name,
                                extradata=extradata,
                            )
                            if extradata:
                                logger.info("Decoder initialized with %s SPS/PPS extradata (%d bytes)", codec_name, len(extradata))
                            else:
                                logger.warning("Decoder initialized WITHOUT SPS/PPS — may fail until keyframe")

                        # NEED + RPLY(cvrp) already sent by valeria._handle_cvrp().
                        # Mark streaming started now.
                        if not self._streaming_started:
                            self._streaming_started = True
                            self._hpd1_hpa1_sent = True
                            logger.info("[STREAM] Streaming started — NEED sent with CVRP response")

                    elif packet.subtype == Magic.CLOK:
                        logger.info("CLOK received — clock created")
                        # NEED was already sent with CVRP. Nothing to do here.

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

            from mirance.usb.endpoint import USBEndpoint
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

        # Update session video dimensions from first decoded frame.
        # ValeriaSession doesn't parse SPS for width/height, so we
        # backfill from the actual decoded frame. This is needed for
        # recording (set_video_format) and the video_format property.
        if self._session and (width > 0) and (height > 0):
            if self._session._video_width == 0:
                self._session._video_width = width
                self._session._video_height = height
                logger.info("Video dimensions detected from decode: %dx%d", width, height)

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
        if self._usbmux:
            try:
                self._usbmux.stop()
            except Exception:
                pass
            self._usbmux = None

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
