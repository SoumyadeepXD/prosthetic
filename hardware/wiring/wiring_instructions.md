# VAPA Physical Harness Wiring & Assembly Instructions

**Document**: `hardware/wiring/wiring_instructions.md`  
**Audience**: Assembly Technicians, Hardware Engineers  
**Applies to**: VAPA Rev 2 Prototype Arm Harness

---

## 1. Required Tools, Materials & Wire Gauges

### 1.1 Wire Gauges (High-Flex Silicone Stranded Wire Only)
Never use solid-core wire on articulating prosthesis joints. Repeated bending causes work-hardening fatigue and intermittent failure.

| Wire Purpose | Gauge | Conductor Spec | Insulation | Max Current Rating |
| :--- | :--- | :--- | :--- | :--- |
| **Main Battery to PDB** | **AWG 12** | 680 strands, 0.08 mm tinned copper | Ultra-flex silicone | $30\,\text{A}$ continuous |
| **Servo Rails A & B Main Leads** | **AWG 16** | 252 strands, 0.08 mm tinned copper | Ultra-flex silicone | $15\,\text{A}$ continuous |
| **Individual Servo Power (Pigtails)**| **AWG 22** | 60 strands, 0.08 mm tinned copper | Ultra-flex silicone | $3\,\text{A}$ continuous |
| **5V Logic Supply to Jetson** | **AWG 20** | 100 strands, 0.08 mm tinned copper | Ultra-flex silicone | $5\,\text{A}$ continuous |
| **Analog Sensors (FSRs)** | **AWG 26** | 30 strands, 0.08 mm tinned copper | Ultra-flex silicone | Signal |
| **I2C Bus & Serial UART** | **AWG 28** | Shielded twisted pair (STP) | PVC / Silicone | High-frequency signal |
| **Isolated EMG Electrodes** | **AWG 26** | Shielded 3-conductor medical cable | Medical grade PVC | $< 10\,\mu\text{A}$ isolated |

### 1.2 Essential Tools
- Ratcheting crimpers: Engineer PA-09 / PA-20 (for JST-SH and Molex PicoBlade), IWISS IWS-2820M.
- XT60 soldering clamp and temperature-controlled iron ($\ge 60\,\text{W}$) with chisel tip.
- Adhesive-lined dual-wall polyolefin heat shrink tubing (3:1 shrink ratio).
- Braided expandable PET cable sleeving (3 mm, 6 mm, 10 mm diameters).
- Digital Multimeter with continuity buzzer and low-resistance four-wire Kelvin capability.

---

## 2. Step-by-Step Wiring & Assembly Procedures

### Step 1: Main Battery & E-Stop Interlock Assembly
1. **XT60 Assembly**: Solder AWG 12 silicone wire (Red for BAT+, Black for BAT-) to the XT60 connector. Slide heat shrink over each terminal prior to soldering.
2. **Main Fuse**: Splice the in-line ATO/ATC fuse holder into the positive BAT+ wire within $50\,\text{mm}$ of the XT60 plug. Insert a **30 A Littelfuse 0257030**.
3. **E-Stop Integration**: Route the BAT+ lead through the high-side PROFET power switch (`BTS50015-1TMA`). Wire the IDEC Normally Closed (NC) mushroom switch into the PROFET control gate and ESP32 optocoupler sensing terminal (`GPIO27`).
4. **Initial Verification**: Prior to connecting any downstream regulators, connect the 12V battery and verify with a multimeter:
   - With E-stop button depressed (pushed down): Output terminal measures $0.0\,\text{V}$.
   - With E-stop released (pulled up): Output terminal measures $11.1\text{--}12.6\,\text{V}$.

