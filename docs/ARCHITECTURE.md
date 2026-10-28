# VAPA System Architecture (Rev 2)

## 1. System Overview
VAPA is a vision-assisted prosthetic arm controlled via an autonomous dual-processor architecture:
1. **ESP32-WROOM-32**: Dedicated hard real-time sensor ingestion, watchdog supervisor, and hardware output gating.
2. **Jetson Orin Nano**: High-level perception, EMG feature decoding, vision processing, closed-loop trajectory planning, and operator UI.

```
+----------------------------------------------------------------------------------+
|                              Jetson Orin Nano                                    |
|                                                                                  |
|  [RealSense D435i] --> [Vision Process] --(Distance Matrix, Class)--> [Fusion]  |
|                                                                          ^       |
|  [ESP Link Task] ----> [Decoder Process] --(Activation Intent)-----------+       |
|                                                                          |       |
|  [Safety Machine] <--> [Heartbeat (50Hz)]                           [Controller] |
|        |                                                                 |       |
|  [Arm Gate] <------------------------------------------------------------+       |
|        |                                                                         |
|        v                                                                         |
|  [PCA9685 HAL] --(I2C: /dev/i2c-7)--> PCA9685 (0x40) ----+                       |
|  [AS5600 HAL]  --(I2C: /dev/i2c-7)--> TCA9548A (0x71)    |                       |
+--------------------------------------------|-------------|-----------------------+
                     UART2 (460800 baud)     |             |
                                             v             | PWM Signals
+-------------------------------------------------------+  |
|                    ESP32-WROOM-32                     |  |
|                                                       |  |
|  - ADS1115 (0x48): MyoWare ENV (A0, A1), EEG (A2)     |  |
|  - FSR 1..5: GPIO 32-36 (ADC1)                        |  |
|  - E-Stop NO: GPIO27 (Input Pullup, Active LOW)       |  |
|  - Watchdog & Safety Supervisor                       |  |
|  - GPIO25: PCA9685 Output Enable (OE) ----------------+--+--> PCA9685 / Servos
+-------------------------------------------------------+
```

## 2. Hardware Allocation

### ESP32-WROOM-32 Pin Map
- **GPIO25:** PCA9685 Output Enable (`OE`). Active LOW. Pulled HIGH via 1k resistor. Boot default = HIGH.
- **GPIO27:** Emergency Stop contact. `INPUT_PULLUP`. Low = Active / Pressed.
- **GPIO32-36:** FSR Analog Inputs (ADC1 only). Thumb, Index, Middle, Ring, Little. Higher ADC counts = higher force.
- **GPIO21/22:** I2C SDA/SCL connected to ADS1115 (`0x48`).
  - A0: Flexor EMG Envelope
  - A1: Extensor EMG Envelope
  - A2: EEG Analog Signal (experimental)
  - A3: Spare
- **GPIO16/17:** UART2 RX2/TX2 connected to Jetson UART header.

### Jetson Orin Nano Pin Map
- **I2C Bus (`/dev/i2c-7`):**
  - Pin 3 (SDA), Pin 5 (SCL)
  - `0x40`: PCA9685 PWM Driver (50 Hz). `ALLCALL` disabled.
  - `0x71`: TCA9548A I2C Multiplexer (A0 tied to 3.3V).
    - Port 0: AS5600 Finger group encoder (`0x36`)
    - Port 1: AS5600 Wrist flex encoder (`0x36`)
    - Port 2: AS5600 Wrist rotate encoder (`0x36`)
    - Port 3: AS5600 Forearm rotation encoder (`0x36`)
    - Port 4: Reserved for 5th encoder
- **UART2:**
  - Pin 8 (TXD), Pin 10 (RXD) connected cross-wired to ESP32 UART2.
- **USB3:** Intel RealSense D435i.
- **HDMI:** 5-inch 800x480 status display.

### Servo Channel Assignment (PCA9685)
- Channels 0-4: MG996R (Fingers 1 to 5)
- Channel 5: DS3225 (Wrist Flex)
- Channel 6: DS3225 (Wrist Rotate)
- Channel 7: DS3225 (Wrist Bend, open-loop)
- Channel 8: DS3218 (Forearm Rotation)
- Channels 9-15: Reserved
