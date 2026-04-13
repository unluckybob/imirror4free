"""Entry Point - iPhone USB Screen Mirroring (v2.4 Compliant)"""
import logging
import usb.core
import usb.util
import time
from imirror.usb.device import activate_qt_and_get_interface
from imirror.usb.valeria import ValeriaEngine
from imirror.usb.stream import StreamManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def main():
    try:
        logger = logging.getLogger(__name__)
        logger.info("🍎 Starting MIRROR4FREE v2.4 USB Mirroring...")

        dev, cfg, intf = activate_qt_and_get_interface()

        logger.info("Claiming USB interface...")
        usb.util.claim_interface(dev, intf.bInterfaceNumber)

        # Find bulk IN endpoint (device → host)
        ep_in = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
        )
        if not ep_in:
            raise RuntimeError("No bulk IN endpoint found. Check USB connection.")
        
        # Find bulk OUT endpoint (host → device)
        ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
        )
        if not ep_out:
            raise RuntimeError("No bulk OUT endpoint found. Check USB connection.")

        logger.info("Initializing protocol engine...")
        engine = ValeriaEngine()
        stream = StreamManager(dev, intf, ep_in, ep_out, engine)
        stream.start()

        logger.info("✅ Stream started! iPhone screen data is being received.")
        logger.info("Press Ctrl+C to stop mirroring safely.")
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logging.info("\n🛑 Shutting down gracefully...")
    except Exception as e:
        logging.error(f"Fatal error: {e}")
    finally:
        if 'stream' in locals(): stream.stop()
        if 'dev' in locals() and 'intf' in locals():
            try: usb.util.release_interface(dev, intf.bInterfaceNumber)
            except: pass

if __name__ == "__main__":
    main()
