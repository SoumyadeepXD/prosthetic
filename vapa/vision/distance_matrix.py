"""3D distance matrix calculation and obstacle feature extraction."""

from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np

@dataclass
class DistanceMatrixResult:
    grid_depth_m: np.ndarray       # (H, W) float32
    grid_valid: np.ndarray         # (H, W) bool
    nearest_distance_m: float
    centroid_3d_m: Optional[Tuple[float, float, float]]
    approach_velocity_mps: float
    reach_confidence: float

class DistanceMatrixProcessor:
    """Processes full-resolution depth frames into an H x W median depth grid and proximity metrics."""

    def __init__(
        self,
        grid_rows: int = 12,
        grid_cols: int = 16,
        z_min_m: float = 0.10,
        z_max_m: float = 0.80,
    ):
        self.grid_rows = grid_rows
        self.grid_cols = grid_cols
        self.z_min_m = z_min_m
        self.z_max_m = z_max_m
        self._prev_nearest_m: Optional[float] = None
        self._prev_time: Optional[float] = None

    def process(self, depth_meters: np.ndarray, timestamp: float) -> DistanceMatrixResult:
        h, w = depth_meters.shape
        cell_h = h // self.grid_rows
        cell_w = w // self.grid_cols

        grid_depth = np.zeros((self.grid_rows, self.grid_cols), dtype=np.float32)
        grid_valid = np.zeros((self.grid_rows, self.grid_cols), dtype=bool)

        for r in range(self.grid_rows):
            for c in range(self.grid_cols):
                cell = depth_meters[r * cell_h : (r + 1) * cell_h, c * cell_w : (c + 1) * cell_w]
                valid_mask = (cell >= self.z_min_m) & (cell <= self.z_max_m)
                if np.any(valid_mask):
                    med = float(np.median(cell[valid_mask]))
                    grid_depth[r, c] = med
                    grid_valid[r, c] = True
                else:
                    grid_depth[r, c] = 0.0
                    grid_valid[r, c] = False

        valid_depths = grid_depth[grid_valid]
        if len(valid_depths) > 0:
            nearest_m = float(np.min(valid_depths))
            valid_count = int(np.sum(grid_valid))
            reach_confidence = min(1.0, valid_count / (self.grid_rows * self.grid_cols * 0.2))

            # Estimate centroid
            r_indices, c_indices = np.where(grid_valid)
            mean_r = float(np.mean(r_indices))
            mean_c = float(np.mean(c_indices))
            centroid = (mean_c / self.grid_cols, mean_r / self.grid_rows, float(np.mean(valid_depths)))
        else:
            nearest_m = 999.0
            reach_confidence = 0.0
            centroid = None

        # Approach velocity calculation
        velocity = 0.0
        if self._prev_nearest_m is not None and self._prev_time is not None:
            dt = timestamp - self._prev_time
            if dt > 1e-4:
                # Positive velocity = approaching hand
                velocity = (self._prev_nearest_m - nearest_m) / dt

        self._prev_nearest_m = nearest_m
        self._prev_time = timestamp

        return DistanceMatrixResult(
            grid_depth_m=grid_depth,
            grid_valid=grid_valid,
            nearest_distance_m=nearest_m,
            centroid_3d_m=centroid,
            approach_velocity_mps=velocity,
            reach_confidence=reach_confidence,
        )
