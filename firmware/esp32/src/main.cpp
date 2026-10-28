/**
 * VAPA ESP32 Sensor Ingestion & Safety Supervisor Firmware (Rev 2)
 *
 * Implements:
 * - Independent FreeRTOS supervisor controlling PCA9685 OE (GPIO25).
 * - Multi-task architecture with hardware task watchdog.
 * - ADS1115 (0x48) round-robin envelope sampling (A0, A1, A2).
 * - 5x FSR402 ADC1 sampling (GPIO32-36) with median-of-3 + EMA filter.
 * - Hardware E-stop monitoring on GPIO27 with immediate OE drop.
 * - Binary framing at 460800 baud (100 Hz SENSOR, 2 Hz STATUS).
 */

#include <Arduino.h>
#include <Wire.h>
#include <esp_task_wdt.h>
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

// Protocol and timing constants
#define FW_VERSION 0x0200
#define SENSOR_INTERVAL_MS 10   // 100 Hz
#define STATUS_INTERVAL_MS 500  // 2 Hz
#define WATCHDOG_TIMEOUT_S 2

// ADS1115 Address and Registers
#define ADS1115_ADDR 0x48
#define ADS_REG_CONV 0x00
#define ADS_REG_CFG  0x01

// Global Supervisor State and Config (protected by mutex)
static supervisor_state_t g_supervisor;
static supervisor_config_t g_config = {
    .force_ceiling = 3500,
    .hb_timeout_ms = 250,
    .force_hold_ms = 100,
};

static SemaphoreHandle_t g_data_mutex = NULL;
static uint16_t g_shared_emg[2] = {0, 0};
static uint16_t g_shared_eeg = 0;
static uint16_t g_shared_fsr[5] = {0, 0, 0, 0, 0};
static bool g_shared_ads_ok = false;
static uint16_t g_rx_err_count = 0;
static uint16_t g_ads_err_count = 0;
static uint8_t g_tx_seq = 0;

// Immediate OE control helper
static inline void set_hardware_oe(bool enable) {
    if (enable) {
        digitalWrite(PIN_PCA9685_OE, LOW); // LOW = Enabled
    } else {
        digitalWrite(PIN_PCA9685_OE, HIGH); // HIGH = Disabled
    }
}

// Simple non-blocking ADS1115 single-ended read
static bool ads1115_read_channel(uint8_t channel, uint16_t *out_val) {
    if (channel > 3) return false;

    // Config: OS=1 (start single conv), MUX=channel vs GND, PGA=4.096V (001), MODE=single (1), DR=860SPS (111)
    uint16_t mux_bits = (0x04 | channel) << 12;
    uint16_t config = 0x8000 | mux_bits | 0x0200 | 0x0100 | 0x00E0 | 0x0003;

    Wire.beginTransmission(ADS1115_ADDR);
    Wire.write(ADS_REG_CFG);
    Wire.write((uint8_t)(config >> 8));
    Wire.write((uint8_t)(config & 0xFF));
    if (Wire.endTransmission() != 0) {
        return false;
    }

    // Wait ~1.2ms for 860 SPS conversion
    delayMicroseconds(1200);

    Wire.beginTransmission(ADS1115_ADDR);
    Wire.write(ADS_REG_CONV);
    if (Wire.endTransmission() != 0) {
        return false;
    }

    if (Wire.requestFrom((uint8_t)ADS1115_ADDR, (uint8_t)2) != 2) {
        return false;
    }

    uint16_t raw = (Wire.read() << 8) | Wire.read();
    // Clip negative differential values
    if ((int16_t)raw < 0) raw = 0;
    *out_val = raw;
    return true;
}

// Median of 3 helper
static inline uint16_t median_of_3(uint16_t a, uint16_t b, uint16_t c) {
    if ((a <= b && b <= c) || (c <= b && b <= a)) return b;
    if ((b <= a && a <= c) || (c <= a && a <= b)) return a;
    return c;
}

/**
 * FreeRTOS Task 1: Sensor Sampling Task (Priority 2)
 */
