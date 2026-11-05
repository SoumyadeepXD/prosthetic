"""PCA9685 16-channel 12-bit PWM HAL driver with Mock and Real backends."""

from abc import abstractmethod
from typing import Dict, List, Optional
from .base import BaseDevice

class AbstractPCA9685(BaseDevice):
    """Abstract interface for PCA9685 PWM controller."""

    @abstractmethod
    def set_pulse_us(self, channel: int, pulse_us: float) -> None:
        """Set PWM pulse width in microseconds on specified channel (0-15)."""
        pass

    @abstractmethod
    def disable_channel(self, channel: int) -> None:
        """Disable PWM output on specified channel (0% duty cycle)."""
        pass

    @abstractmethod
    def disable_all(self) -> None:
        """Disable PWM on all 16 channels."""
        pass

class MockPCA9685(AbstractPCA9685):
    """Mock PCA9685 for testing without hardware."""

    def __init__(self, address: int = 0x40, frequency_hz: int = 50):
        self.address = address
        self.frequency_hz = frequency_hz
        self._initialized = False
        self._allcall_disabled = False
        self._channel_pulses: Dict[int, float] = {i: 0.0 for i in range(16)}
        self._pulse_history: List[tuple[int, float]] = []

    def initialize(self) -> bool:
        self._initialized = True
        self._allcall_disabled = True
        self.disable_all()
        return True

    def close(self) -> None:
        self.disable_all()
        self._initialized = False

    def is_healthy(self) -> bool:
        return self._initialized and self._allcall_disabled

    def set_pulse_us(self, channel: int, pulse_us: float) -> None:
        if not (0 <= channel < 16):
            raise ValueError(f"Channel {channel} out of range (0-15)")
        self._channel_pulses[channel] = pulse_us
        self._pulse_history.append((channel, pulse_us))

    def disable_channel(self, channel: int) -> None:
        if not (0 <= channel < 16):
            raise ValueError(f"Channel {channel} out of range (0-15)")
        self._channel_pulses[channel] = 0.0

    def disable_all(self) -> None:
        for ch in range(16):
            self._channel_pulses[ch] = 0.0

    def get_pulse_us(self, channel: int) -> float:
        return self._channel_pulses.get(channel, 0.0)

    @property
    def pulse_history(self) -> List[tuple[int, float]]:
        return self._pulse_history

class RealPCA9685(AbstractPCA9685):
    """Real I2C PCA9685 driver using smbus2 on Linux/Jetson."""

    PCA9685_MODE1 = 0x00
    PCA9685_PRESCALE = 0xFE
    PCA9685_LED0_ON_L = 0x06
    PCA9685_ALL_LED_OFF_H = 0xFD

    def __init__(self, bus_num: int = 7, address: int = 0x40, frequency_hz: int = 50):
        self.bus_num = bus_num
        self.address = address
        self.frequency_hz = frequency_hz
        self._bus = None
        self._healthy = False

    def initialize(self) -> bool:
        try:
            from smbus2 import SMBus
            self._bus = SMBus(self.bus_num)

            # Disable ALLCALL (MODE1 bit 0 = 0) and set normal mode
            mode1 = self._bus.read_byte_data(self.address, self.PCA9685_MODE1)
            mode1 &= ~0x01  # Clear ALLCALL bit
            mode1 &= ~0x10  # Clear SLEEP bit (wake up)
            self._bus.write_byte_data(self.address, self.PCA9685_MODE1, mode1)

            # Set prescale for 50 Hz PWM
            prescale_val = int(round(25000000.0 / (4096.0 * self.frequency_hz)) - 1)
            self._bus.write_byte_data(self.address, self.PCA9685_MODE1, mode1 | 0x10) # sleep to set prescale
            self._bus.write_byte_data(self.address, self.PCA9685_PRESCALE, prescale_val)
            self._bus.write_byte_data(self.address, self.PCA9685_MODE1, mode1) # wake
            
            self.disable_all()
            self._healthy = True
            return True
        except Exception:
            self._healthy = False
            return False

    def close(self) -> None:
        if self._bus:
            try:
                self.disable_all()
                self._bus.close()
            except Exception:
                pass
            self._bus = None
        self._healthy = False

    def is_healthy(self) -> bool:
        return self._healthy

    def set_pulse_us(self, channel: int, pulse_us: float) -> None:
        if not (0 <= channel < 16):
            raise ValueError(f"Channel {channel} out of range (0-15)")
        if not self._healthy or not self._bus:
            raise RuntimeError("PCA9685 is not initialized or healthy")

        # Period at 50 Hz is 20000 us, mapped to 4096 ticks
        ticks = int(round((pulse_us / 20000.0) * 4096.0))
        ticks = max(0, min(4095, ticks))

        reg = self.PCA9685_LED0_ON_L + 4 * channel
        data = [0x00, 0x00, ticks & 0xFF, (ticks >> 8) & 0x0F]
        try:
            self._bus.write_i2c_block_data(self.address, reg, data)
        except Exception:
            try:
                from smbus2 import SMBus
                self._bus = SMBus(self.bus_num)
                self._bus.write_i2c_block_data(self.address, reg, data)
            except Exception as e:
                self._healthy = False
                raise RuntimeError(f"PCA9685 I2C write failed on channel {channel}: {e}")

    def disable_channel(self, channel: int) -> None:
        if not (0 <= channel < 16):
            raise ValueError(f"Channel {channel} out of range (0-15)")
        if self._bus and self._healthy:
            reg = self.PCA9685_LED0_ON_L + 4 * channel
            try:
                self._bus.write_i2c_block_data(self.address, reg, [0x00, 0x00, 0x00, 0x10]) # Full OFF bit
            except Exception:
                self._healthy = False

    def disable_all(self) -> None:
        if self._bus and self._healthy:
            try:
                self._bus.write_byte_data(self.address, self.PCA9685_ALL_LED_OFF_H, 0x10)
            except Exception:
                self._healthy = False
