# Component Specifications & Electrical Engineering Analysis

**Project**: Vision-Assisted Prosthetic Arm (VAPA)  
**Standard Compliance**: IEC 60601-1 (Medical Electrical Equipment: Basic Safety and Essential Performance), IPC-2152 (Current Carrying Capacity of Printed Board Design).

---

## 1. Power Distribution & Current Budget Analysis

### 1.1 Total System Current Calculations

The VAPA system operates nine mechanical actuators simultaneously with high-performance edge compute (NVIDIA Jetson Orin Nano) and real-time safety supervisory electronics (ESP32-WROOM-32E).

| Component | Operating Voltage | Idle / Running Current (A) | Peak / Stall Current (A) | Quantity | Total Peak Current (A) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **MG996R Analog Servo** (Fingers) | 6.0 V | 0.15 A / 0.80 A | 2.50 A | 5 | **12.50 A** |
| **DS3225 Digital Servo** (Wrist) | 6.0 V | 0.18 A / 0.95 A | 2.80 A | 3 | **8.40 A** |
| **DS3218 Digital Servo** (Forearm) | 6.0 V | 0.15 A / 0.85 A | 2.20 A | 1 | **2.20 A** |
| **NVIDIA Jetson Orin Nano** (15W Mode) | 5.0 V | 1.20 A / 2.50 A | 3.50 A | 1 | **3.50 A** (17.5 W peak) |
| **Intel RealSense D435i** (via USB 3.1) | 5.0 V (from Jetson) | 0.40 A / 0.70 A | 0.90 A | 1 | Included in Jetson |
| **ESP32-WROOM-32E** (Wi-Fi/BT Off) | 3.3 V | 0.08 A / 0.12 A | 0.25 A | 1 | **0.25 A** |
| **PCA9685 + TCA9548A + ADS1115** | 3.3 V | 0.01 A | 0.03 A | 3 | **0.03 A** |
| **AS5600 Encoders** (4x) | 3.3 V | 0.01 A | 0.02 A | 4 | **0.08 A** |
| **MyoWare 2.0 Sensors** (2x, Isolated) | 3.3 V_ISO | 0.01 A | 0.02 A | 2 | **0.04 A** |

### 1.2 Subsystem Rail Budget Summary

1. **Servo Rail A (Fingers 1–5)**:
   - Nominal Voltage: `6.0 V DC`
   - Continuous Grip Current: $5 \times 0.6\,\text{A} = 3.0\,\text{A}$
   - Simultaneous Stall Current: $5 \times 2.5\,\text{A} = 12.5\,\text{A}$
   - Rail Regulator: Synchronous Buck Regulator rated **15 A continuous, 20 A peak** (Pololu D36V50F6 / TI LM5145).
   - In-line Fuse: **15 A ATO Blade Fuse (F2)**.

2. **Servo Rail B (Wrist 3x + Forearm 1x)**:
   - Nominal Voltage: `6.0 V DC`
   - Continuous Movement Current: $4 \times 0.7\,\text{A} = 2.8\,\text{A}$
   - Simultaneous Stall Current: $(3 \times 2.8\,\text{A}) + (1 \times 2.2\,\text{A}) = 10.6\,\text{A}$
   - Rail Regulator: Synchronous Buck Regulator rated **15 A continuous, 20 A peak** (Pololu D36V50F6 / TI LM5145).
   - In-line Fuse: **15 A ATO Blade Fuse (F3)**.

3. **Logic Rail (Jetson + Sensors)**:
   - Nominal Voltage: `5.0 V DC`
   - Continuous Current: $2.5\,\text{A}$
   - Peak Current: $3.8\,\text{A}$
   - Rail Regulator: TI TPS54620 Synchronous Step-Down rated **6 A continuous, 7 A peak** (95% efficiency).
   - In-line Fuse: **6 A Resettable Polymeric PTC (F4)**.

4. **Main Battery Pack**:
   - Configuration: 3S Li-Ion / LiPo (11.1 V nominal, 12.6 V peak, 9.6 V cutoff) or 4S LiFePO4.
   - Recommended Capacity: $\ge 5200\,\text{mAh}$, continuous discharge rating $\ge 30\,\text{C}$ (150 A capability).
   - Main System Fuse: **30 A Fast-Acting Automotive Blade Fuse (F1)**.
   - Total System Max Stall Power:
     $$P_{\text{servos}} = (12.5\,\text{A} + 10.6\,\text{A}) \times 6.0\,\text{V} = 138.6\,\text{W}$$
     $$P_{\text{logic}} = 3.5\,\text{A} \times 5.0\,\text{V} = 17.5\,\text{W}$$
     $$P_{\text{total, peak}} \approx 156.1\,\text{W} \implies I_{\text{battery}} \approx \frac{156.1\,\text{W}}{11.1\,\text{V} \times 0.92} \approx 15.3\,\text{A}$$
   - Continuous battery current during vigorous continuous manipulation: **4.5 A to 6.2 A** ($\approx 50\text{--}65\,\text{W}$). Operating runtime on 5200 mAh pack: $\approx 50\text{--}70\,\text{minutes}$.

---

## 2. PCB Trace Width & Thermal Calculations (IPC-2152)

For internal/external copper traces on 2 oz/sq ft ($70\,\mu\text{m}$) copper PCB:

$$\text{Area} = \left(\frac{I}{k \times \Delta T^{0.44}}\right)^{\frac{1}{0.725}}$$