### Step 2: Power Distribution Board (PDB) & DC-DC Regulators
1. Mount the 5V logic buck converter and both 6V servo buck converters (Rail A and Rail B) onto the PDB.
2. Connect input terminals to the switched high-current bus from Step 1.
3. Install bulk decoupling capacitors ($2200\,\mu\text{F}$ 16V Low-ESR) directly across the screw terminals of each 6V servo rail.
4. Power on the PDB under no load:
   - Verify Rail A = $6.00\,\text{V} \pm 0.1\,\text{V}$.
   - Verify Rail B = $6.00\,\text{V} \pm 0.1\,\text{V}$.
   - Verify Logic Rail = $5.05\,\text{V} \pm 0.05\,\text{V}$.

### Step 3: Actuator Harness Fabrication
1. Cut servo leads to length for each finger (thumb, index, middle, ring, little).
2. Bundle the five finger servo cables into expandable braided sleeving.
3. Group the ground and power wires of Servos 1–5 onto the heavy-duty Rail A busbars.
4. Route the orange PWM signal wires into channels 0 to 4 of the PCA9685 3-pin headers.
5. Group the wrist servos (Servos 6–8) and forearm servo (Servo 9) onto Rail B. Route their PWM signal wires into channels 5 to 8 of the PCA9685 headers.

### Step 4: Magnetic Encoder Wiring (TCA9548A to AS5600)
1. Use 4-conductor shielded twisted-pair cables for each joint encoder.
2. Twist `SDA` with `GND`, and `SCL` with `3.3V` to minimize inductive cross-talk.
3. Crimp JST-SH 1.0 mm terminals onto both ends.
4. Secure the cable shield to the logic ground at the TCA9548A motherboard end ONLY (leave open at encoder end to avoid ground loops).
5. Ensure minimum bend radius $> 15\,\text{mm}$ across the wrist gimbal to prevent fatigue failure.

### Step 5: Isolated Biomedical EMG Wiring (IEC 60601-1)
1. Mount the Mornsun isolated DC-DC converter (`B0505S-1WR3`) and TI digital isolator (`ISO1540`) on the isolated barrier zone of the carrier board.
2. Maintain a minimum **4.0 mm creepage and clearance distance** on the PCB between `GND_LOGIC` and `GND_ISO`.
3. Connect the MyoWare 2.0 sensor cables using dedicated shielded twisted 3-wire assemblies.
4. Verify with a high-voltage insulation tester (Megger) that the resistance between `GND_ISO` and `GND_BATTERY` exceeds $> 100\,\text{M}\Omega$ at $500\,\text{V}_{\text{DC}}$.

### Step 6: Fingertip FSR Force Sensor Routing
1. Solder AWG 26 ultra-flex silicone wires to the FSR 402 solder tabs using low-temperature solder ($< 250^\circ\text{C}$ for $< 2\,\text{seconds}$) to prevent melting the polyester substrate.
2. Reinforce the solder joints with dual-wall adhesive heat shrink.
3. Route wires down the dorsal side of each finger link through internal wire guides.
4. Connect to the PDB 2-pin Molex PicoBlade headers where the $10\,\text{k}\Omega$ precision pull-down and $0.1\,\mu\text{F}$ filtering caps are located.

---

## 3. Pre-Power Safety Checklist (Mandatory)

Before applying battery power for the first time:

- [ ] Continuity check: Verify ZERO continuity between `12V_BAT+` and `GND` (no short circuit).
- [ ] Continuity check: Verify ZERO continuity between `6V_SERVO_A`, `6V_SERVO_B`, `5V_LOGIC`, and `GND`.
- [ ] Isolation check: Verify ZERO continuity between `GND_ISO` (EMG) and `GND_BATTERY`.
- [ ] Polarity check: Confirm XT60 connector has Red to square terminal (+), Black to chamfer terminal (-).
- [ ] Fuse verification: Confirm 30A fuse in F1, 15A fuse in F2, 15A fuse in F3.
- [ ] E-stop operation: Depress E-stop; verify mechanical latch locks positively into open circuit.
- [ ] PCA9685 OE: Verify 10k pull-up resistor to 3.3V is installed on pin 23 (/OE).
