"""imirror4free - v2.4 Protocol Configuration (pcap-confirmed)"""
USB_READ_CHUNK = 4096          # Low latency bulk read size
USB_CONCURRENT = 5             # Concurrent pending reads

# HPD1 Display Hint (AnyMiro uses 2560x1440, not 4K)
DISPLAY_WIDTH  = 2560.0
DISPLAY_HEIGHT = 1440.0

# HPA1 Audio Config (IEEE 754 LE doubles from pcap)
AUDIO_BUFFER_MS = 0.073        # 73ms BufferAheadInterval
SCREEN_LATENCY  = 0.040        # 40ms ScreenLatency

# CVRP Queue Levels (maintain 3-5 decoded frames)
QUEUE_HIGH_WATER = 5
QUEUE_LOW_WATER  = 3

HEVC_ENABLED = True            # iPhone streams HEVC regardless of Valeria flag
