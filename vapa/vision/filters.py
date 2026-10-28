"""RealSense software and SDK depth filtering pipeline.

Filters:
1. Decimation: Downsamples depth frame (optional).
2. Spatial filter: Edge-preserving smoothing across pixel neighborhoods.
3. Temporal filter: Persistence and temporal smoothing across consecutive frames.
4. Hole filling: Reconstructs missing/occluded depth pixels from neighboring surfaces.
"""

from dataclasses import dataclass
from typing import Optional
import numpy as np

@dataclass
class FilterConfig:
    decimation_magnitude: int = 2
    enable_decimation: bool = False
    spatial_filter: bool = True
    spatial_smooth_alpha: float = 0.5
    spatial_smooth_delta: float = 0.02  # In meters (20 mm)
    temporal_filter: bool = True
    temporal_smooth_alpha: float = 0.4
    temporal_smooth_delta: float = 0.02 # In meters (20 mm)
    hole_filling: int = 1

class SoftwareDepthFilter:
    """Software implementation of edge-preserving spatial, temporal, and hole-filling filters."""

    def __init__(self, cfg: FilterConfig = FilterConfig()):
        self.cfg = cfg
        self._prev_frame: Optional[np.ndarray] = None

    def reset(self) -> None:
        self._prev_frame = None

    def process(self, depth_m: np.ndarray) -> np.ndarray:
        """Apply configured spatial, temporal, and hole-filling filters to depth frame."""
        filtered = depth_m.copy()

        # 1. Optional Decimation
        if self.cfg.enable_decimation and self.cfg.decimation_magnitude > 1:
            mag = self.cfg.decimation_magnitude
            filtered = filtered[::mag, ::mag]

        # 2. Edge-Preserving Spatial Filter
        if self.cfg.spatial_filter:
            filtered = self._apply_spatial_filter(filtered)

        # 3. Temporal Filter with Persistence
        if self.cfg.temporal_filter:
            filtered = self._apply_temporal_filter(filtered)

        # 4. Hole Filling
        if self.cfg.hole_filling > 0:
            filtered = self._apply_hole_filling(filtered)

        return filtered

    def _apply_spatial_filter(self, depth: np.ndarray) -> np.ndarray:
        """Edge-preserving spatial smoothing: smooth with 4-neighborhood only across small depth gradients."""
        h, w = depth.shape
        out = depth.copy()
        alpha = self.cfg.spatial_smooth_alpha
        delta = self.cfg.spatial_smooth_delta

        # Shifted neighbor slices
        up = np.pad(depth[:-1, :], ((1, 0), (0, 0)), mode="edge")
        down = np.pad(depth[1:, :], ((0, 1), (0, 0)), mode="edge")
        left = np.pad(depth[:, :-1], ((0, 0), (1, 0)), mode="edge")
        right = np.pad(depth[:, 1:], ((0, 0), (0, 1)), mode="edge")

        neighbors = [up, down, left, right]
        for n in neighbors:
            mask = (depth > 0) & (n > 0) & (np.abs(depth - n) <= delta)
            out[mask] = alpha * out[mask] + (1.0 - alpha) * n[mask]

        return out

    def _apply_temporal_filter(self, depth: np.ndarray) -> np.ndarray:
        """Temporal exponential moving average with edge delta threshold and persistence."""
        if self._prev_frame is None or self._prev_frame.shape != depth.shape:
            self._prev_frame = depth.copy()
            return depth

        alpha = self.cfg.temporal_smooth_alpha
        delta = self.cfg.temporal_smooth_delta
        out = depth.copy()

        # Case A: Both valid and within delta -> EMA smoothing
        smooth_mask = (depth > 0) & (self._prev_frame > 0) & (np.abs(depth - self._prev_frame) <= delta)
        out[smooth_mask] = alpha * depth[smooth_mask] + (1.0 - alpha) * self._prev_frame[smooth_mask]

        # Case B: Current is missing (0.0), previous was valid -> persistence hold
        persist_mask = (depth == 0) & (self._prev_frame > 0)
        out[persist_mask] = self._prev_frame[persist_mask]

        self._prev_frame = out.copy()
        return out

    def _apply_hole_filling(self, depth: np.ndarray) -> np.ndarray:
        """Fills zero-depth holes from neighboring valid pixels."""
        holes = (depth == 0)
        if not np.any(holes):
            return depth

        out = depth.copy()
        # Find 4-neighborhood max (farthest from around, mode 1)
        up = np.pad(depth[:-1, :], ((1, 0), (0, 0)), mode="edge")
        down = np.pad(depth[1:, :], ((0, 1), (0, 0)), mode="edge")
        left = np.pad(depth[:, :-1], ((0, 0), (1, 0)), mode="edge")
        right = np.pad(depth[:, 1:], ((0, 0), (0, 1)), mode="edge")

        neighbor_max = np.maximum.reduce([up, down, left, right])
        fill_mask = holes & (neighbor_max > 0)
        out[fill_mask] = neighbor_max[fill_mask]
        return out
