"""800x480 HDMI Status Display UI for Jetson Orin Nano with Headless Fallback."""

import os
import sys
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
import numpy as np
import logging

logger = logging.getLogger("vapa.ui")

@dataclass
class UIStatusModel:
    safety_state: str = "DISARMED"
    active_profile: str = "default"
    heartbeat_ok: bool = False
    estop_pressed: bool = False
    oe_enabled: bool = False
    fault_reason: Optional[str] = None

    # Vision
    nearest_distance_mm: float = 0.0
    reach_confidence: float = 0.0
    approach_velocity_mm_s: float = 0.0
    grid_depth_m: Optional[np.ndarray] = None
    grid_valid: Optional[np.ndarray] = None
    target_class: Optional[str] = None
    target_confidence: float = 0.0
    bounding_box: Optional[Tuple[float, float, float, float]] = None

    # EMG & FSR
    emg_flex_norm: float = 0.0
    emg_ext_norm: float = 0.0
    emg_flex_mv: float = 0.0
    emg_ext_mv: float = 0.0
    emg_intent: str = "HOLD"
    fsr_forces: Tuple[float, float, float, float, float] = (0.0, 0.0, 0.0, 0.0, 0.0)

    # Performance Metrics
    loop_rate_hz: float = 100.0
    loop_jitter_ms: float = 0.0
    max_cycle_ms: float = 0.0
    crc_errors: int = 0
    ads_errors: int = 0
    drops: int = 0

