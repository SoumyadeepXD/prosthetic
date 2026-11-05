"""Fault Injection Test: Sensor Disconnection, Open/Short Circuits, and Signal Saturation.

Verifies:
1. FSR open-circuit (<10 counts) hardware disconnection detection.
2. FSR short-circuit (>=4090 counts) wiring failure detection.
3. EMG electrode saturation (>3200 mV) rail detection.
4. EMG electrode detachment / flatline stuck signal detection.
5. Extensor open command override executes reliably even under sensor anomalies.
"""

import pytest
import yaml
from vapa.control.fsr_calibrator import FSRCalibrator
from vapa.emg.envelope import EnvelopeNormalizer, EMGCalibration
from vapa.safety import SafetyStateMachine, SafetyState, PWMGate
from vapa.hal import MockPCA9685


@pytest.fixture
def fsr_calibrator():
    with open("config/fsr.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    return FSRCalibrator(cfg)


def test_fsr_open_circuit_disconnection(fsr_calibrator):
    """Verify that a broken FSR wire (<10 ADC counts) trips open-circuit fault."""
    sm = SafetyStateMachine()
    sm.request_arm(
        esp_link_healthy=True,
        estop_released=True,
        no_latched_fault=True,
        pca9685_healthy=True,
        encoders_healthy=True,
        emg_plausible=True,
        fsr_plausible=True,
    )
    sm.set_active()

    # Normal reading
    grams, plausible, err = fsr_calibrator.curves["thumb"].raw_to_grams(1200)
    assert plausible is True
    assert grams > 0.0
    assert err is None

    # Broken wire: ADC drops to 0 counts
    fault_grams, fault_plausible, fault_err = fsr_calibrator.curves["thumb"].raw_to_grams(0)
    assert fault_plausible is False
    assert "open-circuit" in fault_err.lower()

    # System disarms on sensor hardware fault
    sm.trigger_fault(f"Thumb FSR fault: {fault_err}")
    assert sm.state == SafetyState.FAULT
    assert sm.is_pwm_allowed is False


def test_fsr_short_circuit_fault(fsr_calibrator):
    """Verify that an FSR shorted to 3.3V rail (>=4090 ADC counts) trips fault."""
    _, fault_plausible, fault_err = fsr_calibrator.curves["index"].raw_to_grams(4094)
    assert fault_plausible is False
    assert "short-circuit" in fault_err.lower()


def test_emg_rail_saturation_fault():
    """Verify that an electrode motion artifact or power rail short (>3200 mV) faults."""
    normalizer = EnvelopeNormalizer(
        flexor_cal=EMGCalibration(baseline_mv=250.0, mvc_mv=2200.0, saturation_mv=3200.0),
        extensor_cal=EMGCalibration(baseline_mv=250.0, mvc_mv=2200.0, saturation_mv=3200.0),
        stuck_window_size=10,
    )
    sm = SafetyStateMachine()

    # Saturated signal injected
    _, _, healthy = normalizer.normalize(3250.0, 300.0)
    assert healthy is False
    assert "saturated" in normalizer.last_fault_reason.lower()

    sm.trigger_fault(f"EMG hardware failure: {normalizer.last_fault_reason}")
    assert sm.state == SafetyState.FAULT


def test_emg_flatline_disconnect_fault():
    """Verify that a detached electrode presenting unchanging flatline counts faults."""
    normalizer = EnvelopeNormalizer(
        flexor_cal=EMGCalibration(baseline_mv=250.0, mvc_mv=2200.0, saturation_mv=3200.0),
        extensor_cal=EMGCalibration(baseline_mv=250.0, mvc_mv=2200.0, saturation_mv=3200.0),
        stuck_window_size=10,
    )

    # Feed perfectly flatline 150 mV for 10 samples
    for i in range(10):
        _, _, healthy = normalizer.normalize(150.0, 150.0)

    assert healthy is False
    assert "stuck" in normalizer.last_fault_reason.lower()


def test_extensor_open_override_immunity_to_vision():
    """Verify non-negotiable rule 5: EMG open overrides all grips and vision contexts."""
    from vapa.emg.decoder import EMGIntent
    from vapa.fusion.arbitrator import SharedControlArbitrator

    with open("config/grip_profiles.yaml") as f:
        grip_cfg = yaml.safe_load(f)

    arbitrator = SharedControlArbitrator(grip_cfg)

    # User commands intentional OPEN
    output = arbitrator.arbitrate(
        emg_intent=EMGIntent.OPEN,
        emg_velocity=1.0,
        vision_profile="cylindrical",
        distance_result=None,
        current_aperture=0.8,
    )

    # Grasping MUST NOT close; must execute OPEN release
    assert output.motion_command == "OPEN"
    assert output.preshape_aperture == 0.0  # Fully open
