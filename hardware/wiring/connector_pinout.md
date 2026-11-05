# VAPA Hardware Connector Pinout Specification (Rev 2)

**Document**: `hardware/wiring/connector_pinout.md`  
**Revision**: 2.1 (Production Baseline)

---

## 1. NVIDIA Jetson Orin Nano 40-Pin Header

The Jetson Orin Nano connects to the VAPA carrier motherboard via its standard 40-pin GPIO header.

| Pin Number | Signal Name | Direction | Connected To | Voltage Level | Wire Color | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Pin 2** | `5V_IN` | Power Input | PDB 5V / 6A Buck Converter | 5.0 V DC ($\pm 3\%$) | **RED** | High-current logic supply |
| **Pin 4** | `5V_IN` | Power Input | PDB 5V / 6A Buck Converter | 5.0 V DC ($\pm 3\%$) | **RED** | Paralleled with Pin 2 for 4A capability |
| **Pin 6** | `GND` | Ground | System Logic Ground (GND_LOGIC) | 0.0 V | **BLACK** | Star-ground return |
| **Pin 3** | `I2C_SDA` | Bidirectional | TCA9548A (0x71) & PCA9685 (0x40) | 3.3 V Logic | **GREEN** | Jetson I2C Bus 7 (400 kHz) |
| **Pin 5** | `I2C_SCL` | Bidirectional | TCA9548A (0x71) & PCA9685 (0x40) | 3.3 V Logic | **YELLOW** | Jetson I2C Bus 7 (400 kHz) |
| **Pin 8** | `UART1_TXD` | Output | ESP32 GPIO16 (`UART2_RX2`) | 3.3 V CMOS | **ORANGE** | 460800 baud binary telemetry |
| **Pin 10** | `UART1_RXD` | Input | ESP32 GPIO17 (`UART2_TX2`) | 3.3 V CMOS | **BLUE** | 460800 baud binary telemetry |
| **Pin 9** | `GND` | Ground | ESP32 Digital Ground | 0.0 V | **BLACK** | Serial signal reference return |

---

## 2. ESP32-WROOM-32 Pin Allocations

| GPIO Pin | Pin Type | Direction | Net / Connection | Safe Boot State | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **GPIO25** | Digital Output | Output | `PCA9685_OE` | **HIGH (Disabled)** | Active-LOW Output Enable. Driven HIGH immediately at boot. Pulled up to 3.3V with 10k resistor. |
| **GPIO27** | Digital Input | Input | `ESTOP_SENSE` | Pull-up Enabled | Reads LOW when Emergency Stop is activated. Optocoupled to physical E-stop switch. |
| **GPIO21** | Open Drain | Bidirectional | `I2C_SDA_LOCAL` | High-Z | Fast I2C Bus to ISO1540 (Isolated ADS1115). 4.7k pull-up to 3.3V. |
| **GPIO22** | Open Drain | Output | `I2C_SCL_LOCAL` | High-Z | Fast I2C Clock to ISO1540 (Isolated ADS1115). 4.7k pull-up to 3.3V. |
| **GPIO16** | Digital Input | Input | `UART2_RX2` | High-Z | Serial RX from Jetson Pin 8 (TXD). 460800 baud. |
| **GPIO17** | Digital Output | Output | `UART2_TX2` | Driven | Serial TX to Jetson Pin 10 (RXD). 460800 baud. |
| **GPIO32** | Analog ADC1_4 | Input | `FSR_THUMB` | Analog Input | Voltage divider from FSR402 Thumb (10k pull-down). |
| **GPIO33** | Analog ADC1_5 | Input | `FSR_INDEX` | Analog Input | Voltage divider from FSR402 Index (10k pull-down). |
| **GPIO34** | Analog ADC1_6 | Input | `FSR_MIDDLE` | Analog Input | Voltage divider from FSR402 Middle (10k pull-down, Input Only). |
| **GPIO35** | Analog ADC1_7 | Input | `FSR_RING` | Analog Input | Voltage divider from FSR402 Ring (10k pull-down, Input Only). |
| **GPIO36 (VP)**| Analog ADC1_0 | Input | `FSR_LITTLE` | Analog Input | Voltage divider from FSR402 Little (10k pull-down, Input Only). |
| **3V3** | Power | Input | `3V3_ESP` | Power | Powered from dedicated low-noise AP2112K LDO (600mA). |
| **GND** | Ground | Ground | `GND_LOGIC` | Ground | Connected to common logic ground plane. |

---

## 3. PCA9685 16-Channel PWM Servo Controller

