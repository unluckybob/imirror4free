"""v2.4 Handshake & State Machine"""
import time
import struct
import logging
from .packets import (
    Magic, build_rply, build_time_reply, 
    build_afmt_rply, build_asyn_hpd1, build_asyn_hpa1, 
    build_asyn_need, build_asyn_hpd0, build_asyn_hpa0
)

logger = logging.getLogger(__name__)

class ValeriaEngine:
    def __init__(self):
        self.cwpa_dev_ref = self.cvrp_dev_ref = self.clok_dev_ref = self.audio_ref = None
        self.start_ns = time.perf_counter_ns()

    def now_ns(self) -> int: 
        return time.perf_counter_ns() - self.start_ns

    def handle_sync(self, sub: bytes, corr: bytes, payload: bytes) -> bytes | None:
        if sub == Magic.CWPA:
            # CWPA contains device audio clock ref at offset 20
            self.cwpa_dev_ref = struct.unpack_from("<Q", payload, 20)[0]
            self.audio_ref = self.cwpa_dev_ref + 1000
            logger.info("CWPA received → Audio Ref: 0x%X", self.audio_ref)
            return build_rply(corr, self.audio_ref)
            
        elif sub == Magic.CVRP:
            # CVRP contains device video clock ref at offset 20
            self.cvrp_dev_ref = struct.unpack_from("<Q", payload, 20)[0]
            reply_ref = self.cvrp_dev_ref + 0x1000AF
            logger.info("CVRP received → Video Ref: 0x%X", reply_ref)
            return build_rply(corr, reply_ref)
            
        elif sub == Magic.CLOK:
            base = struct.unpack_from("<Q", payload, 20)[0]
            self.clok_dev_ref = base + 0x10000
            return build_rply(corr, self.clok_dev_ref)
            
        elif sub == Magic.TIME:
            return build_time_reply(corr, self.now_ns())
            
        elif sub == Magic.AFMT:
            # AFMT contains connection_id (20:28) and tag (28:32)
            conn = payload[20:28] if len(payload)>=28 else b"\x00"*8
            tag = payload[28:32] if len(payload)>=32 else b"\x00"*4
            logger.info("AFMT received → Sending 62-byte RPLY")
            return build_afmt_rply(conn, tag)
            
        elif sub in (Magic.SKEW, Magic.OG, Magic.STOP):
            return build_rply(corr, 0)
            
        return None

    def handle_asyn(self, sub: bytes, payload: bytes) -> bytes | None:
        if sub == Magic.FEED:
            # Flow control: Send NEED immediately after FEED
            ref = (self.cvrp_dev_ref or 0).to_bytes(8, "little")
            return build_asyn_need(ref)
        return None

    def get_initial_packets(self) -> list[bytes]:
        """Returns packets to send at start of handshake."""
        # v2.4 §A5: HPD1 sent TWICE, then HPA1 after CWPA-RPLY
        hpd1 = build_asyn_hpd1()
        hpa1 = build_asyn_hpa1(b"\x00\x00\x00\x00\x00\x00\x00\x00")  # placeholder clock ref
        return [hpd1, hpd1, hpa1]
