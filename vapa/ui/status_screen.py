"""800x480 HDMI Status Display UI for Jetson Orin Nano."""

from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class UIStatusModel:
    safety_state: str = "DISARMED"
    esp_link_healthy: bool = False
    estop_pressed: bool = False
    oe_enabled: bool = False
    active_profile: str = "default"
    nearest_distance_m: float = 0.0
    emg_flex_val: float = 0.0
    emg_ext_val: float = 0.0
    fsr_vals: tuple = (0, 0, 0, 0, 0)
    fault_msg: Optional[str] = None

class StatusScreen:
    """Status screen renderer (supports headless / terminal and pygame renderers)."""

    def __init__(self, width: int = 800, height: int = 480, headless: bool = True):
        self.width = width
        self.height = height
        self.headless = headless
        self.model = UIStatusModel()

    def update(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self.model, k):
                setattr(self.model, k, v)

    def render(self) -> None:
        """Render one frame (or print headless summary)."""
        if self.headless:
            return  # Headless mode operates silently unless queried
