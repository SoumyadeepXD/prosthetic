"""Main orchestrator and CLI application for VAPA (Rev 2).

Architecture:
- Dedicated 30 Hz Multiprocessing Vision Worker (never blocks control loop).
- Deterministic 100 Hz Main Control Loop with perf_counter jitter tracking.
- Dedicated 50 Hz Heartbeat Watchdog Thread.
- Fail-Closed Safety State Machine and Hardware-Gated PWM Outputs.
- 800x480 Status Display with Headless Fallback.
"""

import os
import sys
import time
import signal
import atexit
import argparse
import multiprocessing as mp
from queue import Empty
from pathlib import Path
from typing import Optional, Dict, Any
import yaml
import logging

from ..safety import SafetyStateMachine, SafetyState, HeartbeatThread, PWMGate
from ..hal import MockPCA9685, MockTCA9548A, MockAS5600, MockESPLink
from ..control import (
    ServoMapper,
    SlewRateLimiter,
    FingerForceController,
    GripExecutor,
    EncoderMonitor,
    FSRCalibrator,
)
from ..emg import (
    ThresholdEMGDecoder,
    EnvelopeNormalizer,
    EMGCalibration,
    counts_to_mv,
)
from ..vision.worker import VisionWorker
from ..vision.distance_matrix import DistanceMatrixResult
from ..vision.detector import GripSelectionResult
from ..fusion import SharedControlArbitrator, ArbitrationOutput
from ..logging import SessionRecorder
from ..ui import StatusScreen

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("vapa.app")

