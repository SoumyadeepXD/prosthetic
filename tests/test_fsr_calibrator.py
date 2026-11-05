"""Unit tests for FSR piecewise non-linear calibration curves and hardware fault detection."""

import numpy as np
import pytest
from vapa.control.fsr_calibrator import FSRCalibrator, FSRCalibrationCurve

def test_fsr_curve_interpolation():
    curve = FSRCalibrationCurve(
        finger_name="index",
        pin=33,
        baseline_raw=50,
        noise_margin=30,
        max_raw=3800,
        raw_points=np.array([50.0, 200.0, 800.0, 2000.0, 3600.0]),
        force_points=np.array([0.0, 50.0, 150.0, 300.0, 600.0]),
    )

    # 1. Below baseline + noise margin (50 + 30 = 80) -> deadband gives 0g
    grams, ok, err = curve.raw_to_grams(70)
    assert ok is True
    assert grams == 0.0

    # 2. Exact lookup points
    g_200, _, _ = curve.raw_to_grams(200)
    assert pytest.approx(g_200, abs=0.1) == 50.0

    g_800, _, _ = curve.raw_to_grams(800)
    assert pytest.approx(g_800, abs=0.1) == 150.0

    # 3. Intermediate interpolation point (midway between 200 and 800: 500)
    # (500 - 200)/(800 - 200) = 300/600 = 0.5 -> 50 + 0.5*(150 - 50) = 100g
    g_mid, ok_mid, _ = curve.raw_to_grams(500)
    assert ok_mid is True
    assert pytest.approx(g_mid, abs=0.5) == 100.0

def test_fsr_open_circuit_fault():
    curve = FSRCalibrationCurve(
        finger_name="index",
        pin=33,
        baseline_raw=50,
        noise_margin=30,
        max_raw=3800,
        raw_points=np.array([50.0, 500.0]),
        force_points=np.array([0.0, 100.0]),
    )
    # ADC = 5 indicates open circuit / disconnected sensor line (< 10)
    grams, ok, err = curve.raw_to_grams(5)
    assert ok is False
    assert grams == 0.0
    assert "open-circuit" in err.lower()

def test_fsr_short_circuit_fault():
    curve = FSRCalibrationCurve(
        finger_name="thumb",
        pin=32,
        baseline_raw=50,
        noise_margin=30,
        max_raw=3800,
        raw_points=np.array([50.0, 500.0]),
        force_points=np.array([0.0, 100.0]),
    )
    # ADC = 4095 indicates short to 3.3V rail (>= 4090)
    grams, ok, err = curve.raw_to_grams(4095)
    assert ok is False
    assert "short-circuit" in err.lower()

def test_fsr_calibrator_multi_sensor():
    cfg = {
        "sensors": {
            "thumb": {"pin": 32, "calibration_points": [[50, 0], [500, 100], [1500, 300]]},
            "index": {"pin": 33, "calibration_points": [[50, 0], [500, 100], [1500, 300]]},
            "middle": {"pin": 34, "calibration_points": [[50, 0], [500, 100], [1500, 300]]},
            "ring": {"pin": 35, "calibration_points": [[50, 0], [500, 100], [1500, 300]]},
            "little": {"pin": 36, "calibration_points": [[50, 0], [500, 100], [1500, 300]]},
        }
    }
    calibrator = FSRCalibrator(cfg)

    # Valid readings
    raw_readings = (500, 500, 500, 500, 500)
    forces, all_ok = calibrator.convert_readings(raw_readings)
    assert all_ok is True
    for f in ["thumb", "index", "middle", "ring", "little"]:
        assert pytest.approx(forces[f], abs=0.5) == 100.0

    # Fault injection: index disconnected (ADC=0)
    fault_readings = (500, 0, 500, 500, 500)
    forces_f, all_ok_f = calibrator.convert_readings(fault_readings)
    assert all_ok_f is False
    assert any("index" in fault for fault in calibrator.last_faults)