| Header | Channel | Actuator Name | Servo Model | Power Rail | Pulse Range | Wire Colors (GND / V+ / SIG) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **J1** | CH 0 | **Thumb Flexion** | MG996R | Servo Rail A (6V) | 650 – 2350 $\mu\text{s}$ | Brown / Red / Orange |
| **J2** | CH 1 | **Index Flexion** | MG996R | Servo Rail A (6V) | 650 – 2350 $\mu\text{s}$ | Brown / Red / Orange |
| **J3** | CH 2 | **Middle Flexion** | MG996R | Servo Rail A (6V) | 650 – 2350 $\mu\text{s}$ | Brown / Red / Orange |
| **J4** | CH 3 | **Ring Flexion** | MG996R | Servo Rail A (6V) | 650 – 2350 $\mu\text{s}$ | Brown / Red / Orange |
| **J5** | CH 4 | **Little Flexion** | MG996R | Servo Rail A (6V) | 650 – 2350 $\mu\text{s}$ | Brown / Red / Orange |
| **J6** | CH 5 | **Wrist Flexion/Extension** | DS3225 | Servo Rail B (6V) | 500 – 2500 $\mu\text{s}$ | Black / Red / White |
| **J7** | CH 6 | **Wrist Pronation/Supination**| DS3225 | Servo Rail B (6V) | 500 – 2500 $\mu\text{s}$ | Black / Red / White |
| **J8** | CH 7 | **Wrist Radial/Ulnar Deviation** | DS3225 | Servo Rail B (6V) | 500 – 2500 $\mu\text{s}$ | Black / Red / White |
| **J9** | CH 8 | **Forearm Rotation** | DS3218 | Servo Rail B (6V) | 500 – 2500 $\mu\text{s}$ | Black / Red / White |
| **J10-J16**| CH 9–15| Reserved Expansion | N/A | Servo Rail B (6V) | Unassigned | Unpopulated / Reserved |

---

## 4. TCA9548A I2C Multiplexer & AS5600 Magnetic Encoders

All encoder connections use 4-pin JST-SH (1.0 mm pitch) shielded cables.

| Connector | Mux Channel | Joint Name | Sensor Type | Net Names (Pin 1 to 4) | Wire Colors |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ENC_FING** | Channel 0 | `finger_group` (Tendon Spool) | AS5600 (0x36) | `3V3_LOGIC`, `GND_LOGIC`, `SCL_CH0`, `SDA_CH0` | Red, Black, Yellow, Green |
| **ENC_WFLEX**| Channel 1 | `wrist_flex` (Wrist Pitch) | AS5600 (0x36) | `3V3_LOGIC`, `GND_LOGIC`, `SCL_CH1`, `SDA_CH1` | Red, Black, Yellow, Green |
| **ENC_WROT** | Channel 2 | `wrist_rotate` (Wrist Roll) | AS5600 (0x36) | `3V3_LOGIC`, `GND_LOGIC`, `SCL_CH2`, `SDA_CH2` | Red, Black, Yellow, Green |
| **ENC_FARM** | Channel 3 | `forearm_rotation` (Forearm) | AS5600 (0x36) | `3V3_LOGIC`, `GND_LOGIC`, `SCL_CH3`, `SDA_CH3` | Red, Black, Yellow, Green |
| **ENC_RESV** | Channel 4 | `wrist_bend_reserved` | AS5600 (0x36) | `3V3_LOGIC`, `GND_LOGIC`, `SCL_CH4`, `SDA_CH4` | Red, Black, Yellow, Green |

---

## 5. Isolated Biomedical EMG Interface (IEC 60601-1)

All EMG connectors use 3-pin JST-XH (2.54 mm pitch) connectors completely isolated from chassis/battery ground.

| Connector | Signal Name | Pin 1 | Pin 2 | Pin 3 | Target Destination |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **J_EMG1** | Flexor Carpi Radialis | `3.3V_ISO` (Red) | `GND_ISO` (Black) | `EMG1_ENV` (Blue) | ADS1115 Analog Input A0 |
| **J_EMG2** | Extensor Digitorum | `3.3V_ISO` (Red) | `GND_ISO` (Black) | `EMG2_ENV` (Blue) | ADS1115 Analog Input A1 |
| **J_EEG_AUX**| Auxiliary / Cranial | `3.3V_ISO` (Red) | `GND_ISO` (Black) | `EEG_AUX` (White) | ADS1115 Analog Input A2 |

---

## 6. FSR402 Fingertip Force Sensor Headers

Connectors: 2-pin Molex PicoBlade (1.25 mm pitch) located at each distal phalanx fingertip.

| Connector | Finger | Pin 1 | Pin 2 | ESP32 ADC1 Pin |
| :--- | :--- | :--- | :--- | :--- |
| **J_FSR1** | Thumb | `3V3_LOGIC` | `FSR_SIG_THUMB` | GPIO32 |
| **J_FSR2** | Index | `3V3_LOGIC` | `FSR_SIG_INDEX` | GPIO33 |
| **J_FSR3** | Middle | `3V3_LOGIC` | `FSR_SIG_MIDDLE` | GPIO34 |
| **J_FSR4** | Ring | `3V3_LOGIC` | `FSR_SIG_RING` | GPIO35 |
| **J_FSR5** | Little | `3V3_LOGIC` | `FSR_SIG_LITTLE` | GPIO36 |
