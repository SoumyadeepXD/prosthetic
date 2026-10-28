"""Grip executor applying grip profiles, force control, and coordinated servo commands."""

from typing import Dict, Any, Optional
from .servo_mapper import ServoMapper
from .slew_limiter import SlewRateLimiter
from .force_controller import FingerForceController
from ..safety.pwm_gate import PWMGate

class GripExecutor:
    """Coordinates finger motion, force feedback, and joint posture according to active grip profile."""

    FINGERS = ["thumb", "index", "middle", "ring", "little"]
    JOINTS = ["wrist_flex", "wrist_rotate", "wrist_bend", "forearm_rotation"]

    def __init__(
        self,
        mapper: ServoMapper,
        slew_limiter: SlewRateLimiter,
        force_controller: FingerForceController,
        pwm_gate: PWMGate,
        open_rate: float = 2.0,  # Normalized units per second for opening (fast)
    ):
        self.mapper = mapper
        self.slew_limiter = slew_limiter
        self.force_controller = force_controller
        self.gate = pwm_gate
        self.open_rate = open_rate

        self.current_finger_positions: Dict[str, float] = {f: 0.0 for f in self.FINGERS}
        self.current_joint_angles: Dict[str, float] = {j: 0.0 for j in self.JOINTS}

    def reset(self) -> None:
        for f in self.FINGERS:
            self.current_finger_positions[f] = 0.0
        for j in self.JOINTS:
            self.current_joint_angles[j] = 0.0
        self.force_controller.reset()

    def step(
        self,
        motion_command: str,          # "OPEN", "CLOSE", "HOLD", "MODE_CYCLE"
        emg_velocity: float,          # [0.0..1.0]
        profile_data: Dict[str, Any], # Active grip profile
        preshape_aperture: Optional[float] = None, # [0.0..1.0] from vision (or None)
        measured_forces: Optional[Dict[str, float]] = None, # Measured grams per finger
        dt_s: float = 0.01,           # 100 Hz = 0.01s
    ) -> Dict[str, float]:
        """Execute one 100 Hz step of grip and motion execution.

        Returns:
            Dictionary of {servo_name: commanded_pulse_us}
        """
        # 1. Extract profile parameters
        closing_targets = profile_data.get("closing_target", {f: 0.85 for f in self.FINGERS})
        preshape_targets = profile_data.get("preshape", {f: 0.2 for f in self.FINGERS})
        force_target = float(profile_data.get("force_target_grams", 150.0))
        force_cap = float(profile_data.get("force_cap_grams", 300.0))
        close_speed = float(profile_data.get("close_speed", 0.5))

        commanded_pulses: Dict[str, float] = {}

        # 2. Update each finger
        for f in self.FINGERS:
            curr_pos = self.current_finger_positions[f]
            target_close = float(closing_targets.get(f, 0.85))
            target_preshape = float(preshape_targets.get(f, 0.2))
            meas_force = float(measured_forces.get(f, 0.0)) if measured_forces else 0.0

            if motion_command == "OPEN":
                # Opening runs at faster open_rate, ignores force targets
                step = self.open_rate * emg_velocity * dt_s if emg_velocity > 0 else self.open_rate * dt_s
                next_pos = max(0.0, curr_pos - step)
            elif motion_command == "CLOSE":
                # Closing is rate-limited and force-limited
                desired_pos = curr_pos + (target_close - curr_pos) * close_speed * emg_velocity * 0.1
                next_pos = self.force_controller.compute_finger_command(
                    finger_name=f,
                    current_pos=curr_pos,
                    target_pos=desired_pos,
                    measured_force=meas_force,
                    target_force=force_target,
                    force_cap=force_cap,
                    dt_s=dt_s,
                )
            else: # HOLD or MODE_CYCLE
                # Hold at current position, or adapt preshape aperture if opening wider
                if preshape_aperture is not None and preshape_aperture > 0 and preshape_aperture < curr_pos:
                    # Vision preshape can open the hand toward target, never close it
                    next_pos = max(preshape_aperture, curr_pos - self.open_rate * dt_s)
                else:
                    next_pos = curr_pos

            # Slew rate limit finger movement
            slewed_pos = self.slew_limiter.update(f, next_pos, dt_s)
            self.current_finger_positions[f] = slewed_pos

            # Map to clamped pulse
            pulse_us = self.mapper.normalized_to_pulse(f, slewed_pos)
            commanded_pulses[f] = pulse_us

            # Send through PWM arm gate
            servo_cal = self.mapper.servos.get(f)
            if servo_cal:
                self.gate.set_pulse_us(servo_cal.channel, pulse_us)

        # 3. Update Wrist and Forearm Joints
        wrist_hints = profile_data.get("wrist_hint_deg", {})
        for j in self.JOINTS:
            hint_key = j.replace("wrist_", "")
            target_deg = float(wrist_hints.get(hint_key, self.current_joint_angles[j]))

            slewed_deg = self.slew_limiter.update(j, target_deg, dt_s)
            self.current_joint_angles[j] = slewed_deg

            pulse_us = self.mapper.degrees_to_pulse(j, slewed_deg)
            commanded_pulses[j] = pulse_us

            servo_cal = self.mapper.servos.get(j)
            if servo_cal:
                self.gate.set_pulse_us(servo_cal.channel, pulse_us)

        return commanded_pulses
