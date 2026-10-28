"""Test distance matrix math on synthetic depth frames."""

import numpy as np
from vapa.vision import DistanceMatrixProcessor

def test_distance_matrix_grid_and_nearest():
    proc = DistanceMatrixProcessor(grid_rows=12, grid_cols=16, z_min_m=0.10, z_max_m=1.00)

    # 480x640 depth image with background at 2.0m (out of range)
    depth = np.full((480, 640), 2.0, dtype=np.float32)

    # Place an obstacle of 0.30m in top-left cells (row 0..39, col 0..39)
    depth[0:40, 0:40] = 0.30

    res = proc.process(depth, timestamp=1.0)
    assert res.grid_depth_m.shape == (12, 16)
    assert res.grid_valid[0, 0] is np.True_ or res.grid_valid[0, 0] == True
    assert res.grid_valid[11, 15] is np.False_ or res.grid_valid[11, 15] == False
    assert abs(res.nearest_distance_m - 0.30) < 1e-4

def test_distance_matrix_approach_velocity():
    proc = DistanceMatrixProcessor()

    depth1 = np.full((480, 640), 0.50, dtype=np.float32)
    proc.process(depth1, timestamp=1.0)

    depth2 = np.full((480, 640), 0.40, dtype=np.float32)
    res2 = proc.process(depth2, timestamp=1.1)

    # Approach velocity: (0.50 - 0.40) / 0.1s = 1.0 m/s
    assert abs(res2.approach_velocity_mps - 1.0) < 1e-2
