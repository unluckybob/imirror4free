"""USB Bulk Read Loop & Packet Dispatch (v2.4)"""
import threading
import struct
import logging
import usb.util
from .packets import Magic, build_ping
from .valeria import ValeriaEngine

logger = logging.getLogger(__name__)

class StreamManager:
    def __init__(self, dev, intf, ep_in, ep_out, engine: ValeriaEngine):
        self.dev = dev
        self.intf = intf
        self.ep_in = ep_in
        self.ep_out = ep_out
        self.engine = engine
        self.running = False
        self.buffer = b""

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=3)

    def _write_packet(self, pkt: bytes):
        """Sends packet with 4-byte LE length prefix."""
        self.ep_out.write(struct.pack("<I", len(pkt)) + pkt)

    def _read_loop(self):
        try:
            logger.info("📡 USB read loop started (waiting for PING from device)...")
            while self.running:
                chunk = self.ep_in.read(4096, timeout=2000)
                if not chunk:
                    continue
                self.buffer += bytes(chunk)
                self._process_buffer()
        except usb.core.USBError as e:
            logger.error(f"USB error: {e}")
        except Exception as e:
            logger.error(f"Stream loop crash: {e}")
        finally:
            try: usb.util.release_interface(self.dev, self.intf.bInterfaceNumber)
            except: pass

    def _process_buffer(self):
        """Parses complete frames and dispatches to protocol engine."""
        while len(self.buffer) >= 4:
            total = struct.unpack_from("<I", self.buffer, 0)[0]
            # v2.4 §A2: length includes the 4-byte header
            if total < 16 or total > len(self.buffer):
                break

            frame = self.buffer[:total]
            self.buffer = self.buffer[total:]
            payload = frame[4:]

            magic = payload[:4]
            if magic == Magic.PING:
                self._write_packet(build_ping())
            elif magic == Magic.SYNC:
                sub = payload[16:20]
                corr = payload[8:16]
                reply = self.engine.handle_sync(sub, corr, payload)
                if reply:
                    self._write_packet(reply)
                    
                    # v2.4 §A5: After CWPA-RPLY, queue HPD1×2 + HPA1
                    if sub == Magic.CWPA:
                        audio_ref = self.engine.audio_ref
                        self.engine.queue_hpd1_hpa1(audio_ref)
                    
                    # Send any pending handshake packets
                    for pkt in self.engine.get_pending_packets():
                        self._write_packet(pkt)
            elif magic == Magic.ASYN:
                sub = payload[16:20]
                reply = self.engine.handle_asyn(sub, payload[20:])
                if reply: self._write_packet(reply)
