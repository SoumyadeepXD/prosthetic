"""3D distance matrix calculation, central-zone target tracking, approach velocity, and reach confidence."""

from dataclasses import dataclass
from typing import Optional, Tuple, Deque, List
from collections import deque
import numpy as np

@dataclass
class DistanceMatrixResult:
    grid_depth_m: np.ndarray             # (H, W) float32 in meters
    grid_valid: np.ndarray               # (H, W) bool
    nearest_distance_m: float            # Nearest distance in meters
    centroid_3d_m: Optional[Tuple[float, float, float]] = None
    approach_velocity_mps: float = 0.0   # in m/s (positive = approaching hand, backwards compat)
    reach_confidence: float = 0.0        # [0.0..1.0]
    grid_depth_mm: Optional[np.ndarray] = None # (H, W) float32 in millimeters
    nearest_distance_mm: float = 0.0     # Nearest distance in mm
    nearest_cell: Optional[Tuple[int, int]] = None # (row, col) of tracked nearest target cell
    approach_velocity_mm_s: float = 0.0  # in mm/s (negative = closing in, per Master Prompt spec)

    def __post_init__(self):
        if self.grid_depth_mm is None and self.grid_depth_m is not None:
            self.grid_depth_mm = self.grid_depth_m * 1000.0
        if self.nearest_distance_mm == 0.0 and self.nearest_distance_m != 0.0:
            self.nearest_distance_mm = self.nearest_distance_m * 1000.0
        if self.approach_velocity_mm_s == 0.0 and self.approach_velocity_mps != 0.0:
            self.approach_velocity_mm_s = -self.approach_velocity_mps * 1000.0

