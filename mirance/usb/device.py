"""USB QuickTime Mode Activation & Interface Discovery (v2.4)"""
import usb.core
import usb.util
import time
import logging

logger = logging.getLogger(__name__)

def activate_qt_and_get_interface():
    """Finds iPhone, activates QT mode, returns (dev, cfg, intf)."""
    import traceback
    
    logger.info("Searching for iPhone (VendorID: 0x05AC)...")
    dev = usb.core.find(idVendor=0x05AC)
    if not dev:
        logger.error("No iPhone found. Plug it in and tap 'Trust'.")
        raise RuntimeError("No iPhone found. Plug it in and tap 'Trust'.")

    logger.info(f"Found iPhone: {dev.product} (PID: 0x{dev.idProduct:04X})")
    logger.info("Activating QuickTime USB mode...")
    try:
        # v2.4 §A1: Control transfer to enable QT streaming
        result = dev.ctrl_transfer(0x40, 0x52, 0x00, 0x02, b'', timeout=5000)
        logger.debug(f"  → ctrl_transfer result: {result}")
        time.sleep(3)  # Wait for re-enumeration
        logger.debug("  → Performing device reset...")
        dev.reset()
    except usb.core.USBError as e:
        logger.error(f"USB error during QT activation: {e}")
        logger.debug(f"  → Full traceback:\n{traceback.format_exc()}")
        # Continue anyway - device might still work
    except Exception as e:
        logger.error(f"QT activation failed: {e}")
        logger.debug(f"  → Full traceback:\n{traceback.format_exc()}")

    # Re-find device after reset
    logger.debug("  → Re-scanning for device...")
    dev = usb.core.find(idVendor=0x05AC)
    if not dev:
        logger.error("Device disappeared after QT activation. Try again.")
        raise RuntimeError("Device disappeared after QT activation. Try again.")

    logger.info(f"Re-connected: {dev.product} (PID: 0x{dev.idProduct:04X})")

    # v2.4 §A1: Find interface by SubClass 0x2A
    logger.debug("Scanning for QuickTime interface (bInterfaceSubClass: 0x2A)...")
    for cfg in dev:
        for intf in cfg:
            logger.debug(f"  → Interface {intf.bInterfaceNumber}: class=0x{intf.bInterfaceClass:02X}, subclass=0x{intf.bInterfaceSubClass:02X}")
            if intf.bInterfaceClass == 0xFF and intf.bInterfaceSubClass == 0x2A:
                logger.info("✅ QuickTime interface found!")
                return dev, cfg, intf

    logger.error("QuickTime interface not found. Install WinUSB driver (see README).")
    raise RuntimeError("QuickTime interface not found. Install WinUSB driver (see README).")
    
