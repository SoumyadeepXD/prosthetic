"""Comprehensive integration tests for Phase 8 (Fusion, 100 Hz Loop, UI, and Orchestration)."""

import pytest
import time
import numpy as np
from pathlib import Path
from vapa.fusion import SharedControlArbitrator, ArbitrationOutput
from vapa.emg import EMGIntent
from vapa.vision.distance_matrix import DistanceMatrixResult
from vapa.ui import StatusScreen, UIStatusModel
from vapa.app.main import VAPAApplication
from vapa.safety.state_machine import SafetyState


@pytest.fixture
def arbitrator():
    profiles = {
        "profiles": {
            "default": {"force_cap_grams": 300.0, "preshape": {"index": 0.2}},
            "cylindrical": {"force_cap_grams": 350.0, "preshape": {"index": 0.1}},
            "pinch": {"force_cap_grams": 150.0, "preshape": {"index": 0.05}},
        }
    }
    return SharedControlArbitrator(profiles)


def test_property_vision_alone_can_never_close(arbitrator):
    """PROPERTY TEST: Over a 100-point sweep of distances and reach confidences,
    vision alone with EMG=HOLD must NEVER command CLOSE.
    """
    distances = np.linspace(0.05, 1.5, 10)
    confidences = np.linspace(0.0, 1.0, 10)

    for d in distances:
        for conf in confidences:
            dist_res = DistanceMatrixResult(
                grid_depth_m=np.full((12, 16), d, dtype=np.float32),
                grid_valid=np.ones((12, 16), dtype=bool),
                nearest_distance_m=d,
                centroid_3d_m=(0.5, 0.5, d),
                approach_velocity_mps=0.5,
                reach_confidence=conf,
            )

            out = arbitrator.arbitrate(
                emg_intent=EMGIntent.HOLD,
                emg_velocity=0.0,
                vision_profile="pinch",
                distance_result=dist_res,
                current_aperture=0.1,
            )

            # Mathematical invariant: motion_command is NEVER CLOSE
            assert out.motion_command != "CLOSE", f"Violated at dist={d}, conf={conf}"
            assert out.motion_command == "HOLD"


def test_proportional_closing_and_force_ceiling(arbitrator):
    dist_res = DistanceMatrixResult(
        grid_depth_m=np.full((12, 16), 0.30, dtype=np.float32),
        grid_valid=np.ones((12, 16), dtype=bool),
        nearest_distance_m=0.30,
        centroid_3d_m=(0.5, 0.5, 0.30),
        approach_velocity_mps=0.1,
        reach_confidence=0.8,
    )

    # User contracts flexor at 70% effort
    out = arbitrator.arbitrate(
        emg_intent=EMGIntent.CLOSE,
        emg_velocity=0.70,
        vision_profile="pinch",
        distance_result=dist_res,
        current_aperture=0.0,
    )

    assert out.motion_command == "CLOSE"
    assert out.command_velocity == 0.70
    assert out.force_cap_grams == 150.0  # Pinch profile force cap
    assert out.active_profile == "pinch"


def test_status_screen_ascii_dashboard():
    screen = StatusScreen(width=800, height=480, headless=True)
    screen.update(
        safety_state="ARMED_IDLE",
        active_profile="cylindrical",
        heartbeat_ok=True,
        estop_pressed=False,
        oe_enabled=True,
        nearest_distance_mm=320.0,
        reach_confidence=0.85,
        target_class="bottle",
        target_confidence=0.91,
        emg_flex_norm=0.45,
        emg_ext_norm=0.10,
        emg_intent="CLOSE",
        fsr_forces=(120.0, 110.0, 95.0, 80.0, 60.0),
        loop_rate_hz=100.0,
        loop_jitter_ms=0.25,
        max_cycle_ms=4.5,
    )

    ascii_out = screen.format_ascii_dashboard()
    assert "VAPA 800x480 STATUS DASHBOARD" in ascii_out
    assert "ARMED_IDLE" in ascii_out
    assert "cylindrical" in ascii_out
    assert "OK (50 Hz)" in ascii_out
    assert "320.0mm" in ascii_out
    assert "FLEX:" in ascii_out
    assert "Rate: 100.0 Hz" in ascii_out


def test_vapa_app_end_to_end_mock_run():
    """Start the whole stack in mock mode, execute 25 control cycles (0.25s), and verify clean shutdown."""
    app = VAPAApplication(mock_mode=True, headless=True)
    assert app.initialize()

    # Preconditions check and request arm
    app.safety.request_arm(
        esp_link_healthy=True,
        estop_released=True,
        no_latched_fault=True,
        pca9685_healthy=True,
        encoders_healthy=True,
        emg_plausible=True,
        fsr_plausible=True,
    )
    assert app.safety.state == SafetyState.ARMED_IDLE

    # Run 25 cycles @ 100 Hz = 0.25 s
    dt = 0.01
    for _ in range(25):
        app.run_step(dt)

    assert app._cycle_count == 25
    assert app.heartbeat.is_alive()
    assert app.ui.model.loop_rate_hz == 100.0

    # Shutdown cleanly
    app.shutdown()
    assert app.safety.state == SafetyState.DISARMED
    assert not app.heartbeat.is_alive()
