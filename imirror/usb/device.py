"""USB QuickTime Mode Activation & Interface Discovery (v2.4)"""
import usb.core
import usb.util
import time
import logging

logger = logging.getLogger(__name__)

def activate_qt_and_get_interface():
    """Finds iPhone, activates QT mode, returns (dev, cfg, intf)."""
    logger.info("Searching for iPhone (VendorID: 0x05AC)...")
    dev = usb.core.find(idVendor=0x05AC)
    if not dev:
        raise RuntimeError("No iPhone found. Plug it in and tap 'Trust'.")

    logger.info("Activating QuickTime USB mode...")
    try:
        # v2.4 §A1: Control transfer to enable QT streaming
        dev.ctrl_transfer(0x40, 0x52, 0x00, 0x02, b'', timeout=5000)
        time.sleep(3)  # Wait for re-enumeration
        dev.reset()
    except Exception as e:
        logger.warning(f"QT activation step failed: {e}")

    # Re-find device after reset
    dev = usb.core.find(idVendor=0x05AC)
    if not dev:
        raise RuntimeError("Device disappeared after QT activation. Try again.")

    # v2.4 §A1: Find interface by SubClass 0x2A
    for cfg in dev:
        for intf in cfg:
            if intf.bInterfaceClass == 0xFF and intf.bInterfaceSubClass == 0x2A:
                logger.info("✅ QuickTime interface found!")
                return dev, cfg, intf

    raise RuntimeError("QuickTime interface not found. Install WinUSB driver (see README).")
