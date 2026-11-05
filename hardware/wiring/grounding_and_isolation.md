# Grounding Architecture & Galvanic Isolation Strategy

**Document**: `hardware/wiring/grounding_and_isolation.md`  
**Classification**: Electrical & Biomedical Safety Standard  
**Compliance Standard**: IEC 60601-1 (Medical electrical equipment — General requirements for basic safety and essential performance)

---

## 1. The Ground Bounce & High-Current Problem

In an articulated robotic prosthesis actuating nine high-torque servos:
- Peak stall current reaches **23.1 A** across the dual 6V rails.
- PWM switching at 50 Hz with micro-second rise times produces slew rates exceeding:
  $$\frac{dI}{dt} \approx \frac{10\,\text{A}}{1\,\mu\text{s}} = 10^7\,\text{A/s}$$
- Even across a microscopic PCB trace or wiring harness resistance of just $15\,\text{m}\Omega$ and inductance of $25\,\text{nH}$:
  $$V_{\text{bounce}} = I \cdot R + L \cdot \frac{dI}{dt} = (10 \times 0.015) + (25 \times 10^{-9} \times 10^7) = 0.15\,\text{V} + 0.25\,\text{V} = \mathbf{0.40\,\text{V}}$$

If sensitive analog sensors (FSRs, EMG electrodes) or digital logic chips (ESP32, Jetson) share this return path, this 400 mV ground bounce causes:
1. False E-stop trips and watchdog panics.
2. Severely corrupted ADC readings.
3. I2C bus lockups due to SCL/SDA voltage levels dipping below $V_{IL}$ ($0.3 \times V_{DD} \approx 0.99\,\text{V}$).
4. Severe electrical safety and noise injection hazard for the prosthetic user.

---

## 2. Three-Zone Grounding Topology (Star Architecture)

To completely eliminate common-impedance coupling, the VAPA electrical architecture divides grounds into **three strictly segregated domains**:

```
+-----------------------------------------------------------------------------------------+
|                                    12V LI-ION BATTERY                                   |
+-----------------------------------------------------------------------------------------+
                                             |
                         [STAR GROUND POINT / MAIN PDB SHUNT]
                                             |
         +-----------------------------------+-----------------------------------+
         |                                                                       |
+--------------------------+                                           +--------------------------+
|      ZONE 1: POWER       |                                           |      ZONE 2: LOGIC       |
|    High-Current Return   |                                           |     Clean Digital/Analog |
+--------------------------+                                           +--------------------------+
| - Servo Rail A (15A max) |                                           | - Jetson Orin Nano (5V)  |
| - Servo Rail B (15A max) |                                           | - ESP32-WROOM-32E (3.3V) |
| - High-Side PROFET GND   |                                           | - PCA9685 Logic Core     |
| - Decoupling Caps (4x)   |                                           | - TCA9548A Mux & AS5600s |
+--------------------------+                                           | - FSR Voltage Dividers   |
                                                                       +--------------------------+
                                                                                     |
                                                                        [1.5 kV ISOLATION BARRIER]
                                                                        (Mornsun B0505S + ISO1540)
                                                                                     |
                                                                       +--------------------------+
                                                                       |    ZONE 3: BIOMEDICAL    |
                                                                       |     IEC 60601-1 Isolated |
                                                                       +--------------------------+
                                                                       | - MyoWare 2.0 Sensors    |
                                                                       | - Forearm Skin Contact   |
                                                                       | - Isolated ADS1115 ADC   |
                                                                       | - 3.3V_ISO Analog Rail   |
                                                                       +--------------------------+
```

### 2.1 Zone 1: Power Ground (`GND_POWER`)
- Dedicated to high-current inductive return from the nine servo motors and buck converter output stages.
- Formed by a dedicated heavy copper pour on the bottom layer of the PDB (or external AWG 16/12 bus wires).
- Directly connects back to the negative terminal of the XT60 battery connector.
- High-frequency bulk decoupling capacitors ($2200\,\mu\text{F}$ 16V low-ESR) are positioned physically adjacent to the servo power pins so current loops close locally within millimeters, rather than traversing the entire harness.

