"""Intel RealSense D435i camera driver with Mock and Real backends."""

import time
import numpy as np
from abc import abstractmethod
from typing import Tuple, Optional, Dict, Any
from .base import BaseDevice

class AbstractRealSense(BaseDevice):
    """Abstract interface for RealSense D435i aligned depth and color capture."""

    @abstractmethod
    def capture_frame(self) -> Tuple[np.ndarray, np.ndarray, float]:
        """Capture aligned RGB and Depth frames.

        Returns:
            Tuple of:
            - color: np.ndarray (H, W, 3) uint8
            - depth_meters: np.ndarray (H, W) float32 (values in meters, 0.0 = invalid)
            - timestamp: float (seconds)
        """
        pass

class MockRealSense(AbstractRealSense):
    """Mock RealSense camera generating synthetic depth and color scenes."""

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        target_distance_m: float = 0.35,
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.target_distance_m = target_distance_m
        self._initialized = False
        self._sim_time = 0.0

    def initialize(self) -> bool:
        self._initialized = True
        return True

    def close(self) -> None:
        self._initialized = False

    def is_healthy(self) -> bool:
        return self._initialized

    def set_target_distance(self, distance_m: float) -> None:
        self.target_distance_m = distance_m

    def capture_frame(self) -> Tuple[np.ndarray, np.ndarray, float]:
        if not self._initialized:
            raise RuntimeError("MockRealSense not initialized")

        t = time.time() if self._sim_time == 0.0 else self._sim_time
        # Synthetic RGB image
        color = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        color[:, :] = [40, 40, 40]

        # Synthetic depth image in meters
        # Background at 2.0 meters
        depth = np.full((self.height, self.width), 2.0, dtype=np.float32)

        # Place a target in center at self.target_distance_m
        cy, cx = self.height // 2, self.width // 2
        r = 75
        depth[cy - r : cy + r, cx - r : cx + r] = self.target_distance_m
        color[cy - r : cy + r, cx - r : cx + r] = [0, 200, 200]

        return color, depth, t

class RealRealSense(AbstractRealSense):
    """Real D435i capture using pyrealsense2 with aligned color/depth and hardware filters."""

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        filter_config: Optional[Dict[str, Any]] = None,
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.filter_config = filter_config or {}
        self._pipeline = None
        self._align = None
        self._filters = []
        self._healthy = False

    def initialize(self) -> bool:
        try:
            import pyrealsense2 as rs
            self._pipeline = rs.pipeline()
            config = rs.config()
            config.enable_stream(rs.stream.depth, self.width, self.height, rs.format.z16, self.fps)
            config.enable_stream(rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps)

            profile = self._pipeline.start(config)
            self._align = rs.align(rs.stream.color)

            # Initialize hardware/SDK post-processing filters
            self._filters = []

            # 1. Decimation filter
            dec_mag = self.filter_config.get("decimation_magnitude", 2)
            if self.filter_config.get("enable_decimation", False) and dec_mag > 1:
                dec = rs.decimation_filter()
                dec.set_option(rs.option.filter_magnitude, dec_mag)
                self._filters.append(dec)

            # 2. Spatial filter (edge-preserving)
            if self.filter_config.get("spatial_filter", True):
                spat = rs.spatial_filter()
                spat.set_option(rs.option.filter_smooth_alpha, self.filter_config.get("spatial_smooth_alpha", 0.5))
                spat.set_option(rs.option.filter_smooth_delta, self.filter_config.get("spatial_smooth_delta", 20))
                self._filters.append(spat)

            # 3. Temporal filter (persistence)
            if self.filter_config.get("temporal_filter", True):
                temp = rs.temporal_filter()
                temp.set_option(rs.option.filter_smooth_alpha, self.filter_config.get("temporal_smooth_alpha", 0.4))
                temp.set_option(rs.option.filter_smooth_delta, self.filter_config.get("temporal_smooth_delta", 20))
                self._filters.append(temp)

            # 4. Hole filling filter
            hole_mode = self.filter_config.get("hole_filling", 1)
            if hole_mode > 0:
                hole = rs.hole_filling_filter(hole_mode)
                self._filters.append(hole)

            self._healthy = True
            return True
        except Exception:
            self._healthy = False
            return False

    def close(self) -> None:
        if self._pipeline:
            try:
                self._pipeline.stop()
            except Exception:
                pass
            self._pipeline = None
        self._healthy = False

    def is_healthy(self) -> bool:
        return self._healthy

    def capture_frame(self) -> Tuple[np.ndarray, np.ndarray, float]:
        if not self._healthy or not self._pipeline:
            raise RuntimeError("RealSense pipeline not active")

        frames = self._pipeline.wait_for_frames(timeout_ms=1000)
        aligned_frames = self._align.process(frames)
        depth_frame = aligned_frames.get_depth_frame()
        color_frame = aligned_frames.get_color_frame()

        if not depth_frame or not color_frame:
            raise RuntimeError("Failed to acquire aligned frames")

        # Apply post-processing filter chain
        for f in self._filters:
            depth_frame = f.process(depth_frame)

        depth_raw = np.asanyarray(depth_frame.get_data())
        color_image = np.asanyarray(color_frame.get_data())
        # Convert depth uint16 (mm) to float32 (meters)
        depth_meters = depth_raw.astype(np.float32) * 0.001
        t = time.time()
        return color_image, depth_meters, t
