"""v2.4 Handshake & State Machine"""
import time, struct, logging
from .packets import Magic, build_rply_28, build_time_reply, build_afmt_rply, build_need

logger = logging.getLogger(__name__)

class ValeriaEngine:
    def __init__(self):
        self.cwpa_dev_ref = self.cvrp_dev_ref = self.clok_dev_ref = self.audio_ref = None
        self.start_ns = time.perf_counter_ns()

    def now_ns(self) -> int: return time.perf_counter_ns() - self.start_ns

    def handle_sync(self, sub: bytes, corr: bytes, payload: bytes) -> bytes | None:
        if sub == Magic.CWPA:
            self.cwpa_dev_ref = struct.unpack_from("<Q", payload, 20)[0]
            self.audio_ref = self.cwpa_dev_ref + 1000
            logger.info("CWPA → Audio Ref: 0x%X", self.audio_ref)
            return build_rply_28(corr, self.audio_ref)
        elif sub == Magic.CVRP:
            self.cvrp_dev_ref = struct.unpack_from("<Q", payload, 20)[0]
            reply_ref = self.cvrp_dev_ref + 0x1000AF
            logger.info("CVRP → Video Ref: 0x%X", reply_ref)
            return build_rply_28(corr, reply_ref)
        elif sub == Magic.CLOK:
            base = struct.unpack_from("<Q", payload, 20)[0]
            self.clok_dev_ref = base + 0x10000
            return build_rply_28(corr, self.clok_dev_ref)
        elif sub == Magic.TIME:
            return build_time_reply(corr, self.now_ns())
        elif sub == Magic.AFMT:
            conn = payload[20:28] if len(payload)>=28 else b"\x00"*8
            tag = payload[28:32] if len(payload)>=32 else b"\x00"*4
            return build_afmt_rply(conn, tag)
        elif sub in (Magic.SKEW, Magic.OG, Magic.STOP):
            return build_rply_28(corr, 0)
        return None

    def handle_asyn(self, sub: bytes, corr: bytes, payload: bytes) -> bytes | None:
        if sub == Magic.FEED:
            ref = (self.cvrp_dev_ref or 0).to_bytes(8, "little")
            return build_need(ref)
        return None
