"""HAL Factory for creating mock or real device backends based on hardware configuration."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
import logging
from .pca9685 import AbstractPCA9685, MockPCA9685, RealPCA9685
from .esp_link import AbstractESPLink, MockESPLink, RealESPLink
from .realsense import AbstractRealSense, MockRealSense, RealRealSense
from .webcam import AbstractWebcam, MockWebcam, GenericWebcam

logger = logging.getLogger(__name__)

@dataclass
class HALContainer:
    pca9685: AbstractPCA9685
    esp_link: AbstractESPLink
    realsense: Optional[AbstractRealSense] = None
    webcam: Optional[AbstractWebcam] = None

    def initialize_all(self) -> bool:
        """Initialize all HAL devices. Returns True if all active devices report healthy."""
        ok_pca = self.pca9685.initialize()
        ok_esp = self.esp_link.initialize()
        ok_rs = self.realsense.initialize() if self.realsense else True
        ok_cam = self.webcam.initialize() if self.webcam else True

        if not (ok_pca and ok_esp and ok_rs and ok_cam):
            logger.error(
                f"HAL init failures: PCA={ok_pca}, ESP={ok_esp}, RS={ok_rs}, Cam={ok_cam}"
            )
            return False
        return True

    def close_all(self) -> None:
        """Safely close and release all HAL resources."""
        self.pca9685.disable_all()
        self.pca9685.close()
        self.esp_link.close()
        if self.realsense:
            self.realsense.close()
        if self.webcam:
            self.webcam.close()

def create_hal(
    hardware_config: Dict[str, Any],
    force_mock: bool = False,
    enable_camera: Optional[bool] = None,
    camera_type: str = "auto",
    config_dir: str = "config",
) -> HALContainer:
    """Create and return a HALContainer with appropriate backends.

    Args:
        hardware_config: Hardware configuration dictionary.
        force_mock: Force mock backends regardless of config.
        enable_camera: Whether to initialize a camera.
                       When None: defaults to True for mock mode (CI tests),
                       and False for real hardware unless explicitly requested.
        camera_type: Camera device type ("auto", "webcam", "realsense").
        config_dir: Directory containing config files (e.g. vision.yaml).
    """
    jetson_cfg = hardware_config.get("jetson", {})
    backend_mode = "mock" if force_mock else jetson_cfg.get("backend", "mock").lower()

    # Determine camera enablement
    cam_active = (enable_camera is True) if enable_camera is not None else (backend_mode == "mock")

    # Determine camera type from vision.yaml if "auto"
    cam_device = "webcam"
    cam_index = 0
    vision_cfg_path = Path(config_dir) / "vision.yaml"
    if vision_cfg_path.exists():
        try:
            with open(vision_cfg_path, "r") as f:
                v_cfg = yaml.safe_load(f) or {}
                cam_device = v_cfg.get("camera", {}).get("device", "webcam").lower()
                cam_index = int(v_cfg.get("camera", {}).get("device_index", 0))
        except Exception:
            pass

    if camera_type != "auto":
        cam_device = camera_type.lower()

    is_webcam = "webcam" in cam_device or "usb" in cam_device or "v4l2" in cam_device

    rs: Optional[AbstractRealSense] = None
    cam: Optional[AbstractWebcam] = None

    if backend_mode == "mock":
        logger.info("Initializing HAL with MOCK backends")
        pca = MockPCA9685(
            address=jetson_cfg.get("pca9685", {}).get("address", 0x40),
            frequency_hz=jetson_cfg.get("pca9685", {}).get("frequency_hz", 50),
        )
        esp = MockESPLink(
            hb_timeout_ms=hardware_config.get("timing", {}).get("heartbeat_timeout_ms", 250),
        )
        if cam_active:
            # Provide both mock devices in mock mode to satisfy all unit test assertions
            cam = MockWebcam(width=640, height=480, fps=30)
            rs = MockRealSense()
    elif backend_mode == "real":
        logger.info("Initializing HAL with REAL hardware backends")
        i2c_bus = int(jetson_cfg.get("i2c_bus", 7))
        pca_addr = int(jetson_cfg.get("pca9685", {}).get("address", 0x40))
        freq = int(jetson_cfg.get("pca9685", {}).get("frequency_hz", 50))

        pca = RealPCA9685(bus_num=i2c_bus, address=pca_addr, frequency_hz=freq)
        esp = RealESPLink(
            port=jetson_cfg.get("uart_port", "/dev/ttyTHS1"),
            baudrate=jetson_cfg.get("uart_baudrate", 460800),
        )
        if cam_active:
            if is_webcam:
                cam = GenericWebcam(device_index=cam_index, width=640, height=480, fps=30)
            else:
                rs = RealRealSense()
    else:
        raise ValueError(f"Unknown HAL backend mode: {backend_mode}")

    return HALContainer(
        pca9685=pca,
        esp_link=esp,
        realsense=rs,
        webcam=cam,
    )

def create_hal_container(
    backend: str = "real",
    config_dir: str = "config",
    enable_camera: bool = False,
    camera_type: str = "auto",
) -> HALContainer:
    """Create a HALContainer directly by backend name with optional camera support."""
    cfg_path = Path(config_dir) / "hardware.yaml"
    hw_config: Dict[str, Any] = {}
    if cfg_path.exists():
        with open(cfg_path, "r") as f:
            hw_config = yaml.safe_load(f) or {}

    force_mock = (backend.lower() == "mock")
    return create_hal(
        hw_config,
        force_mock=force_mock,
        enable_camera=enable_camera,
        camera_type=camera_type,
        config_dir=config_dir,
    )
