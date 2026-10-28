/**
 * VAPA ESP32 Sensor Ingestion & Safety Supervisor Firmware (Rev 2)
 */

#include <Arduino.h>
#include <Wire.h>
#include "protocol.h"
#include "supervisor.h"

// Hardware Pin Definitions (Rev 2)
#define PIN_PCA9685_OE 25   // Active LOW; drive HIGH immediately on boot
#define PIN_ESTOP      27   // INPUT_PULLUP; LOW = pressed
#define PIN_FSR_THUMB  32
#define PIN_FSR_INDEX  33
#define PIN_FSR_MID    34
#define PIN_FSR_RING   35
#define PIN_FSR_LITTLE 36
#define PIN_I2C_SDA    21
#define PIN_I2C_SCL    22
#define PIN_UART_TX    17
#define PIN_UART_RX    16

static supervisor_state_t g_supervisor;
static supervisor_config_t g_config = {
    .force_ceiling = 3500,
    .hb_timeout_ms = 250,
    .force_hold_ms = 100,
};

void setup() {
    // 1. FIRST THING ON BOOT: Disable PCA9685 outputs immediately
    pinMode(PIN_PCA9685_OE, OUTPUT);
    digitalWrite(PIN_PCA9685_OE, HIGH); // HIGH = all servo outputs disabled

    // 2. Configure E-stop pin
    pinMode(PIN_ESTOP, INPUT_PULLUP);

    // 3. Initialize supervisor state
    supervisor_init(&g_supervisor, &g_config);

    // 4. Initialize UART2 at 460800 baud
    Serial2.begin(460800, SERIAL_8N1, PIN_UART_RX, PIN_UART_TX);
}

void loop() {
    uint32_t now = millis();

    // Read E-Stop state (LOW = pressed)
    g_supervisor.estop_pressed = (digitalRead(PIN_ESTOP) == LOW);

    // Fast analog FSR reads (ADC1)
    uint16_t fsr[5];
    fsr[0] = analogRead(PIN_FSR_THUMB);
    fsr[1] = analogRead(PIN_FSR_INDEX);
    fsr[2] = analogRead(PIN_FSR_MID);
    fsr[3] = analogRead(PIN_FSR_RING);
    fsr[4] = analogRead(PIN_FSR_LITTLE);

    // Update supervisor logic
    supervisor_update(&g_supervisor, &g_config, now, fsr);

    // Update physical OE line (LOW = enabled, HIGH = disabled)
    if (g_supervisor.oe_enabled) {
        digitalWrite(PIN_PCA9685_OE, LOW);
    } else {
        digitalWrite(PIN_PCA9685_OE, HIGH);
    }

    delay(10); // Loop cadence
}
