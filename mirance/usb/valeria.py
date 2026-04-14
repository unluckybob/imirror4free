"""v2.4 Handshake & State Machine"""
import time
import struct
import logging
from .packets import (
    build_rply, build_skew_reply, build_time_reply,
    build_rply, build_time_reply, 
    build_afmt_rply, build_asyn_hpd1, build_asyn_hpa1, 
    build_asyn_need, build_asyn_hpd0, build_asyn_hpa0,
    Magic
)

logger = logging.getLogger(__name__)

class ValeriaEngine:
    def __init__(self):
        self.cwpa_dev_ref = self.cvrp_dev_ref = self.clok_dev_ref = self.audio_ref = None
        self._rels_received = 0
        self._pending_packets = []
        # v2.4 §A9: SKEW tracking
        self._skew_start_local = None
        self._skew_start_device = None
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
            # v2.4 §A10: Use corr (correlationID) and sub (sub-type) directly
            # These are already extracted from SYNC header by caller
            logger.info("AFMT received → Sending 62-byte RPLY")
            return build_afmt_rply(connection_id=corr, tag=sub)
            
        elif sub == Magic.SKEW:
            # v2.4 §A9: SKEW uses float64 drift ratio, not integer
            return build_skew_reply(corr, self._calculate_skew())
        elif sub in (Magic.OG, Magic.STOP):
            return build_rply(corr, 0)
            
        return None

    def handle_asyn(self, sub: bytes, payload: bytes) -> bytes | None:
        # v2.4 §A5: TEARDOWN - handle RELS (release confirmations)
        if sub == Magic.RELS:
            self._rels_received += 1
            logger.info(f"RELS received ({self._rels_received}/2)")
            # After 2 RELS, send final HPD0
            if self._rels_received >= 2:
                logger.info("Both RELS received - sending final HPD0")
                return build_asyn_hpd0()
            return None
        
        if sub == Magic.FEED:
            # v2.4 §A4.5: Flow control - only send NEED after CVRP received
            if self.cvrp_dev_ref is None:
                logger.warning("FEED received but CVRP not yet received - skipping NEED")
                return None
            ref = self.cvrp_dev_ref.to_bytes(8, "little")
            return build_asyn_need(ref)
        
        # v2.4 §A3: Catch-all for unknown ASYN sub-types (SPRP, TJMP, SRAT, TBAS)
        # These are rare/conditional and don't block normal streaming
        logger.debug(f"Unknown ASYN sub-type: {sub.hex()}")
        return None
    
    def start_teardown(self) -> list[bytes]:
        """Start teardown sequence per v2.4 §A5.
        
        Send HPA0 + HPD0, then wait for 2× RELS.
        """
        self._rels_received = 0
        logger.info("Starting teardown sequence...")
        
        # Send HPA0 then HPD0
        hpa0 = build_asyn_hpa0(struct.pack("<Q", self.audio_ref or 0))
        hpd0 = build_asyn_hpd0()
        return [hpa0, hpd0]

    def get_initial_packets(self) -> list[bytes]:
        """Returns packets AFTER PING+CWPA handshake per v2.4 §A5.
        
        Sequence: PING → CWPA → THEN send HPD1×2 + HPA1
        """
        return []  # Handshake packets sent after CWPA via queue_hpd1_hpa1()
    def queue_hpd1_hpa1(self, audio_clock_ref: int):
        """Queue HPD1 (×2) + HPA1 to send after CWPA-RPLY per v2.4 §A5.
        
        audio_clock_ref: the CWPA DeviceClockRef from the iPhone
        """
        self._pending_packets = []
        
        # HPD1 sent twice (v2.4 §A5 confirmed)
        hpd1 = build_asyn_hpd1()
        self._pending_packets.extend([hpd1, hpd1])
        
        # HPA1 with asynTypeHeader = CWPA DeviceClockRef (§A7)
        hpa1 = build_asyn_hpa1(struct.pack("<Q", audio_clock_ref))
        self._pending_packets.append(hpa1)
        
        logger.info(f"Queued {len(self._pending_packets)} handshake packets (2×HPD1 + HPA1)")
    
    def get_pending_packets(self) -> list[bytes]:
        """Return and clear any pending handshake packets."""
        packets = getattr(self, '_pending_packets', [])
        self._pending_packets = []
        return packets
