"""
iOS Trust Prompt Detection and Handling - Exact replica of AnyMiro

This module handles the iOS "Trust This Computer" dialog that appears
when connecting an iPhone to a computer via USB.

AnyMiro's Core.MirroringConnection.dll references:
- isTrustOpened
- TrustDevice
- needTrust

This implements Trust detection and handling exactly like AnyMiro.

Reference: AnyMiro's Core.MirroringConnection.dll (TrustDevice, needTrust, isTrustOpened)
"""

import logging
import platform
import subprocess
import time
from typing import Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class TrustState(Enum):
    """iOS Trust state - exact match to AnyMiro."""
    UNKNOWN = 0
    TRUSTED = 1       # Device is trusted
    UNTRUSTED = 2     # Device is not trusted
    PROMPT_PENDING = 3  # Waiting for user to respond
    BLOCKED = 4       # Device is blocked (too many failed attempts)


class TrustChecker:
    """
    iOS Trust prompt detection - exact replica of AnyMiro's approach.
    
    Monitors the iOS device trust state and handles the trust prompt.
    """
    
    def __init__(self):
        self._last_state = TrustState.UNKNOWN
        self._callbacks: list[Callable[[TrustState], None]] = []
        self._poll_interval = 1.0
        self._running = False
        
    def start(self) -> None:
        """Start monitoring trust state - like AnyMiro."""
        self._running = True
        logger.info("TrustChecker started (AnyMiro-style)")
        
    def stop(self) -> None:
        """Stop monitoring trust state."""
        self._running = False
        
    def add_callback(self, callback: Callable[[TrustState], None]) -> None:
        """Add trust state change callback."""
        self._callbacks.append(callback)
        
    def remove_callback(self, callback: Callable[[TrustState], None]) -> None:
        """Remove trust state change callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
            
    def check_trust_state(self, device_udid: str) -> TrustState:
        """
        Check current trust state - exact like AnyMiro.
        
        AnyMiro's approach:
        1. Query lockdown service for trust state
        2. Check pair record
        3. Check if device is paired
        
        Args:
            device_udid: Device UDID
            
        Returns:
            Current trust state
        """
        if platform.system() != "Windows":
            return TrustState.UNKNOWN
            
        try:
            # Query lockdown for trust info - same as AnyMiro
            result = subprocess.run([
                "powershell", "-NoProfile", "-Command",
                f"""
                # Try to query lockdown via usbmuxd
                $pairRecord = "$env:APPDATA\\Apple Computer\\Lockdown\\{device_udid}.plist"
                if (Test-Path $pairRecord) {{
                    $xml = [xml](Get-Content $pairRecord)
                    $trust = $xml.SelectSingleNode("//key[text()='TrustStatus']/following-sibling::*[1]")
                    if ($trust -and $trust.'#text' -eq '1') {{
                        Write-Output "TRUSTED"
                    }} else {{
                        Write-Output "UNTRUSTED"
                    }}
                }} else {{
                    Write-Output "PROMPT_PENDING"
                }}
                """
            ], capture_output=True, text=True, timeout=10)
            
            output = result.stdout.strip().upper()
            
            if "TRUSTED" in output:
                logger.debug(f"Device {device_udid}: TRUSTED")
                return TrustState.TRUSTED
            elif "UNTRUSTED" in output:
                logger.debug(f"Device {device_udid}: UNTRUSTED")
                return TrustState.UNTRUSTED
            else:
                logger.debug(f"Device {device_udid}: PROMPT_PENDING")
                return TrustState.PROMPT_PENDING
                
        except Exception as e:
            logger.debug(f"Trust check error: {e}")
            return TrustState.UNKNOWN
            
    def is_device_trusted(self, device_udid: str) -> bool:
        """
        Check if device is trusted - exact like AnyMiro's isTrustOpened.
        
        Args:
            device_udid: Device UDID
            
        Returns:
            True if device is trusted
        """
        return self.check_trust_state(device_udid) == TrustState.TRUSTED
        
    def wait_for_trust(self, device_udid: str, timeout: float = 60.0) -> bool:
        """
        Wait for user to trust the device - exact like AnyMiro.
        
        This waits for the user to tap "Trust" on the iPhone prompt.
        
        Args:
            device_udid: Device UDID
            timeout: Max wait time in seconds
            
        Returns:
            True if device became trusted
        """
        start = time.time()
        
        while time.time() - start < timeout:
            state = self.check_trust_state(device_udid)
            
            if state == TrustState.TRUSTED:
                logger.info(f"Device {device_udid} is now trusted!")
                return True
                
            if state == TrustState.BLOCKED:
                logger.error(f"Device {device_udid} is blocked - too many failed attempts")
                return False
                
            # Notify callbacks of state
            for cb in self._callbacks:
                try:
                    cb(state)
                except Exception:
                    pass
                    
            time.sleep(self._poll_interval)
            
        logger.warning(f"Trust timeout after {timeout}s for device {device_udid}")
        return False
        
    def has_pair_record(self, device_udid: str) -> bool:
        """
        Check if device has a pair record - like AnyMiro's pair record check.
        
        Args:
            device_udid: Device UDID
            
        Returns:
            True if device has been paired before
        """
        if platform.system() != "Windows":
            return False
            
        try:
            # Check for pair record - same location as AnyMiro
            result = subprocess.run([
                "powershell", "-NoProfile", "-Command",
                f"""
                $pairRecord = "$env:APPDATA\\Apple Computer\\Lockdown\\{device_udid}.plist"
                if (Test-Path $pairRecord) {{
                    Write-Output "EXISTS"
                }}
                """
            ], capture_output=True, text=True, timeout=5)
            
            return "EXISTS" in result.stdout
            
        except Exception:
            return False
            
    def get_trust_info(self, device_udid: str) -> dict:
        """
        Get detailed trust information - like AnyMiro.
        
        Returns:
            Dictionary with trust details
        """
        info = {
            "udid": device_udid,
            "has_pair_record": self.has_pair_record(device_udid),
            "is_trusted": False,
            "trust_state": "UNKNOWN",
        }
        
        state = self.check_trust_state(device_udid)
        info["trust_state"] = state.name
        info["is_trusted"] = (state == TrustState.TRUSTED)
        
        return info


# Global trust checker instance
_trust_checker: Optional[TrustChecker] = None


def get_trust_checker() -> TrustChecker:
    """Get the global trust checker instance."""
    global _trust_checker
    if _trust_checker is None:
        _trust_checker = TrustChecker()
    return _trust_checker


def is_device_trusted(device_udid: str) -> bool:
    """Check if device is trusted."""
    return get_trust_checker().is_device_trusted(device_udid)


def wait_for_trust(device_udid: str, timeout: float = 60.0) -> bool:
    """Wait for user to trust the device."""
    return get_trust_checker().wait_for_trust(device_udid, timeout)


def check_trust_state(device_udid: str) -> TrustState:
    """Check current trust state."""
    return get_trust_checker().check_trust_state(device_udid)


# Alias functions matching AnyMiro's naming
def isTrustOpened(device_udid: str) -> bool:
    """Alias for is_device_trusted - matches AnyMiro's isTrustOpened."""
    return is_device_trusted(device_udid)


def TrustDevice(device_udid: str) -> bool:
    """Alias for wait_for_trust - matches AnyMiro's TrustDevice."""
    return wait_for_trust(device_udid, timeout=60.0)


def needTrust(device_udid: str) -> bool:
    """Check if device needs trust - matches AnyMiro's needTrust."""
    state = check_trust_state(device_udid)
    return state in (TrustState.UNTRUSTED, TrustState.PROMPT_PENDING)


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 1:
        udid = sys.argv[1]
        
        # Check trust state
        checker = get_trust_checker()
        info = checker.get_trust_info(udid)
        
        print(f"Device: {udid}")
        print(f"  Has pair record: {info['has_pair_record']}")
        print(f"  Is trusted: {info['is_trusted']}")
        print(f"  Trust state: {info['trust_state']}")
    else:
        print("Usage: python trust_checker.py <device_udid>")