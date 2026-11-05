"""TCA9548A I2C multiplexer driver with Mock and Real backends."""

from abc import abstractmethod
from typing import Optional
from .base import BaseDevice

class AbstractTCA9548A(BaseDevice):
    """Abstract interface for TCA9548A I2C switch."""

    @abstractmethod
    def select_channel(self, channel: int) -> None:
        """Enable one channel (0-7) via bitmask."""
        pass

    @abstractmethod
    def deselect(self) -> None:
        """Disable all multiplexer channels (write 0x00)."""
        pass

class MockTCA9548A(AbstractTCA9548A):
    """Mock TCA9548A multiplexer for testing."""

    def __init__(self, address: int = 0x71):
        self.address = address
        self.active_channel: Optional[int] = None
        self._initialized = False

    def initialize(self) -> bool:
        self._initialized = True
        self.deselect()
        return True

    def close(self) -> None:
        self.deselect()
        self._initialized = False

    def is_healthy(self) -> bool:
        return self._initialized

    def select_channel(self, channel: int) -> None:
        if not (0 <= channel < 8):
            raise ValueError(f"TCA9548A channel {channel} out of range (0-7)")
        self.active_channel = channel

    def deselect(self) -> None:
        self.active_channel = None

class RealTCA9548A(AbstractTCA9548A):
    """Real TCA9548A driver using smbus2."""

    def __init__(self, bus_num: int = 7, address: int = 0x71):
        self.bus_num = bus_num
        self.address = address
        self._bus = None
        self._healthy = False

    def initialize(self) -> bool:
        try:
            from smbus2 import SMBus
            self._bus = SMBus(self.bus_num)
            self.deselect()
            self._healthy = True
            return True
        except Exception:
            self._healthy = False
            return False

    def close(self) -> None:
        if self._bus:
            try:
                self.deselect()
                self._bus.close()
            except Exception:
                pass
            self._bus = None
        self._healthy = False
        self._active_channel: Optional[int] = None

    def is_healthy(self) -> bool:
        return self._healthy

    def select_channel(self, channel: int) -> None:
        if not (0 <= channel < 8):
            raise ValueError(f"Channel {channel} out of range (0-7)")
        if self._active_channel == channel:
            return
        if not self._healthy or not self._bus:
            raise RuntimeError("RealTCA9548A is not initialized or healthy")
        try:
            self._bus.write_byte(self.address, 1 << channel)
            self._active_channel = channel
        except Exception:
            # Attempt one bus recovery
            try:
                from smbus2 import SMBus
                self._bus = SMBus(self.bus_num)
                self._bus.write_byte(self.address, 1 << channel)
                self._active_channel = channel
            except Exception as e:
                self._healthy = False
                self._active_channel = None
                raise RuntimeError(f"TCA9548A failed to select channel {channel}: {e}")

    def deselect(self) -> None:
        if self._active_channel is None:
            return
        if self._bus and self._healthy:
            try:
                self._bus.write_byte(self.address, 0x00)
                self._active_channel = None
            except Exception:
                self._healthy = False
                self._active_channel = None
