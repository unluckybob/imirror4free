"""mirror4free - v2.4 Protocol Configuration (pcap-confirmed)"""

# ─── USB Layer ─────────────────────────────────────────────────────
USB_READ_CHUNK_SIZE = 4096          # Low latency, OSS-confirmed
USB_READ_CONCURRENT = 5             # Concurrent pending reads

# ─── Display Hint (HPD1) ──────────────────────────────────────────
# v2.4: AnyMiro sends 2560×1440 (QHD), NOT 4K.
# Higher values hint to iPhone to encode at higher resolution.
DEFAULT_DISPLAY_WIDTH = 2560.0
DEFAULT_DISPLAY_HEIGHT = 1440.0

# ─── Audio Configuration (HPA1) ───────────────────────────────────
# v2.4: Exact IEEE 754 LE doubles confirmed
AUDIO_BUFFER_AHEAD_INTERVAL = 0.073  # 73ms (e4 a5 9b c4 20 b0 b2 3f)
AUDIO_SCREEN_LATENCY = 0.040         # 40ms (7b 14 ae 47 e1 7a a4 3f)

# ─── Video Buffer Queue (CVRP) ────────────────────────────────────
# v2.4: Maintain 3-5 decoded frames in output queue
VIDEO_QUEUE_HIGH_WATER = 5
VIDEO_QUEUE_LOW_WATER = 3

# ─── Codec Support ────────────────────────────────────────────────
HEVC_SUPPORT = True                  # v2.2/v2.4: FEED contains HEVC regardless of Valeria flag
