/* 状态灯实现：WS2812 via RMT（espressif/led_strip 组件）。 */
#include "status_led.h"

#include <string.h>

#include "driver/gpio.h"
#include "esp_log.h"
#include "led_strip.h"
#include "platform/board_pins.h"

static const char *TAG = "led";
static led_strip_handle_t s_strip = NULL;
static bool s_blink_state = false;

#define LED_COUNT     5
#define LED_REC       0   /* 第 1 颗：录音蓝闪 */
#define LED_STATUS    4   /* 第 5 颗：配网/连接状态 */
#define REC_SRATE     16000

esp_err_t led_init(void) {
    /* WS2812 由 GPIO8 供电域供电：demo 常开（量产需接租约，见注释） */
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << kBeanPins.periph_power,
        .mode = GPIO_MODE_OUTPUT,
    };
    gpio_config(&io);
    gpio_set_level((gpio_num_t)kBeanPins.periph_power, 1);

    if (s_strip) return ESP_OK;
    led_strip_config_t strip = {
        .strip_gpio_num = kBeanPins.ws2812,
        .max_leds = LED_COUNT,
        .led_pixel_format = LED_PIXEL_FORMAT_GRB,
        .led_model = LED_MODEL_WS2812,
        .flags.invert_out = false,
    };
    led_strip_rmt_config_t rmt = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = 10 * 1000 * 1000,
        .mem_block_symbols = 64,
    };
    esp_err_t err = led_strip_new_rmt_device(&strip, &rmt, &s_strip);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "led_strip init failed: %s", esp_err_to_name(err));
        s_strip = NULL;
        return err;
    }
    led_strip_clear(s_strip);
    ESP_LOGI(TAG, "状态灯就绪（5 颗 WS2812 @ GPIO%d）", kBeanPins.ws2812);
    return ESP_OK;
}

void led_clear_all(void) {
    if (s_strip) led_strip_clear(s_strip);
}

void led_set(int idx, uint8_t r, uint8_t g, uint8_t b) {
    if (!s_strip || idx < 0 || idx >= LED_COUNT) return;
    led_strip_set_pixel(s_strip, idx, r, g, b);
    led_strip_refresh(s_strip);
}

void led_provisioning(void) {
    if (!s_strip) return;
    led_strip_clear(s_strip);
    led_strip_set_pixel(s_strip, LED_STATUS, 255, 0, 0);
    led_strip_refresh(s_strip);
}

void led_connected(void) {
    if (!s_strip) return;
    led_strip_clear(s_strip);
    led_strip_set_pixel(s_strip, LED_STATUS, 0, 255, 120);
    led_strip_refresh(s_strip);
}

void led_rec_blink_tick(size_t frames_recorded) {
    if (!s_strip) return;
    bool on = (frames_recorded / (REC_SRATE / 4)) % 2 == 0;  /* 250ms 翻转 */
    if (on != s_blink_state) {
        s_blink_state = on;
        if (on) led_strip_set_pixel(s_strip, LED_REC, 0, 0, 255);
        else led_strip_set_pixel(s_strip, LED_REC, 0, 0, 0);
        led_strip_refresh(s_strip);
    }
}

void led_rec_off(void) {
    if (!s_strip) return;
    led_strip_set_pixel(s_strip, LED_REC, 0, 0, 0);
    led_strip_refresh(s_strip);
    s_blink_state = false;
}