- For external traces ($k = 0.048$), maximum allowable temperature rise $\Delta T = 20^\circ\text{C}$:
  - **Main Battery Bus (30 A peak)**: Requires copper pour or AWG 12 silicone wire directly soldered to PDB.
  - **Servo Rails A & B (15 A peak)**: Requires trace width $\ge 6.8\,\text{mm}$ (270 mils) in 2 oz copper, or augmented by solder fill / busbar reinforcement.
  - **Ground Plane**: Solid internal plane on 4-layer board (Layer 2) dedicated to high-current return, with star point isolation to sensitive analog ground.

---

## 3. High-Side Emergency Power Isolation (E-Stop Circuit)

### 3.1 Architecture
The emergency stop mechanism isolates **both the logic PWM enable line and the raw high-current battery power rail** to eliminate all mechanical torque and runaway risks.

- **Switch**: IDEC AB6E-3BV01PRM Normally Closed (NC) red mushroom industrial safety switch.
- **Power Switch**: Infineon BTS50015-1TMA Smart High-Side Power Switch (PROFET).
  - Continuous Current Rating: $33\,\text{A}$ at $T_C = 85^\circ\text{C}$.
  - On-State Resistance: $R_{\text{DS(on)}} = 1.5\,\text{m}\Omega$ (dissipates only $0.35\,\text{W}$ at $15\,\text{A}$).
  - Integrated Protection: Over-temperature shutdown, short-circuit latch-off, reverse battery protection.
- **Fail-Safe Mechanism**: The NC contact holds the gate pull-down active. If the physical E-stop button is struck, or if the safety wire harness is severed, the circuit instantly drops gate bias, turning off the high-side MOSFET in $< 35\,\mu\text{s}$.
- Simultaneously, an optocoupled signal is asserted to ESP32 GPIO27, causing the FreeRTOS supervisor to pull PCA9685 `/OE` HIGH within $< 100\,\mu\text{s}$.

---

## 4. Biomedical Galvanic Isolation (IEC 60601-1 Type BF Compliance)

Prosthetic arms contact human skin via surface EMG electrodes. Placing user-worn electrodes in contact with an unisolated electrical system that carries 20A motor current presents severe safety risks (ground loops, electrical burns, and dangerous shock currents if battery ground faults occur).

### 4.1 Isolation Barrier Specifications
1. **Galvanic Voltage Rating**: $\ge 1500\,\text{V}_{\text{DC}}$ dielectric withstand.
2. **Coupling Capacitance**: $< 10\,\text{pF}$ (Mornsun B0505S-1WR3 achieves $2\,\text{pF}$).
3. **Leakage Current**: $< 10\,\mu\text{A}$ at $50/60\,\text{Hz}$ under Single Fault Condition (SFC).

### 4.2 Circuit Implementation
- **Isolated Power**: Mornsun B0505S-1WR3 generates an isolated 5.0 V rail (`VDD_ISO` / `GND_ISO`).
- **Clean Isolated Analog Power**: Texas Instruments TPS79333 low-noise LDO regulates `VDD_ISO` down to `3.3V_ISO` with $32\,\mu\text{V}_{\text{RMS}}$ noise floor to supply the MyoWare 2.0 sensors and ADS1115 ADC.
- **Digital Communication Isolation**: Texas Instruments ISO1540 bidirectional I2C digital isolator bridges the isolated I2C bus (`ADS1115` at 0x48) to the non-isolated ESP32 hardware I2C bus (`GPIO21/22`).
- **Electrode Contact Safety**: The user's forearm is only connected to `GND_ISO` through the MyoWare reference electrode. There is ZERO DC conductive path between the user and the main 12V battery ground.

---

## 5. Sensor Interface Engineering

### 5.1 FSR402 Force Sensing Resistors
- **Circuit**: Voltage divider with fixed $10.0\,\text{k}\Omega \pm 0.1\%$ 25ppm metal-film resistor connected between sensor terminal and clean 3.3V analog ground.
- **Filtering**: Parallel $0.1\,\mu\text{F}$ ceramic capacitor gives a low-pass cutoff frequency:
  $$f_c = \frac{1}{2\pi R_{\text{eq}} C} \approx \frac{1}{2\pi (5\,\text{k}\Omega)(0.1\,\mu\text{F})} \approx 318\,\text{Hz}$$
  This effectively attenuates 20 kHz PWM motor switching noise while preserving 100 Hz fingertip contact dynamics.
- **Clamping**: Littelfuse SP3002 TVS array clamps voltage spikes to $\le 3.6\,\text{V}$, preventing ESD damage to ESP32 ADC1 inputs.

### 5.2 AS5600 Magnetic Rotary Encoders & TCA9548A Multiplexer
- **Addressing**: All 4x AS5600 chips have fixed I2C address `0x36`.
- **Multiplexer**: TCA9548A routes the I2C bus to channels 0, 1, 2, 3. Address set to `0x71` ($A_0 = \text{VDD}, A_1 = \text{GND}, A_2 = \text{GND}$) to prevent collision with PCA9685 All-Call (`0x70`).
- **Magnets**: Diametrically magnetized Grade N52 neodymium discs placed with air gap $0.5\text{--}1.5\,\text{mm}$ from chip package. Status register `0x0B` monitored for `MD=1` (Magnet Detected), `ML=0` (Magnet Not Too Weak), `MH=0` (Magnet Not Too Strong).