class VAPAApplication:
    """Master orchestrator integrating Safety, HAL, Control, EMG, Vision, and UI."""

    def __init__(
        self,
        mock_mode: bool = True,
        config_dir: str = "config",
        record: bool = False,
        headless: Optional[bool] = None,
    ):
        self.mock_mode = mock_mode
        self.config_dir = Path(config_dir)
        self.record_enabled = record

        # Load YAML configurations
        self.hw_config = self._load_yaml("hardware.yaml")
        self.servo_config = self._load_yaml("servos.yaml")
        self.fsr_config = self._load_yaml("fsr.yaml")
        self.emg_config = self._load_yaml("emg.yaml")
        self.grip_config = self._load_yaml("grip_profiles.yaml")
        self.vision_config = self._load_yaml("vision.yaml")

        # Core Safety State Machine
        self.safety = SafetyStateMachine()

        # HAL Layer
        if self.mock_mode:
            self.pca9685 = MockPCA9685()
            self.tca9548a = MockTCA9548A()
            self.as5600 = MockAS5600()
            self.esp_link = MockESPLink()
        else:
            from ..hal.factory import create_hal_container
            container = create_hal_container(backend="real")
            self.pca9685 = container.pca9685
            self.tca9548a = container.tca9548a
            self.as5600 = container.as5600
            self.esp_link = container.esp_link

        # PWM Arm Gate
        self.pwm_gate = PWMGate(self.pca9685, self.safety)

        # Control Subsystems
        self.mapper = ServoMapper(self.servo_config)
        slew_rates = {k: float(v.get("max_slew_rate_deg_s", 180.0)) for k, v in self.servo_config.get("servos", {}).items()}
        self.slew_limiter = SlewRateLimiter(slew_rates)
        self.force_controller = FingerForceController()
        self.fsr_calibrator = FSRCalibrator(self.fsr_config)
        self.grip_executor = GripExecutor(
            mapper=self.mapper,
            slew_limiter=self.slew_limiter,
            force_controller=self.force_controller,
            pwm_gate=self.pwm_gate,
        )
        self.encoder_monitor = EncoderMonitor()

        # EMG Processing Subsystem
        f_thresh = self.emg_config.get("thresholds", {}).get("flexor", {})
        e_thresh = self.emg_config.get("thresholds", {}).get("extensor", {})
        self.emg_normalizer = EnvelopeNormalizer(
            flexor_cal=EMGCalibration(
                baseline_mv=float(f_thresh.get("baseline_mv", 250.0)),
                mvc_mv=float(f_thresh.get("mvc_mv", 2200.0)),
                saturation_mv=float(f_thresh.get("saturation_mv", 3200.0)),
            ),
            extensor_cal=EMGCalibration(
                baseline_mv=float(e_thresh.get("baseline_mv", 250.0)),
                mvc_mv=float(e_thresh.get("mvc_mv", 2000.0)),
                saturation_mv=float(e_thresh.get("saturation_mv", 3200.0)),
            ),
        )
        self.emg_decoder = ThresholdEMGDecoder()

        # Shared Control Arbitration
        self.arbitrator = SharedControlArbitrator(self.grip_config)

        # Telemetry & UI
        self.recorder = SessionRecorder(enabled=self.record_enabled)
        self.ui = StatusScreen(headless=headless)

        # Vision Multiprocess Communication
        self.vision_queue = mp.Queue(maxsize=2)
        self.vision_stop = mp.Event()
        self.vision_worker = VisionWorker(
            result_queue=self.vision_queue,
            stop_event=self.vision_stop,
            mock_mode=self.mock_mode,
            fps=30,
            config_dir=str(self.config_dir),
        )

        # Latest vision context cache
        self.latest_dist_result: Optional[DistanceMatrixResult] = None
        self.latest_grip_result: Optional[GripSelectionResult] = None
        self.latest_vision_time: float = 0.0

        # Dedicated 50 Hz Heartbeat Watchdog Thread
        self.heartbeat = HeartbeatThread(
            send_fn=self.esp_link.send_message,
            get_arm_request_fn=lambda: self.safety.arm_request,
            get_state_fn=lambda: self.safety.state.value,
        )

        # Performance & Diagnostics
        self._cycle_count = 0
        self._last_perf_time = time.perf_counter()
        self._max_cycle_ms = 0.0
        self._jitter_accumulator_ms = 0.0
        self._running = False

        self._register_safety_handlers()

    def _load_yaml(self, filename: str) -> dict:
        filepath = self.config_dir / filename
        if filepath.exists():
            with open(filepath, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    def _register_safety_handlers(self) -> None:
        """Register fail-closed signal handlers and atexit hook."""
        def emergency_shutdown(signum, frame):
            logger.warning(f"OS Signal {signum} caught! Disarming immediately...")
            self.shutdown()
            sys.exit(0)

        signal.signal(signal.SIGINT, emergency_shutdown)
        signal.signal(signal.SIGTERM, emergency_shutdown)
        atexit.register(self.shutdown)

    def initialize(self) -> bool:
        """Initialize HAL hardware, start vision process and heartbeat thread."""
        logger.info("Initializing VAPA subsystems...")
        ok = (
            self.pca9685.initialize()
            and self.tca9548a.initialize()
            and self.as5600.initialize()
            and self.esp_link.initialize()
        )
        if not ok:
            logger.error("Failed to initialize one or more HAL devices")
            return False

        # Start 30 Hz Vision Multiprocessing Worker
        self.vision_worker.start()

        # Start 50 Hz Heartbeat Thread
        self.heartbeat.start()

        if self.record_enabled:
            snapshot = {
                "hardware": self.hw_config,
                "servos": self.servo_config,
                "fsr": self.fsr_config,
                "emg": self.emg_config,
            }
            self.recorder.start_session(snapshot)

        logger.info(f"VAPA initialized successfully in state: {self.safety.state.name}")
        return True

    def run_step(self, dt_s: float = 0.01) -> None:
        """Execute one 100 Hz control cycle with jitter measurement and fail-safe gating."""
        t_cycle_start = time.perf_counter()
        self._cycle_count += 1

        # 1. Feed Heartbeat Watchdog
        self.heartbeat.feed()

        # 2. Poll Vision Queue (Non-blocking: control loop never blocks on vision)
        try:
            while True:
                dist_res, grip_res, t_vis = self.vision_queue.get_nowait()
                self.latest_dist_result = dist_res
                self.latest_grip_result = grip_res
                self.latest_vision_time = time.time()
        except Empty:
            pass

        # Vision freshness check (timeout if no vision packet received in > 0.25s / 250ms)
        if self.latest_vision_time > 0 and (time.time() - self.latest_vision_time) > 0.25:
            self.latest_dist_result = None
            self.latest_grip_result = None

        # 3. Read Sensor Telemetry from ESP32 Link
        sensor_msg = self.esp_link.get_latest_sensor()
        if not sensor_msg:
            # Check for link timeout
            return

        # 4. Check ESP32 Supervisor Fault Flags
        if sensor_msg.estop_pressed:
            self.safety.trigger_estop("Physical Emergency Stop active")
        elif sensor_msg.force_fault:
            self.safety.trigger_fault("ESP32 supervisor hardware force ceiling fault")
        elif sensor_msg.ads_fault:
            self.safety.trigger_fault("ESP32 supervisor ADS1115 ADC fault")

        # 5. Process EMG Envelope & Health
        raw_flex_mv = counts_to_mv(sensor_msg.emg[0])
        raw_ext_mv = counts_to_mv(sensor_msg.emg[1])
        a_flex, a_ext, emg_healthy = self.emg_normalizer.normalize(raw_flex_mv, raw_ext_mv)
        if not emg_healthy:
            self.safety.trigger_fault(f"EMG signal failure: {self.emg_normalizer.last_fault_reason}")

        # 6. Decode EMG Intent (with Dwell, Hysteresis, and Open Override)
        emg_intent, emg_velocity = self.emg_decoder.decode(a_flex, a_ext, dt_s)

        # 7. Shared-Control Arbitration
        suggested_profile = self.latest_grip_result.profile_name if self.latest_grip_result else "default"
        current_aperture = self.grip_executor.current_finger_positions.get("index", 0.0)

        arb: ArbitrationOutput = self.arbitrator.arbitrate(
            emg_intent=emg_intent,
            emg_velocity=emg_velocity,
            vision_profile=suggested_profile,
            distance_result=self.latest_dist_result,
            current_aperture=current_aperture,
        )

        # 8. Motion & Grip Execution (Clamp -> Slew -> PWMGate)
        active_prof_data = self.grip_config.get("profiles", {}).get(arb.active_profile, {})
        preshape_val = arb.preshape_aperture

        # Calibrate raw FSR ADC readings to grams using piecewise calibration curve
        fsr_grams, fsr_ok = self.fsr_calibrator.convert_readings(sensor_msg.fsr)
        if not fsr_ok:
            fault_desc = ", ".join(self.fsr_calibrator.last_faults)
            self.safety.trigger_fault(f"FSR sensor fault: {fault_desc}")

        commanded_pulses = self.grip_executor.step(
            motion_command=arb.motion_command,
            emg_velocity=arb.command_velocity,
            profile_data=active_prof_data,
            preshape_aperture=preshape_val,
            measured_forces=fsr_grams,
            dt_s=dt_s,
        )

        # 9. Closed-Loop Encoder Monitoring
        # Build commanded angles for all monitored joints (including finger_group)
        commanded_angles = dict(self.grip_executor.current_joint_angles)
        commanded_angles["finger_group"] = self.grip_executor.current_finger_positions.get("index", 0.0) * 90.0

        # In mock mode, advance mock physical positions towards commanded angles
        if isinstance(self.as5600, MockAS5600):
            self.as5600.simulate_step(commanded_angles)

        # Read actual measured joint angles from AS5600 sensors behind TCA9548A mux
        measured_angles: Dict[str, float] = {}
        for joint in self.encoder_monitor.monitored_joints:
            status = self.as5600.read_joint_status(joint)
            if not status.is_valid:
                self.safety.trigger_fault(f"Encoder invalid or disconnected for joint '{joint}'")
                break
            measured_angles[joint] = status.joint_angle_degrees

        enc_fault, enc_reason = self.encoder_monitor.update(
            commanded_angles=commanded_angles,
            measured_angles=measured_angles,
            dt_s=dt_s,
        )
        if enc_fault:
            self.safety.trigger_fault(enc_reason or "Encoder tracking mismatch")

        # 10. Record Telemetry
        if self.record_enabled:
            self.recorder.record_sensors(
                t_ms=sensor_msg.t_ms,
                emg=sensor_msg.emg,
                fsr=sensor_msg.fsr,
                safety_state=self.safety.state.name,
                arm_request=self.safety.arm_request,
                flags=sensor_msg.flags,
            )

        # 11. Timing & Jitter Measurement
        t_cycle_end = time.perf_counter()
        cycle_time_s = t_cycle_end - t_cycle_start
        cycle_ms = cycle_time_s * 1000.0
        jitter_ms = abs(cycle_ms - (dt_s * 1000.0))
        self._max_cycle_ms = max(self._max_cycle_ms, cycle_ms)
        self._jitter_accumulator_ms = 0.9 * self._jitter_accumulator_ms + 0.1 * jitter_ms

        if cycle_ms > 15.0:
            logger.warning(f"Control loop cycle exceeded 15 ms: {cycle_ms:.2f} ms")
        if cycle_ms > 40.0:
            self.safety.trigger_fault(f"Control loop stall watchdog: cycle took {cycle_ms:.2f} ms (>40ms)")

        # 12. Update UI Status Model
        nearest_mm = self.latest_dist_result.nearest_distance_mm if self.latest_dist_result else 0.0
        reach_conf = self.latest_dist_result.reach_confidence if self.latest_dist_result else 0.0
        app_vel = self.latest_dist_result.approach_velocity_mm_s if self.latest_dist_result else 0.0
        grid_m = self.latest_dist_result.grid_depth_m if self.latest_dist_result else None
        grid_v = self.latest_dist_result.grid_valid if self.latest_dist_result else None

        self.ui.update(
            safety_state=self.safety.state.name,
            active_profile=arb.active_profile,
            heartbeat_ok=sensor_msg.heartbeat_ok,
            estop_pressed=sensor_msg.estop_pressed,
            oe_enabled=sensor_msg.oe_enabled,
            fault_reason=self.safety.fault_reason,
            nearest_distance_mm=nearest_mm,
            reach_confidence=reach_conf,
            approach_velocity_mm_s=app_vel,
            grid_depth_m=grid_m,
            grid_valid=grid_v,
            target_class=self.latest_grip_result.class_name if self.latest_grip_result else None,
            target_confidence=self.latest_grip_result.confidence if self.latest_grip_result else 0.0,
            bounding_box=self.latest_grip_result.bounding_box if self.latest_grip_result else None,
            emg_flex_norm=a_flex,
            emg_ext_norm=a_ext,
            emg_flex_mv=raw_flex_mv,
            emg_ext_mv=raw_ext_mv,
            emg_intent=emg_intent.name,
            fsr_forces=tuple(fsr_grams.values()),
            loop_rate_hz=100.0,
            loop_jitter_ms=self._jitter_accumulator_ms,
            max_cycle_ms=self._max_cycle_ms,
        )
        self.ui.render()

    def shutdown(self) -> None:
        """Safe fail-closed system shutdown."""
        if not self._running and self.safety.state == SafetyState.DISARMED:
            return
        self._running = False
        logger.info("Executing fail-closed system shutdown...")

        self.safety.disarm("System shutdown")
        self.heartbeat.stop()

        # Terminate vision worker
        self.vision_stop.set()
        if hasattr(self, "vision_worker") and self.vision_worker.is_alive():
            self.vision_worker.join(timeout=1.0)
            if self.vision_worker.is_alive():
                self.vision_worker.terminate()

        if hasattr(self, "pwm_gate"):
            self.pwm_gate.close()
        if hasattr(self, "pca9685"):
            self.pca9685.disable_all()
            self.pca9685.close()
        if hasattr(self, "esp_link"):
            self.esp_link.close()
        if hasattr(self, "recorder"):
            self.recorder.close()

        logger.info("Safe shutdown complete. System disarmed.")

def main():
    parser = argparse.ArgumentParser(description="VAPA Prosthetic Arm Master Orchestrator")
    parser.add_argument("--mock", action="store_true", default=True, help="Run with mock hardware backends")
    parser.add_argument("--config", type=str, default="config", help="Configuration directory path")
    parser.add_argument("--record", action="store_true", help="Record session telemetry to logs/")
    parser.add_argument("--headless", action="store_true", help="Run without graphical display")
    parser.add_argument("--duration", type=float, default=0.0, help="Optional duration in seconds (0 = run indefinitely)")
    args = parser.parse_args()

    app = VAPAApplication(
        mock_mode=args.mock,
        config_dir=args.config,
        record=args.record,
        headless=args.headless,
    )

    if not app.initialize():
        sys.exit(1)

    # Arm system if mock mode and preconditions pass
    if args.mock:
        app.safety.request_arm(
            esp_link_healthy=True,
            estop_released=True,
            no_latched_fault=True,
            pca9685_healthy=True,
            encoders_healthy=True,
            emg_plausible=True,
            fsr_plausible=True,
        )

    logger.info("Starting 100 Hz main control loop (Press Ctrl+C to terminate)...")
    app._running = True
    start_time = time.time()
    dt = 0.01  # 100 Hz

    try:
        while app._running:
            t0 = time.perf_counter()
            app.run_step(dt)
            elapsed = time.perf_counter() - t0
            sleep_time = max(0.0, dt - elapsed)
            time.sleep(sleep_time)

            if args.duration > 0.0 and (time.time() - start_time) >= args.duration:
                logger.info(f"Duration limit ({args.duration}s) reached. Exiting cleanly.")
                break
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    finally:
        app.shutdown()

if __name__ == "__main__":
    main()
