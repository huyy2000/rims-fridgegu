/* 按键消抖与事件队列：S1..S6（GPIO 2/47/38/41/1/6，低有效）。 */
#include "buttons.h"

#include <string.h>

#include "driver/gpio.h"
#include "esp_log.h"
#include "freertos/task.h"
#include "platform/board_pins.h"

static const char *TAG = "btn";
static QueueHandle_t s_queue = NULL;

static const struct {
    gpio_num_t pin;
    btn_event_t ev;
    const char *name;
} kKeys[] = {
    { (gpio_num_t)2,  BTN_S1, "S1 拍键" },
    { (gpio_num_t)47, BTN_S2, "S2 取下豆" },
    { (gpio_num_t)38, BTN_S3, "S3 放回豆" },
    { (gpio_num_t)41, BTN_S4, "S4 唤醒" },
    { (gpio_num_t)1,  BTN_S5, "S5 冷藏门" },
    { (gpio_num_t)6,  BTN_S6, "S6 冷冻门" },
};

static void add_event(btn_event_t ev) {
    if (s_queue) xQueueSend(s_queue, &ev, 0);
}

static void key_task(void *arg) {
    int idx = (int)(intptr_t)arg;
    gpio_num_t pin = kKeys[idx].pin;
    bool was_pressed = false;
    for (;;) {
        bool pressed = gpio_get_level(pin) == 0;  /* 低有效 */
        if (pressed && !was_pressed) {
            vTaskDelay(pdMS_TO_TICKS(30));        /* 消抖 */
            if (gpio_get_level(pin) == 0) {
                ESP_LOGI(TAG, "%s 按下", kKeys[idx].name);
                add_event(kKeys[idx].ev);
                was_pressed = true;
                while (gpio_get_level(pin) == 0) vTaskDelay(pdMS_TO_TICKS(20));
            }
        } else {
            was_pressed = false;
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

QueueHandle_t buttons_init(void) {
    if (s_queue) return s_queue;
    s_queue = xQueueCreate(8, sizeof(btn_event_t));

    uint32_t mask = 0;
    for (int i = 0; i < (int)(sizeof(kKeys) / sizeof(kKeys[0])); i++)
        mask |= 1ULL << kKeys[i].pin;
    gpio_config_t io = {
        .pin_bit_mask = mask,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    gpio_config(&io);

    char name[8];
    for (int i = 0; i < (int)(sizeof(kKeys) / sizeof(kKeys[0])); i++) {
        snprintf(name, sizeof(name), "key%d", i + 1);
        xTaskCreate(key_task, name, 3072, (void *)(intptr_t)i, 5, NULL);
    }
    return s_queue;
}

void buttons_post(btn_event_t ev) {
    if (s_queue) xQueueSend(s_queue, &ev, 0);
}

bool buttons_wait(btn_event_t *out, int timeout_ms) {
    return xQueueReceive(s_queue, out, pdMS_TO_TICKS(timeout_ms)) == pdTRUE;
}