void SensorSamplingTask(void *pvParameters) {
    esp_task_wdt_add(NULL);

    static uint16_t fsr_history[5][3] = {{0}};
    static float fsr_ema[5] = {0};
    uint8_t sample_idx = 0;

    for (;;) {
        esp_task_wdt_reset();

        // 1. Read FSRs (ADC1 on ESP32: GPIO32-36)
        uint16_t raw_fsr[5];
        raw_fsr[0] = analogRead(PIN_FSR_THUMB);
        raw_fsr[1] = analogRead(PIN_FSR_INDEX);
        raw_fsr[2] = analogRead(PIN_FSR_MID);
        raw_fsr[3] = analogRead(PIN_FSR_RING);
        raw_fsr[4] = analogRead(PIN_FSR_LITTLE);

        // Filter FSRs: Median of 3 then Exponential Moving Average (EMA)
        uint16_t filtered_fsr[5];
        for (int i = 0; i < 5; ++i) {
            fsr_history[i][sample_idx] = raw_fsr[i];
            uint16_t med = median_of_3(fsr_history[i][0], fsr_history[i][1], fsr_history[i][2]);
            fsr_ema[i] = 0.6f * med + 0.4f * fsr_ema[i];
            filtered_fsr[i] = (uint16_t)fsr_ema[i];
        }
        sample_idx = (sample_idx + 1) % 3;

        // 2. Read ADS1115 round-robin: A0 (Flex), A1 (Ext), A2 (EEG)
        uint16_t emg[2] = {0, 0};
        uint16_t eeg = 0;
        bool ads_ok = true;

        if (!ads1115_read_channel(0, &emg[0])) ads_ok = false;
        if (!ads1115_read_channel(1, &emg[1])) ads_ok = false;
        if (!ads1115_read_channel(2, &eeg)) ads_ok = false;

        if (!ads_ok) {
            g_ads_err_count++;
            // Immediate safety reaction: ADS fault disables OE immediately
            set_hardware_oe(false);
        }

        // 3. Fast E-stop check in sensor task
        if (digitalRead(PIN_ESTOP) == LOW) {
            set_hardware_oe(false);
        }

        // 4. Update shared data
        if (xSemaphoreTake(g_data_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            g_shared_emg[0] = emg[0];
            g_shared_emg[1] = emg[1];
            g_shared_eeg = eeg;
            for (int i = 0; i < 5; ++i) g_shared_fsr[i] = filtered_fsr[i];
            g_shared_ads_ok = ads_ok;
            xSemaphoreGive(g_data_mutex);
        }

        vTaskDelay(pdMS_TO_TICKS(5)); // High rate sampling cadence
    }
}

/**
 * FreeRTOS Task 2: Supervisor & Communication Task (Priority 3)
 */
void SupervisorUartTask(void *pvParameters) {
    esp_task_wdt_add(NULL);

    frame_parser_t parser;
    frame_parser_init(&parser);

    uint32_t last_sensor_tx_ms = 0;
    uint32_t last_status_tx_ms = 0;
    uint8_t tx_buffer[64];

    for (;;) {
        esp_task_wdt_reset();
        uint32_t now = millis();

        // 1. Process UART incoming bytes
        while (Serial2.available() > 0) {
            uint8_t b = Serial2.read();
            uint8_t msg_type = 0;
            uint8_t seq = 0;
            const uint8_t *payload = NULL;
            uint8_t len = 0;

            if (frame_parser_feed(&parser, b, &msg_type, &seq, &payload, &len)) {
                if (msg_type == MSG_TYPE_HEARTBEAT && len == 2) {
                    const heartbeat_payload_t *hb = (const heartbeat_payload_t *)payload;
                    supervisor_process_heartbeat(&g_supervisor, hb->arm_request, now);
                } else if (msg_type == MSG_TYPE_CONFIG && len == 6) {
                    const config_payload_t *cfg = (const config_payload_t *)payload;
                    g_config.force_ceiling = cfg->force_ceiling;
                    g_config.hb_timeout_ms = cfg->hb_timeout_ms;
                    g_config.force_hold_ms = cfg->force_hold_ms;
                    // Reply ACK
                    ack_nack_payload_t ack = {.ref_type = MSG_TYPE_CONFIG, .ref_seq = seq, .code = 0};
                    size_t enc_len = frame_encode(MSG_TYPE_ACK_NACK, g_tx_seq++, (const uint8_t *)&ack, sizeof(ack), tx_buffer, sizeof(tx_buffer));
                    Serial2.write(tx_buffer, enc_len);
                } else if (msg_type == MSG_TYPE_CLEAR_FAULT && len == 0) {
                    bool cleared = supervisor_clear_fault(&g_supervisor);
                    ack_nack_payload_t ack = {
                        .ref_type = MSG_TYPE_CLEAR_FAULT,
                        .ref_seq = seq,
                        .code = (uint8_t)(cleared ? 0 : 1)
                    };
                    size_t enc_len = frame_encode(MSG_TYPE_ACK_NACK, g_tx_seq++, (const uint8_t *)&ack, sizeof(ack), tx_buffer, sizeof(tx_buffer));
                    Serial2.write(tx_buffer, enc_len);
                }
            }
        }
        g_rx_err_count = parser.crc_errors;

        // 2. Read E-Stop (LOW = pressed)
        g_supervisor.estop_pressed = (digitalRead(PIN_ESTOP) == LOW);
        if (g_supervisor.estop_pressed) {
            set_hardware_oe(false); // Immediate physical drop
        }

        // 3. Retrieve latest sensor data snapshot
        uint16_t local_emg[2] = {0};
        uint16_t local_eeg = 0;
        uint16_t local_fsr[5] = {0};
        bool local_ads_ok = false;

        if (xSemaphoreTake(g_data_mutex, pdMS_TO_TICKS(2)) == pdTRUE) {
            local_emg[0] = g_shared_emg[0];
            local_emg[1] = g_shared_emg[1];
            local_eeg = g_shared_eeg;
            for (int i = 0; i < 5; ++i) local_fsr[i] = g_shared_fsr[i];
            local_ads_ok = g_shared_ads_ok;
            xSemaphoreGive(g_data_mutex);
        }

        // 4. Update Supervisor State Machine
        supervisor_update(&g_supervisor, &g_config, now, local_fsr, local_ads_ok);

        // 5. Update physical PCA9685 OE line
        set_hardware_oe(g_supervisor.oe_enabled);

        // 6. Transmit 100 Hz SENSOR packet
        if (now - last_sensor_tx_ms >= SENSOR_INTERVAL_MS) {
            last_sensor_tx_ms = now;

            sensor_payload_t s_msg;
            s_msg.t_ms = now;
            s_msg.emg[0] = local_emg[0];
            s_msg.emg[1] = local_emg[1];
            s_msg.eeg = local_eeg;
            for (int i = 0; i < 5; ++i) s_msg.fsr[i] = local_fsr[i];
            s_msg.flags = supervisor_get_flags(&g_supervisor);

            size_t enc_len = frame_encode(MSG_TYPE_SENSOR, g_tx_seq++, (const uint8_t *)&s_msg, sizeof(s_msg), tx_buffer, sizeof(tx_buffer));
            if (enc_len > 0) {
                Serial2.write(tx_buffer, enc_len);
            }
        }

        // 7. Transmit 2 Hz STATUS packet
        if (now - last_status_tx_ms >= STATUS_INTERVAL_MS) {
            last_status_tx_ms = now;

            uint32_t hb_age = (g_supervisor.last_heartbeat_time_ms > 0) ? (now - g_supervisor.last_heartbeat_time_ms) : 65535;
            if (hb_age > 65535) hb_age = 65535;

            status_payload_t st_msg;
            st_msg.fw_version = FW_VERSION;
            st_msg.reset_reason = (uint8_t)esp_reset_reason();
            st_msg.fault_code = (uint8_t)(g_supervisor.latched_fault ? 1 : 0);
            st_msg.rx_err = g_rx_err_count;
            st_msg.ads_err = g_ads_err_count;
            st_msg.hb_age_ms = (uint16_t)hb_age;

            size_t enc_len = frame_encode(MSG_TYPE_STATUS, g_tx_seq++, (const uint8_t *)&st_msg, sizeof(st_msg), tx_buffer, sizeof(tx_buffer));
            if (enc_len > 0) {
                Serial2.write(tx_buffer, enc_len);
            }
        }

        vTaskDelay(pdMS_TO_TICKS(2));
    }
}

void setup() {
    // 1. FIRST ACTION ON BOOT: Disable PCA9685 OE immediately
    pinMode(PIN_PCA9685_OE, OUTPUT);
    digitalWrite(PIN_PCA9685_OE, HIGH); // HIGH = all servo outputs disabled

    // 2. Configure E-stop pin
    pinMode(PIN_ESTOP, INPUT_PULLUP);

    // 3. Configure ADC1 attenuation for FSRs (11 dB: 0 to ~3.3V range)
    analogSetAttenuation(ADC_11db);

    // 4. Initialize I2C bus for ADS1115 (Fast mode: 400 kHz)
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 400000);

    // 5. Initialize UART2 at 460800 baud
    Serial2.begin(460800, SERIAL_8N1, PIN_UART_RX, PIN_UART_TX);

    // 6. Initialize supervisor state
    supervisor_init(&g_supervisor, &g_config);

    // 7. Create data synchronization mutex
    g_data_mutex = xSemaphoreCreateMutex();

    // 8. Configure Hardware Task Watchdog
    esp_task_wdt_config_t twdt_config = {
        .timeout_ms = WATCHDOG_TIMEOUT_S * 1000,
        .idle_core_mask = 0,
        .trigger_panic = true,
    };
    esp_task_wdt_init(&twdt_config);

    // 9. Launch FreeRTOS Tasks on separate cores
    xTaskCreatePinnedToCore(
        SensorSamplingTask,
        "SensorTask",
        4096,
        NULL,
        2,
        NULL,
        0 // Core 0
    );

    xTaskCreatePinnedToCore(
        SupervisorUartTask,
        "SupervisorTask",
        4096,
        NULL,
        3,
        NULL,
        1 // Core 1
    );
}

void loop() {
    // FreeRTOS tasks run execution; idle loop
    vTaskDelay(pdMS_TO_TICKS(1000));
}
