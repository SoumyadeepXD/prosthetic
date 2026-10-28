"""Comprehensive tests for RealSense distance matrix, filters, tracking, and replay harness."""

import pytest
import numpy as np
from pathlib import Path
from vapa.vision import (
    DistanceMatrixProcessor,
    DistanceMatrixResult,
    SoftwareDepthFilter,
    FilterConfig,
    VisionSequenceRecorder,
    VisionReplayHarness,
)


def test_distance_matrix_grid_and_nearest():
    proc = DistanceMatrixProcessor(grid_rows=12, grid_cols=16, z_min_m=0.10, z_max_m=1.00)

    # 480x640 depth image with background at 2.0m (out of range)
    depth = np.full((480, 640), 2.0, dtype=np.float32)

    # Place an obstacle of 0.30m in top-left cells (row 0..39, col 0..39)
    depth[0:40, 0:40] = 0.30

    res = proc.process(depth, timestamp=1.0)
    assert res.grid_depth_m.shape == (12, 16)
    assert res.grid_depth_mm.shape == (12, 16)
    assert res.grid_valid[0, 0] is np.True_ or res.grid_valid[0, 0] == True
    assert res.grid_valid[11, 15] is np.False_ or res.grid_valid[11, 15] == False
    assert abs(res.nearest_distance_m - 0.30) < 1e-4
    assert abs(res.nearest_distance_mm - 300.0) < 1e-1


def test_distance_matrix_approach_velocity_spec():
    """Verify approach velocity in mm/s (negative = closing in per Master Prompt spec) and 5-frame window."""
    proc = DistanceMatrixProcessor()

    # Frame 1 to 5: Object moving from 500mm to 300mm in 0.1s steps (vel = -500 mm/s)
    # 500mm, 450mm, 400mm, 350mm, 300mm at t = 0.0, 0.1, 0.2, 0.3, 0.4
    depths = [0.50, 0.45, 0.40, 0.35, 0.30]
    times = [0.0, 0.1, 0.2, 0.3, 0.4]

    res = None
    for d, t in zip(depths, times):
        frame = np.full((480, 640), d, dtype=np.float32)
        res = proc.process(frame, timestamp=t)

    assert res is not None
    # Approach velocity should be negative mm/s (closing in)
    assert res.approach_velocity_mm_s < 0
    assert pytest.approx(res.approach_velocity_mm_s, abs=10.0) == -500.0
    # Backwards compatibility m/s (positive = approaching)
    assert pytest.approx(res.approach_velocity_mps, abs=0.01) == 0.50


def test_central_zone_target_tracking():
    proc = DistanceMatrixProcessor(
        grid_rows=12,
        grid_cols=16,
        central_row_range=(2, 9),
        central_col_range=(3, 12),
    )

    depth = np.full((480, 640), 1.5, dtype=np.float32)

    # Place Object A at row 0, col 0 (outside central zone) at 0.25m
    depth[0:40, 0:40] = 0.25

    # Place Object B at center (row 5, col 7) at 0.35m
    cy_start, cy_end = 5 * 40, 6 * 40
    cx_start, cx_end = 7 * 40, 8 * 40
    depth[cy_start:cy_end, cx_start:cx_end] = 0.35

    res = proc.process(depth, timestamp=1.0)
    # The central zone object (0.35m) MUST be prioritized over peripheral object (0.25m)
    assert res.nearest_cell == (5, 7)
    assert pytest.approx(res.nearest_distance_m, 0.01) == 0.35
    assert res.reach_confidence > 0.5


def test_software_depth_filters():
    cfg = FilterConfig(
        spatial_filter=True,
        spatial_smooth_alpha=0.5,
        spatial_smooth_delta=0.05,
        temporal_filter=True,
        temporal_smooth_alpha=0.5,
        temporal_smooth_delta=0.05,
        hole_filling=1,
    )
    filt = SoftwareDepthFilter(cfg)

    # 1. Edge-preserving spatial filter check:
    # A step change of 1.0m (from 0.3m to 1.3m) should NOT be blurred across the boundary
    frame1 = np.full((100, 100), 0.30, dtype=np.float32)
    frame1[:, 50:] = 1.30  # Step edge
    filtered1 = filt.process(frame1)

    assert pytest.approx(filtered1[50, 48], 0.01) == 0.30
    assert pytest.approx(filtered1[50, 52], 0.01) == 1.30

    # 2. Hole filling check:
    # A single zero pixel surrounded by 0.40m should be filled
    frame2 = np.full((100, 100), 0.40, dtype=np.float32)
    frame2[50, 50] = 0.0  # Missing pixel
    filtered2 = filt.process(frame2)
    assert filtered2[50, 50] > 0.0

    # 3. Temporal persistence check:
    # If a pixel drops to 0.0 in the next frame, temporal persistence holds it
    frame3 = np.full((100, 100), 0.40, dtype=np.float32)
    frame3[20, 20] = 0.0
    filtered3 = filt.process(frame3)
    assert filtered3[20, 20] > 0.0  # Held by temporal persistence


def test_vision_sequence_recorder_and_replay_harness(tmp_path):
    seq_file = tmp_path / "test_approach.npz"

    # Generate synthetic sequence of 10 frames
    VisionSequenceRecorder.create_synthetic_sequence(
        filepath=seq_file,
        num_frames=10,
        fps=30.0,
        start_dist_m=0.60,
        end_dist_m=0.30,
    )
    assert seq_file.exists()

    harness = VisionReplayHarness(seq_file)
    assert len(harness) == 10

    results = []
    for idx, res, t in harness.stream():
        results.append(res)
        assert res.grid_depth_m.shape == (12, 16)
        assert res.nearest_distance_m <= 0.65

    # Check that distance decreased monotonically
    first_dist = results[0].nearest_distance_mm
    last_dist = results[-1].nearest_distance_mm
    assert last_dist < first_dist

    # Velocity at the end should be negative (closing in)
    assert results[-1].approach_velocity_mm_s < 0.0

    # Reach confidence should be higher at 300mm than at 600mm
    assert results[-1].reach_confidence > results[0].reach_confidence