class StatusScreen:
    """800x480 UI Status Screen renderer with graphical pygame and terminal headless fallbacks."""

    def __init__(self, width: int = 800, height: int = 480, headless: Optional[bool] = None):
        self.width = width
        self.height = height
        self.model = UIStatusModel()

        # Detect headless environment if not explicitly set
        if headless is None:
            self.headless = not bool(os.environ.get("DISPLAY"))
        else:
            self.headless = headless

        self._pygame_surface = None
        self._font_small = None
        self._font_med = None
        self._font_large = None
        self._last_render_time = 0.0

        if not self.headless:
            self._init_pygame()

    def _init_pygame(self) -> None:
        try:
            import pygame
            pygame.init()
            pygame.display.set_caption("VAPA - 800x480 Status Display")
            self._pygame_surface = pygame.display.set_mode((self.width, self.height))
            self._font_small = pygame.font.SysFont("monospace", 14)
            self._font_med = pygame.font.SysFont("monospace", 18, bold=True)
            self._font_large = pygame.font.SysFont("monospace", 24, bold=True)
            self.headless = False
            logger.info("Initialized Pygame 800x480 HDMI display.")
        except Exception as e:
            logger.info(f"Graphical display unavailable ({e}). Operating in headless mode.")
            self.headless = True
            self._pygame_surface = None

    def update(self, **kwargs) -> None:
        """Update fields in UIStatusModel."""
        for k, v in kwargs.items():
            if hasattr(self.model, k):
                setattr(self.model, k, v)

    def format_ascii_dashboard(self) -> str:
        """Render a formatted ASCII representation of the 800x480 dashboard."""
        m = self.model
        # Left Panel Strings
        hb_str = "OK (50 Hz)" if m.heartbeat_ok else "LOST"
        estop_str = "PRESSED (FAULT)" if m.estop_pressed else "RELEASED (OK)"
        oe_str = "LOW (ENABLED)" if m.oe_enabled else "HIGH (DISABLED)"
        fault_str = m.fault_reason[:20] if m.fault_reason else "NONE"

        # Right Panel Strings
        f_bar = "=" * int(m.emg_flex_norm * 10)
        e_bar = "=" * int(m.emg_ext_norm * 10)
        f_pct = int(m.emg_flex_norm * 100)
        e_pct = int(m.emg_ext_norm * 100)

        # Center Matrix ASCII
        matrix_lines = []
        if m.grid_depth_m is not None and m.grid_valid is not None:
            for r in range(min(6, m.grid_depth_m.shape[0])):
                row_chars = []
                for c in range(min(16, m.grid_depth_m.shape[1])):
                    if m.grid_valid[r, c]:
                        val = m.grid_depth_m[r, c]
                        row_chars.append("#" if val < 0.35 else ("+" if val < 0.55 else "."))
                    else:
                        row_chars.append(" ")
                matrix_lines.append("".join(row_chars))
        else:
            matrix_lines = ["(Distance matrix initializing...)"]

        while len(matrix_lines) < 6:
            matrix_lines.append("")

        lines = [
            "+" + "-" * 78 + "+",
            f"| VAPA 800x480 STATUS DASHBOARD | State: {m.safety_state:<12} | Mode: {m.active_profile:<12} |",
            "+" + "-" * 20 + "+" + "-" * 32 + "+" + "-" * 24 + "+",
            f"| STATE: {m.safety_state:<11} | 12x16 MATRIX: {m.nearest_distance_mm:5.1f}mm | FLEX: [{f_bar:<10}] {f_pct:3d}% |",
            f"| PROFILE: {m.active_profile:<9} | {matrix_lines[0]:<30} | EXT:  [{e_bar:<10}] {e_pct:3d}% |",
            f"| HEARTBEAT: {hb_str:<7} | {matrix_lines[1]:<30} | INTENT: {m.emg_intent:<14} |",
            f"| ESTOP: {estop_str:<11} | {matrix_lines[2]:<30} | FSR THUMB: {m.fsr_forces[0]:5.0f}g     |",
            f"| OE: {oe_str:<14} | {matrix_lines[3]:<30} | FSR INDEX: {m.fsr_forces[1]:5.0f}g     |",
            f"| FAULT: {fault_str:<11} | Target: {str(m.target_class):<10} ({m.target_confidence:3.2f}) | FSR MID:   {m.fsr_forces[2]:5.0f}g     |",
            "+" + "-" * 20 + "+" + "-" * 32 + "+" + "-" * 24 + "+",
            f"| Rate: {m.loop_rate_hz:5.1f} Hz | Jitter: {m.loop_jitter_ms:4.2f} ms | Max: {m.max_cycle_ms:4.2f} ms | CRC Err: {m.crc_errors:2d} | ADS Err: {m.ads_errors:2d} |",
            "+" + "-" * 78 + "+",
        ]
        return "\n".join(lines)

    def render(self) -> None:
        """Render frame to HDMI display or log terminal dashboard."""
        now = time.time()
        # Cap GUI rendering to 30 fps
        if (now - self._last_render_time) < 0.033:
            return
        self._last_render_time = now

        if self.headless:
            return

        import pygame
        surface = self._pygame_surface
        surface.fill((20, 24, 30))  # Dark background

        # Draw 4 Panels:
        # Left Panel (x: 10, y: 10, w: 220, h: 410)
        pygame.draw.rect(surface, (35, 40, 50), (10, 10, 220, 410), border_radius=6)
        # Center Panel (x: 240, y: 10, w: 320, h: 410)
        pygame.draw.rect(surface, (35, 40, 50), (240, 10, 320, 410), border_radius=6)
        # Right Panel (x: 570, y: 10, w: 220, h: 410)
        pygame.draw.rect(surface, (35, 40, 50), (570, 10, 220, 410), border_radius=6)
        # Bottom Bar (x: 10, y: 430, w: 780, h: 40)
        pygame.draw.rect(surface, (28, 32, 40), (10, 430, 780, 40), border_radius=6)

        # 1. Left Panel Text
        state_color = (0, 220, 100) if self.model.safety_state in ("ARMED_IDLE", "ACTIVE") else (220, 50, 50)
        lbl_state = self._font_large.render(self.model.safety_state, True, state_color)
        surface.blit(lbl_state, (20, 20))

        lbl_prof = self._font_med.render(f"Profile: {self.model.active_profile}", True, (240, 240, 240))
        surface.blit(lbl_prof, (20, 60))

        hb_color = (0, 220, 100) if self.model.heartbeat_ok else (220, 50, 50)
        lbl_hb = self._font_small.render("Heartbeat: " + ("OK (50 Hz)" if self.model.heartbeat_ok else "LOST"), True, hb_color)
        surface.blit(lbl_hb, (20, 95))

        estop_color = (220, 50, 50) if self.model.estop_pressed else (0, 220, 100)
        lbl_estop = self._font_small.render("E-Stop: " + ("PRESSED" if self.model.estop_pressed else "RELEASED"), True, estop_color)
        surface.blit(lbl_estop, (20, 120))

        oe_color = (0, 220, 100) if self.model.oe_enabled else (200, 200, 200)
        lbl_oe = self._font_small.render("OE: " + ("ENABLED (LOW)" if self.model.oe_enabled else "DISABLED (HIGH)"), True, oe_color)
        surface.blit(lbl_oe, (20, 145))

        if self.model.fault_reason:
            lbl_fault = self._font_small.render(f"Fault: {self.model.fault_reason[:25]}", True, (255, 80, 80))
            surface.blit(lbl_fault, (20, 180))

        # 2. Center Panel: Distance Matrix Visualization (12x16 grid)
        lbl_dm = self._font_med.render(f"Distance: {self.model.nearest_distance_mm:.0f} mm", True, (240, 240, 240))
        surface.blit(lbl_dm, (250, 20))

        if self.model.grid_depth_m is not None and self.model.grid_valid is not None:
            cell_w, cell_h = 18, 22
            grid_x, grid_y = 250, 60
            for r in range(12):
                for c in range(16):
                    rect = (grid_x + c * (cell_w + 1), grid_y + r * (cell_h + 1), cell_w, cell_h)
                    if self.model.grid_valid[r, c]:
                        d = self.model.grid_depth_m[r, c]
                        # Color: closer = red/yellow, farther = green/blue
                        if d < 0.30:
                            col = (220, 50, 50)
                        elif d < 0.50:
                            col = (220, 180, 40)
                        else:
                            col = (50, 120, 220)
                    else:
                        col = (45, 50, 60)
                    pygame.draw.rect(surface, col, rect)

        # 3. Right Panel: EMG & FSR Gauges
        lbl_emg = self._font_med.render("EMG & Force Telemetry", True, (240, 240, 240))
        surface.blit(lbl_emg, (580, 20))

        # Flexor bar
        pygame.draw.rect(surface, (50, 55, 65), (580, 60, 200, 20))
        pygame.draw.rect(surface, (0, 180, 220), (580, 60, int(200 * self.model.emg_flex_norm), 20))
        lbl_flex = self._font_small.render(f"Flex: {int(self.model.emg_flex_norm * 100)}%", True, (255, 255, 255))
        surface.blit(lbl_flex, (585, 62))

        # Extensor bar
        pygame.draw.rect(surface, (50, 55, 65), (580, 90, 200, 20))
        pygame.draw.rect(surface, (0, 220, 120), (580, 90, int(200 * self.model.emg_ext_norm), 20))
        lbl_ext = self._font_small.render(f"Ext:  {int(self.model.emg_ext_norm * 100)}%", True, (255, 255, 255))
        surface.blit(lbl_ext, (585, 92))

        # FSR Finger bars
        finger_names = ["Thumb", "Index", "Mid", "Ring", "Little"]
        for idx, name in enumerate(finger_names):
            y_pos = 135 + idx * 30
            val = self.model.fsr_forces[idx] if idx < len(self.model.fsr_forces) else 0.0
            frac = min(1.0, val / 400.0)
            pygame.draw.rect(surface, (50, 55, 65), (580, y_pos, 200, 18))
            bar_color = (220, 60, 60) if val >= 300.0 else (180, 120, 40)
            pygame.draw.rect(surface, bar_color, (580, y_pos, int(200 * frac), 18))
            lbl_f = self._font_small.render(f"{name}: {val:.0f}g", True, (240, 240, 240))
            surface.blit(lbl_f, (585, y_pos + 1))

        # 4. Bottom Metrics Bar
        metrics_text = (
            f"Rate: {self.model.loop_rate_hz:5.1f} Hz  |  "
            f"Jitter: {self.model.loop_jitter_ms:4.2f} ms  |  "
            f"Max Cycle: {self.model.max_cycle_ms:4.2f} ms  |  "
            f"CRC Err: {self.model.crc_errors}  |  "
            f"ADS Err: {self.model.ads_errors}"
        )
        lbl_m = self._font_small.render(metrics_text, True, (200, 205, 215))
        surface.blit(lbl_m, (20, 442))

        pygame.display.flip()
