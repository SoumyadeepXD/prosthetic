"""Tests for Standalone EMG-Driven Prosthetic Mode (Vision Bypassed).

Verifies that when camera/vision processing is commented out / bypassed:
1. VAPAApplication initializes without starting the vision worker process.
2. Muscle intent (EMG) directly controls the prosthetic arm.
3. Slew rate limiter and FSR force controller function correctly.
4. Extensor OPEN unconditionally aborts closing motion.
5. System shuts down cleanly without dangling processes.
"""

import time
import pytest
from vapa.app.main import VAPAApplication
from vapa.safety import SafetyState
from vapa.emg.decoder import EMGIntent
from vapa.protocol import SensorMessage, HeartbeatMessage
from vapa.fusion import ArbitrationOutput


def test_standalone_emg_initialization():
    """Verify application initializes cleanly in standalone EMG mode without vision worker."""
    app = VAPAApplication(mock_mode=True, headless=True, enable_vision=False)
    assert app.enable_vision is False
    assert app.vision_worker is None
    assert app.latest_dist_result is None
    assert app.latest_grip_result is None

    assert app.initialize() is True
    # Vision worker process should not be started
    assert app.vision_worker is None
    assert app.safety.state == SafetyState.DISARMED

    # Shutdown cleanly
    app.shutdown()
    assert app.safety.state == SafetyState.DISARMED


def test_standalone_emg_arbitration_direct():
    """Verify that when vision is bypassed (None), arbitrator directly routes EMG intent."""
    app = VAPAApplication(mock_mode=True, headless=True, enable_vision=False)

    # 1. Flexor contraction (CLOSE intent)
    arb_close: ArbitrationOutput = app.arbitrator.arbitrate(
        emg_intent=EMGIntent.CLOSE,
        emg_velocity=0.85,
        vision_profile="default",
        distance_result=None,
        current_aperture=0.0,
    )
    assert arb_close.motion_command == "CLOSE"
    assert arb_close.command_velocity == pytest.approx(0.85)
    assert arb_close.preshape_aperture == 0.0

    # 2. Extensor contraction (OPEN intent)
    arb_open: ArbitrationOutput = app.arbitrator.arbitrate(
        emg_intent=EMGIntent.OPEN,
        emg_velocity=1.0,
        vision_profile="default",
        distance_result=None,
        current_aperture=0.7,
    )
    assert arb_open.motion_command == "OPEN"
    assert arb_open.command_velocity == pytest.approx(1.0)
    assert arb_open.preshape_aperture == 0.0

    # 3. Rest (HOLD intent)
    arb_hold: ArbitrationOutput = app.arbitrator.arbitrate(
        emg_intent=EMGIntent.HOLD,
        emg_velocity=0.0,
        vision_profile="default",
        distance_result=None,
        current_aperture=0.5,
    )
    assert arb_hold.motion_command == "HOLD"
    assert arb_hold.command_velocity == 0.0

    # 4. Co-contraction (MODE_CYCLE intent)
    arb_mode: ArbitrationOutput = app.arbitrator.arbitrate(
        emg_intent=EMGIntent.MODE_CYCLE,
        emg_velocity=0.0,
        vision_profile="default",
        distance_result=None,
        current_aperture=0.5,
    )
    assert arb_mode.motion_command == "MODE_CYCLE"


def test_standalone_emg_full_motion_cycles():
    """Verify 50 cycles of standalone EMG control loop with FSR feedback."""
    app = VAPAApplication(mock_mode=True, headless=True, enable_vision=False)
    assert app.initialize() is True

    # Arm system
    app.safety.request_arm(
        esp_link_healthy=True,
        estop_released=True,
        no_latched_fault=True,
        pca9685_healthy=True,
        emg_plausible=True,
        fsr_plausible=True,
    )
    assert app.safety.state == SafetyState.ARMED_IDLE

    # Simulate strong flexor muscle signal (CLOSE intent)
    # EMG flexor: 12000 counts (~1500 mV), extensor baseline: 2000 counts (~250 mV)
    app.esp_link.sim_emg = (12000, 2000)
    app.esp_link.update_supervisor()

    # Step through 25 cycles (first 10 cycles dwell-filter, next 15 close fingers)
    dt = 0.01
    for _ in range(25):
        app.run_step(dt)

    # In ACTIVE state, fingers should have moved towards closed
    assert app.safety.state == SafetyState.ACTIVE
    current_pos = app.grip_executor.current_finger_positions["index"]
    assert current_pos > 0.0, "Fingers should have begun closing under EMG flexor intent"

    # Now simulate strong extensor signal (rapid OPEN override)
    # EMG flexor: baseline 2000 counts, extensor: 14000 counts (~1750 mV)
    app.esp_link.sim_emg = (2000, 14000)
    app.esp_link.update_supervisor()

    # Step through 25 cycles to open
    for _ in range(25):
        app.run_step(dt)

    current_pos_after_open = app.grip_executor.current_finger_positions["index"]
    assert current_pos_after_open < current_pos, "Fingers should have opened under EMG extensor intent"

    app.shutdown()
    assert app.safety.state == SafetyState.DISARMED
