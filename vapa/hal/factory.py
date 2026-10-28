"""HAL Factory for creating mock or real device backends based on hardware configuration."""

from dataclasses import dataclass
from typing import Dict, Any, Optional
import logging
from .pca9685 import AbstractPCA9685, MockPCA9685, RealPCA9685
from .tca9548a import AbstractTCA9548A, MockTCA9548A, RealTCA9548A
from .as5600 import AbstractAS5600, MockAS5600, RealAS5600
from .esp_link import AbstractESPLink, MockESPLink, RealESPLink
from .realsense import AbstractRealSense, MockRealSense, RealRealSense

logger = logging.getLogger(__name__)

@dataclass
class HALContainer:
    pca9685: AbstractPCA9685
    tca9548a: AbstractTCA9548A
    as5600: AbstractAS5600
    esp_link: AbstractESPLink
    realsense: AbstractRealSense

    def initialize_all(self) -> bool:
        """Initialize all HAL devices. Returns True if all report healthy."""
        ok_pca = self.pca9685.initialize()
        ok_mux = self.tca9548a.initialize()
        ok_enc = self.as5600.initialize()
        ok_esp = self.esp_link.initialize()
        ok_rs = self.realsense.initialize()

        if not (ok_pca and ok_mux and ok_enc and ok_esp and ok_rs):
            logger.error(
                f"HAL init failures: PCA={ok_pca}, MUX={ok_mux}, ENC={ok_enc}, ESP={ok_esp}, RS={ok_rs}"
            )
            return False
        return True

    def close_all(self) -> None:
        """Safely close and release all HAL resources."""
        self.pca9685.disable_all()
        self.pca9685.close()
        self.as5600.close()
        self.tca9548a.close()
        self.esp_link.close()
        self.realsense.close()

def create_hal(hardware_config: Dict[str, Any], force_mock: bool = False) -> HALContainer:
    """Create and return a HALContainer with appropriate backends."""
    jetson_cfg = hardware_config.get("jetson", {})
    backend_mode = "mock" if force_mock else jetson_cfg.get("backend", "mock").lower()

    if backend_mode == "mock":
        logger.info("Initializing HAL with MOCK backends")
        pca = MockPCA9685(
            address=jetson_cfg.get("pca9685", {}).get("address", 0x40),
            frequency_hz=jetson_cfg.get("pca9685", {}).get("frequency_hz", 50),
        )
        mux = MockTCA9548A(
            address=jetson_cfg.get("tca9548a", {}).get("address", 0x71),
        )
        enc = MockAS5600(
            joint_config=jetson_cfg.get("as5600", {}).get("channels"),
        )
        esp = MockESPLink(
            hb_timeout_ms=hardware_config.get("timing", {}).get("heartbeat_timeout_ms", 250),
        )
        rs = MockRealSense()
    elif backend_mode == "real":
        logger.info("Initializing HAL with REAL hardware backends")
        i2c_bus = int(jetson_cfg.get("i2c_bus", 7))
        pca_addr = int(jetson_cfg.get("pca9685", {}).get("address", 0x40))
        freq = int(jetson_cfg.get("pca9685", {}).get("frequency_hz", 50))
        mux_addr = int(jetson_cfg.get("tca9548a", {}).get("address", 0x71))
        as5600_addr = int(jetson_cfg.get("as5600", {}).get("address", 0x36))
        as5600_channels = jetson_cfg.get("as5600", {}).get("channels")
        as5600_retries = int(jetson_cfg.get("as5600", {}).get("max_retries", 3))

        pca = RealPCA9685(bus_num=i2c_bus, address=pca_addr, frequency_hz=freq)
        mux = RealTCA9548A(bus_num=i2c_bus, address=mux_addr)
        enc = RealAS5600(
            mux=mux,
            bus_num=i2c_bus,
            address=as5600_addr,
            joint_config=as5600_channels,
            max_retries=as5600_retries,
        )
        esp = RealESPLink(
            port=jetson_cfg.get("uart_port", "/dev/ttyTHS1"),
            baudrate=jetson_cfg.get("uart_baudrate", 460800),
        )
        rs = RealRealSense()
    else:
        raise ValueError(f"Unknown HAL backend mode: {backend_mode}")

    return HALContainer(
        pca9685=pca,
        tca9548a=mux,
        as5600=enc,
        esp_link=esp,
        realsense=rs,
    )