### 2.2 Zone 2: System Logic Ground (`GND_LOGIC`)
- Dedicated to digital computing (NVIDIA Jetson, ESP32, PCA9685 logic, TCA9548A multiplexer) and non-body sensors (AS5600 encoders, FSRs).
- Meets `GND_POWER` at exactly **ONE single physical star point** on the PDB adjacent to the battery connector.
- No servo return currents ever flow through the `GND_LOGIC` plane.

### 2.3 Zone 3: Biomedical Isolated Ground (`GND_ISO`)
- Strictly dedicated to user-worn surface EMG electrodes and the ADS1115 ADC.
- Has **ZERO ohmic, galvanic, or capacitive return path** to `GND_LOGIC` or `GND_POWER`.
- Complies with **IEC 60601-1 Type BF (Body Floating)** electrical safety requirements.
- Any fault in the motor power train (e.g. 12V battery shorted to arm chassis) cannot conduct into the patient's forearm.

---

## 3. Biomedical Galvanic Isolation Specifications (IEC 60601-1)

| Parameter | Specification | Measured / Implemented Value | Verification Standard |
| :--- | :--- | :--- | :--- |
| **Isolation Voltage** | $\ge 1500\,\text{V}_{\text{AC}} / 2121\,\text{V}_{\text{DC}}$ | $2500\,\text{V}_{\text{RMS}}$ (ISO1540), $1500\,\text{V}_{\text{DC}}$ (B0505S) | IEC 60601-1 Clause 8.8 |
| **Creepage Distance** | $\ge 4.0\,\text{mm}$ (Material Grp III) | $5.5\,\text{mm}$ physical copper-to-copper gap on PCB | IEC 60601-1 Table 12 |
| **Clearance Distance** | $\ge 2.5\,\text{mm}$ | $4.8\,\text{mm}$ air gap | IEC 60601-1 Table 12 |
| **Coupling Capacitance** | $\le 10\,\text{pF}$ | $2.2\,\text{pF}$ total barrier capacitance | Low 50/60 Hz displacement current |
| **Patient Leakage Current** | $\le 100\,\mu\text{A}$ (Normal), $\le 500\,\mu\text{A}$ (SFC) | $< 2.0\,\mu\text{A}$ at $240\,\text{V}_{\text{AC}} / 50\,\text{Hz}$ | IEC 60601-1 Clause 8.7.4 |

### 3.1 Digital Bus Isolation Implementation
- The I2C bus between ESP32 and ADS1115 is digitally isolated by a **Texas Instruments ISO1540**.
- Side 1 (Logic): Connected to ESP32 `GPIO21` (SDA) and `GPIO22` (SCL) with 4.7k pull-ups to `3V3_ESP`.
- Side 2 (Isolated): Connected to ADS1115 `SDA` and `SCL` with 4.7k pull-ups to `3V3_ISO`.
- Ground Isolation: `GND1` connects to `GND_LOGIC`; `GND2` connects to `GND_ISO`.

---

## 4. Cable Shielding & Noise Rejection Rules

1. **Single-Point Shield Grounding**:
   All shielded cables (AS5600 encoder STP cables, MyoWare electrode leads) must have their outer braided shield grounded at **one end only** (the motherboard controller end).
   *Reason*: Grounding both ends creates a closed conductive loop that acts as a magnetic pick-up antenna for high-current servo PWM radiation.

2. **Twisted-Pair Signal Routing**:
   - Every high-speed digital or analog differential line must be twisted with its corresponding reference ground.
   - I2C SDA and SCL are paired with `GND_LOGIC` (twist rate $\ge 30\,\text{twists/meter}$).
   - Motor power pairs (6V and `GND_POWER`) are twisted together to cancel emitted electromagnetic fields ($B \propto I / r$).

3. **ESD Protection (Electrostatic Discharge)**:
   - All external fingertips contact real-world objects and accumulate static charge (triboelectric effect).
   - Each FSR signal input on the carrier board has an ultra-low capacitance bidirectional TVS diode (Littelfuse SP3002) connected between the signal line and `GND_LOGIC`.
   - Rated for $\pm 15\,\text{kV}$ air discharge and $\pm 8\,\text{kV}$ contact discharge per IEC 61000-4-2.
