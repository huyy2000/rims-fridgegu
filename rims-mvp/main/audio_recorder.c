/* 录音实现：后台任务采样 + RMS 静音检测（VAD）。
 * I2S 配置来源：easy-input-maker keyboard_audio.cpp 同板验证代码（MSB/32bit/RIGHT）。 */
#include "audio_recorder.h"

#include <string.h>

#include "driver/gpio.h"
#include "driver/i2s_std.h"
#include "esp_heap_caps.h"
#include <math.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"
#include "status_led.h"
#include "buttons.h"
#include "platform/board_pins.h"

static const char *TAG = "rec";
static i2s_chan_handle_t s_rx = NULL;

static TaskHandle_t s_task = NULL;
static volatile bool s_active = false;
static volatile bool s_stop_req = false;
static volatile bool s_done = true;
static volatile rec_mode_t s_mode = REC_MODE_TAP;
static volatile bool s_has_speech = false;
static uint8_t *s_buf = NULL;
static volatile size_t s_len = 0;

#define VAD_WIN_FRAMES (REC_SAMPLE_RATE / 4)   /* 250ms 一个 RMS 窗口 */

static esp_err_t rx_setup(void) {
    if (s_rx) return ESP_OK;
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_1, I2S_ROLE_MASTER);
    chan_cfg.dma_desc_num = 6;
    chan_cfg.dma_frame_num = 240;
    esp_err_t err = i2s_new_channel(&chan_cfg, NULL, &s_rx);
    if (err != ESP_OK) return err;

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(REC_SAMPLE_RATE),
        .slot_cfg = I2S_STD_MSB_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = (gpio_num_t)kBeanPins.mic_sck,
            .ws = (gpio_num_t)kBeanPins.mic_ws,
            .dout = I2S_GPIO_UNUSED,
            .din = (gpio_num_t)kBeanPins.mic_sd,
            .invert_flags = {false, false, false},
        },
    };
    std_cfg.slot_cfg.slot_mask = I2S_STD_SLOT_RIGHT;
    err = i2s_channel_init_std_mode(s_rx, &std_cfg);
    if (err != ESP_OK) {
        i2s_del_channel(s_rx);
        s_rx = NULL;
        return err;
    }
    return i2s_channel_enable(s_rx);
}

static void rx_teardown(void) {
    if (s_rx) {
        i2s_channel_disable(s_rx);
        i2s_del_channel(s_rx);
        s_rx = NULL;
    }
}

static void power_on(void) {
    gpio_config_t io = {.pin_bit_mask = 1ULL << kBeanPins.periph_power, .mode = GPIO_MODE_OUTPUT};
    gpio_config(&io);
    gpio_set_level((gpio_num_t)kBeanPins.periph_power, 1);
    vTaskDelay(pdMS_TO_TICKS(20));
}

static uint32_t elapsed_ms(TickType_t start) {
    return (uint32_t)((xTaskGetTickCount() - start) * portTICK_PERIOD_MS);
}

static void rec_task(void *arg) {
    const char *mode_name = s_mode == REC_MODE_BEAN ? "bean" : "tap";
    ESP_LOGI(TAG, "[%s] 开始录音…", mode_name);

    esp_err_t err = rx_setup();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "I2S RX 初始化失败: %s", esp_err_to_name(err));
        s_done = true;
        s_active = false;
        vTaskDelete(NULL);
        return;
    }
    power_on();

    static int32_t raw[240];
    int16_t *dst = (int16_t *)s_buf;
    size_t frames_total = 0;
    uint32_t cap_ms = s_mode == REC_MODE_BEAN ? REC_BEAN_MAX_MS : REC_TAP_MAX_MS;
    bool speech = false;
    uint32_t last_voice_ms = 0;
    TickType_t start = xTaskGetTickCount();
    size_t win_frames = 0;

    while (elapsed_ms(start) < cap_ms && !s_stop_req) {
        size_t bytes_read = 0;
        if (i2s_channel_read(s_rx, raw, sizeof(raw), &bytes_read, portMAX_DELAY) != ESP_OK) break;
        int n = bytes_read / 4;
        int32_t sum_sq = 0;
        for (int i = 0; i < n && frames_total < cap_ms / 1000 * REC_SAMPLE_RATE; i++, frames_total++) {
            int16_t v = (int16_t)(raw[i] >> 16);  /* MSB 32bit → 16bit */
            dst[frames_total] = v;
            sum_sq += ((int32_t)v * v) >> 8;
        }
        win_frames += n;
        led_rec_blink_tick(frames_total);

        if (win_frames >= VAD_WIN_FRAMES) {  /* 每 250ms 一次静音检测 */
            int rms = (int)(sqrtf((float)sum_sq / VAD_WIN_FRAMES));
            ESP_LOGI(TAG, "RMS=%d", rms);
            if (rms > CONFIG_REC_VAD_RMS) {
                speech = true;
                last_voice_ms = elapsed_ms(start);
            }
            win_frames = 0;
            sum_sq = 0;
            uint32_t since_voice = elapsed_ms(start) - last_voice_ms;
            if (s_mode == REC_MODE_TAP && since_voice > REC_TAP_SILENCE_MS) {
                ESP_LOGI(TAG, "静音 %lu ms，结束录音", (unsigned long)REC_TAP_SILENCE_MS);
                break;
            }
        }
    }

    rx_teardown();
    led_rec_off();
    gpio_set_level((gpio_num_t)kBeanPins.periph_power, 0);

    s_len = frames_total * 2;
    s_has_speech = speech;
    s_active = false;
    s_done = true;
    buttons_post(BTN_REC_DONE);  /* 通知主循环取结果并上传 */
    ESP_LOGI(TAG, "录音结束: %u bytes (%.1fs) speech=%d",
             (unsigned)s_len, (float)s_len / 2 / REC_SAMPLE_RATE, s_has_speech);
    vTaskDelete(NULL);
}

esp_err_t recorder_begin(rec_mode_t mode) {
    if (s_active) return ESP_ERR_INVALID_STATE;
    if (s_buf == NULL) {
        s_buf = heap_caps_malloc((size_t)REC_BEAN_MAX_MS / 1000 * REC_SAMPLE_RATE * 2,
                                 MALLOC_CAP_SPIRAM);
        if (s_buf == NULL) {
            ESP_LOGE(TAG, "PSRAM 录音缓冲分配失败");
            return ESP_ERR_NO_MEM;
        }
    }
    s_mode = mode;
    s_stop_req = false;
    s_done = false;
    s_has_speech = false;
    s_len = 0;
    s_active = true;
    if (xTaskCreate(rec_task, "rec", 4096, NULL, 5, &s_task) != pdPASS) {
        s_active = false;
        return ESP_FAIL;
    }
    return ESP_OK;
}

bool recorder_active(void) {
    return s_active;
}

void recorder_request_stop(void) {
    s_stop_req = true;
}

esp_err_t recorder_take(const uint8_t **out, size_t *out_len, bool *has_speech) {
    int wait = 0;
    while (!s_done && wait < 100) {
        vTaskDelay(pdMS_TO_TICKS(50));
        wait++;
    }
    if (!s_done) return ESP_ERR_INVALID_STATE;
    *out = s_buf;
    *out_len = s_len;
    *has_speech = s_has_speech;
    return ESP_OK;
}