class DistanceMatrixProcessor:
    """Processes full-resolution depth frames into an H x W median depth grid and target proximity metrics.

    Grid:
        Rows: 12 (vertical)
        Cols: 16 (horizontal)

    Central Zone:
        Rows: 2 to 9 (inclusive)
        Cols: 3 to 12 (inclusive)
    """

    def __init__(
        self,
        grid_rows: int = 12,
        grid_cols: int = 16,
        z_min_m: float = 0.10,
        z_max_m: float = 0.80,
        central_row_range: Tuple[int, int] = (2, 9),
        central_col_range: Tuple[int, int] = (3, 12),
        velocity_window_size: int = 5,
    ):
        self.grid_rows = grid_rows
        self.grid_cols = grid_cols
        self.z_min_m = z_min_m
        self.z_max_m = z_max_m
        self.central_row_range = central_row_range
        self.central_col_range = central_col_range
        self.velocity_window_size = velocity_window_size

        # Sliding window for 5-frame velocity differentiation: deque of (timestamp, distance_mm)
        self._history: Deque[Tuple[float, float]] = deque(maxlen=velocity_window_size)
        self._prev_nearest_m: Optional[float] = None
        self._prev_time: Optional[float] = None

    def reset(self) -> None:
        """Reset historical tracking buffers."""
        self._history.clear()
        self._prev_nearest_m = None
        self._prev_time = None

    def process(self, depth_meters: np.ndarray, timestamp: float) -> DistanceMatrixResult:
        """Process aligned depth frame into distance matrix and target metrics.

        Args:
            depth_meters: 2D numpy array of float32 depth values in meters.
            timestamp: Frame acquisition timestamp in seconds.

        Returns:
            DistanceMatrixResult containing grid and tracking features.
        """
        h, w = depth_meters.shape
        cell_h = h // self.grid_rows
        cell_w = w // self.grid_cols

        grid_depth_m = np.zeros((self.grid_rows, self.grid_cols), dtype=np.float32)
        grid_valid = np.zeros((self.grid_rows, self.grid_cols), dtype=bool)
        cell_valid_pixel_counts = np.zeros((self.grid_rows, self.grid_cols), dtype=np.int32)

        # 1. Compute median depth per grid cell (rejecting zeros and out-of-range pixels)
        for r in range(self.grid_rows):
            for c in range(self.grid_cols):
                cell = depth_meters[r * cell_h : (r + 1) * cell_h, c * cell_w : (c + 1) * cell_w]
                valid_mask = (cell >= self.z_min_m) & (cell <= self.z_max_m)
                count = int(np.count_nonzero(valid_mask))
                cell_valid_pixel_counts[r, c] = count

                if count > 0:
                    med = float(np.median(cell[valid_mask]))
                    grid_depth_m[r, c] = med
                    grid_valid[r, c] = True
                else:
                    grid_depth_m[r, c] = 0.0
                    grid_valid[r, c] = False

        grid_depth_mm = grid_depth_m * 1000.0

        # 2. Target Tracking: Prioritize nearest valid cell in the Central Zone
        r_start, r_end = self.central_row_range
        c_start, c_end = self.central_col_range

        central_mask = np.zeros_like(grid_valid)
        central_mask[r_start : r_end + 1, c_start : c_end + 1] = True
        central_valid_mask = grid_valid & central_mask

        nearest_m = 999.0
        nearest_cell: Optional[Tuple[int, int]] = None

        if np.any(central_valid_mask):
            # Extract candidate depths in central zone
            indices = np.argwhere(central_valid_mask)
            min_val = 999.0
            best_idx = None
            for idx in indices:
                r, c = idx[0], idx[1]
                val = grid_depth_m[r, c]
                if val < min_val:
                    min_val = val
                    best_idx = (r, c)
            nearest_m = min_val
            nearest_cell = best_idx
        elif np.any(grid_valid):
            # Fallback to whole grid if central zone is empty
            indices = np.argwhere(grid_valid)
            min_val = 999.0
            best_idx = None
            for idx in indices:
                r, c = idx[0], idx[1]
                val = grid_depth_m[r, c]
                if val < min_val:
                    min_val = val
                    best_idx = (r, c)
            nearest_m = min_val
            nearest_cell = best_idx

        nearest_mm = nearest_m * 1000.0 if nearest_m < 999.0 else 9999.0

        # 3. Approach Velocity (differentiation over 5-frame sliding window)
        # Spec convention: mm/s, negative = closing in
        approach_vel_mm_s = 0.0
        approach_vel_mps = 0.0

        if nearest_m < 999.0:
            self._history.append((timestamp, nearest_mm))

            if len(self._history) >= 2:
                times = np.array([p[0] for p in self._history], dtype=np.float64)
                distances = np.array([p[1] for p in self._history], dtype=np.float64)
                dt_total = times[-1] - times[0]

                if dt_total > 1e-4:
                    if len(self._history) >= 3:
                        # Linear regression slope d(dist)/dt
                        t_mean = np.mean(times)
                        d_mean = np.mean(distances)
                        denom = np.sum((times - t_mean) ** 2)
                        if denom > 1e-8:
                            slope = float(np.sum((times - t_mean) * (distances - d_mean)) / denom)
                        else:
                            slope = float((distances[-1] - distances[0]) / dt_total)
                    else:
                        slope = float((distances[-1] - distances[0]) / dt_total)

                    # Negative slope = distance decreasing = closing in
                    approach_vel_mm_s = slope
                    # Backwards compat: positive = approaching
                    approach_vel_mps = -slope / 1000.0

        # 4. Reach Confidence [0.0..1.0]
        # Combines distance score, valid pixel density, and optical centering
        reach_confidence = 0.0
        centroid = None

        if nearest_m < 999.0 and nearest_cell is not None:
            # Distance score: optimal between 150mm and 450mm
            d_mm = nearest_mm
            if 150.0 <= d_mm <= 450.0:
                dist_score = 1.0
            elif 450.0 < d_mm <= 800.0:
                dist_score = max(0.0, 1.0 - (d_mm - 450.0) / 350.0)
            elif 80.0 <= d_mm < 150.0:
                dist_score = max(0.0, (d_mm - 80.0) / 70.0)
            else:
                dist_score = 0.0

            # Pixel density in the nearest target cell
            pixels_per_cell = cell_h * cell_w
            cell_density = min(1.0, cell_valid_pixel_counts[nearest_cell[0], nearest_cell[1]] / max(1.0, pixels_per_cell * 0.3))

            # Optical centering score (center is (5.5, 7.5))
            r_c, c_c = 5.5, 7.5
            norm_r_dist = abs(nearest_cell[0] - r_c) / 5.5
            norm_c_dist = abs(nearest_cell[1] - c_c) / 7.5
            center_score = max(0.2, 1.0 - 0.5 * np.hypot(norm_r_dist, norm_c_dist))

            reach_confidence = float(np.clip(dist_score * cell_density * center_score, 0.0, 1.0))

            # Centroid estimation across valid cells
            r_idx, c_idx = np.where(grid_valid)
            mean_r = float(np.mean(r_idx))
            mean_c = float(np.mean(c_idx))
            mean_z = float(np.mean(grid_depth_m[grid_valid]))
            centroid = (mean_c / self.grid_cols, mean_r / self.grid_rows, mean_z)

        return DistanceMatrixResult(
            grid_depth_m=grid_depth_m,
            grid_depth_mm=grid_depth_mm,
            grid_valid=grid_valid,
            nearest_distance_m=nearest_m,
            nearest_distance_mm=nearest_mm,
            nearest_cell=nearest_cell,
            centroid_3d_m=centroid,
            approach_velocity_mps=approach_vel_mps,
            approach_velocity_mm_s=approach_vel_mm_s,
            reach_confidence=reach_confidence,
        )
