"""Test shared-control arbitration safety properties."""

import pytest
from vapa.fusion import SharedControlArbitrator
from vapa.emg import EMGIntent
from vapa.vision.distance_matrix import DistanceMatrixResult
import numpy as np

@pytest.fixture
def arbitrator():
    profiles = {
        "profiles": {
            "default": {"force_cap_grams": 300.0, "preshape": {"index": 0.2}},
            "cylindrical": {"force_cap_grams": 350.0, "preshape": {"index": 0.1}},
        }
    }
    return SharedControlArbitrator(profiles)

def test_vision_alone_cannot_command_close(arbitrator):
    # Obstacle very close (0.15m), high confidence reach, vision detects cylindrical
    dist_res = DistanceMatrixResult(
        grid_depth_m=np.full((12, 16), 0.15, dtype=np.float32),
        grid_valid=np.ones((12, 16), dtype=bool),
        nearest_distance_m=0.15,
        centroid_3d_m=(0.5, 0.5, 0.15),
        approach_velocity_mps=0.2,
        reach_confidence=1.0,
    )

    # EMG is HOLD (user is not flexing)
    out = arbitrator.arbitrate(
        emg_intent=EMGIntent.HOLD,
        emg_velocity=0.0,
        vision_profile="cylindrical",
        distance_result=dist_res,
        current_aperture=0.0,
    )

    # Invariant: Motion command CANNOT be CLOSE
    assert out.motion_command != "CLOSE"
    assert out.motion_command == "HOLD"
    # Preshape aperture may adapt towards target aperture, but never exceed preshape target
    assert out.preshape_aperture <= 0.2

def test_emg_open_always_wins_over_everything(arbitrator):
    dist_res = DistanceMatrixResult(
        grid_depth_m=np.full((12, 16), 0.15, dtype=np.float32),
        grid_valid=np.ones((12, 16), dtype=bool),
        nearest_distance_m=0.15,
        centroid_3d_m=(0.5, 0.5, 0.15),
        approach_velocity_mps=0.2,
        reach_confidence=1.0,
    )

    out = arbitrator.arbitrate(
        emg_intent=EMGIntent.OPEN,
        emg_velocity=0.8,
        vision_profile="cylindrical",
        distance_result=dist_res,
        current_aperture=0.5,
    )

    assert out.motion_command == "OPEN"
    assert out.preshape_aperture == 0.0
    assert out.command_velocity == 0.8
