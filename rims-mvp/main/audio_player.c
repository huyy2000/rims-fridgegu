/* 喇叭播放实现（配置来源：easy-input-maker keyboard 固件同板验证代码）。 */
#include "audio_player.h"

#include <string.h>

#include "driver/gpio.h"
#include "driver/i2s_std.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "platform/board_pins.h"

static const char *TAG = "player";
static i2s_chan_handle_t s_tx = NULL;
static bool s_tx_ready = false;

static esp_err_t tx_setup(int sample_rate) {
    if (s_tx_ready) {
        i2s_channel_disable(s_tx);
        i2s_del_channel(s_tx);
        s_tx = NULL;
        s_tx_ready = false;
    }
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    chan_cfg.dma_desc_num = 6;
    chan_cfg.dma_frame_num = 240;
    esp_err_t err = i2s_new_channel(&chan_cfg, &s_tx, NULL);
    if (err != ESP_OK) return err;

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(sample_rate),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = (gpio_num_t)kBeanPins.spk_bclk,
            .ws = (gpio_num_t)kBeanPins.spk_ws,
            .dout = (gpio_num_t)kBeanPins.spk_sd,
            .din = I2S_GPIO_UNUSED,
            .invert_flags = {false, false, false},
        },
    };
    std_cfg.slot_cfg.slot_mask = I2S_STD_SLOT_LEFT;
    err = i2s_channel_init_std_mode(s_tx, &std_cfg);
    if (err != ESP_OK) {
        i2s_del_channel(s_tx);
        s_tx = NULL;
        return err;
    }
    err = i2s_channel_enable(s_tx);
    if (err == ESP_OK) s_tx_ready = true;
    return err;
}

static void power_on(void) {
    gpio_config_t io = {
        .pin_bit_mask = 1ULL << kBeanPins.periph_power,
        .mode = GPIO_MODE_OUTPUT,
    };
    gpio_config(&io);
    gpio_set_level((gpio_num_t)kBeanPins.periph_power, 1);
    /* GPIO8 拉高后的最短稳定时间尚无板级数据，20ms 为当前实现策略（见硬件安全文档）。 */
    vTaskDelay(pdMS_TO_TICKS(20));
}

static void power_off(void) {
    gpio_set_level((gpio_num_t)kBeanPins.periph_power, 0);
}

/* 解析 WAV：返回 data 指针（在 data 内）、采样率、声道数；仅支持 16bit。 */
static esp_err_t parse_wav(const uint8_t *data, size_t len, const uint8_t **pcm,
                           size_t *pcm_len, int *rate, int *channels) {
    if (len < 44 || memcmp(data, "RIFF", 4) != 0) return ESP_ERR_NOT_SUPPORTED;
    size_t pos = 12;
    int r = 16000, ch = 1;
    bool have_fmt = false;
    while (pos + 8 <= len) {
        uint32_t size = data[pos + 4] | (data[pos + 5] << 8) | (data[pos + 6] << 16) |
                        ((uint32_t)data[pos + 7] << 24);
        if (!memcmp(data + pos, "fmt ", 4) && size >= 16) {
            r = data[pos + 12] | (data[pos + 13] << 8) | (data[pos + 14] << 16) |
                ((uint32_t)data[pos + 15] << 24);
            ch = data[pos + 10] | (data[pos + 11] << 8);
            int bits = data[pos + 22] | (data[pos + 23] << 8);
            if (bits != 16) return ESP_ERR_NOT_SUPPORTED;
            have_fmt = true;
        } else if (!memcmp(data + pos, "data", 4) && have_fmt) {
            size_t avail = len - (pos + 8);
            *pcm = data + pos + 8;
            *pcm_len = size > avail ? avail : size;  /* 流式头 size 可能虚大，按实际截断 */
            *rate = r;
            *channels = ch;
            return ESP_OK;
        }
        pos += 8 + size + (size & 1);
    }
    return ESP_ERR_NOT_SUPPORTED;
}

esp_err_t player_init(void) {
    /* 通道按需创建/销毁，这里只准备 GPIO8 引脚。 */
    return ESP_OK;
}

esp_err_t player_play_wav(const uint8_t *data, size_t len) {
    const uint8_t *pcm = NULL;
    size_t pcm_len = 0;
    int rate = 16000, ch = 1;
    esp_err_t err = parse_wav(data, len, &pcm, &pcm_len, &rate, &ch);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "WAV 解析失败");
        return err;
    }
    ESP_LOGI(TAG, "播放: %u bytes, %dHz, %dch", (unsigned)pcm_len, rate, ch);

    power_on();
    err = tx_setup(rate);
    if (err != ESP_OK) {
        power_off();
        return err;
    }

    /* mono 16bit 直接写；stereo 逐帧只取左声道，凑成 mono。 */
    if (ch == 1) {
        size_t written = 0, offset = 0;
        while (offset < pcm_len) {
            size_t n = pcm_len - offset > 4800 ? 4800 : pcm_len - offset;
            if (i2s_channel_write(s_tx, pcm + offset, n, &written, portMAX_DELAY) != ESP_OK) break;
            offset += written;
        }
    } else {
        static int16_t mono[2400];
        for (size_t i = 0; i + 4 <= pcm_len; i += 4) {
            mono[(i / 4) % 2400] = (int16_t)(pcm[i] | (pcm[i + 1] << 8));
            if ((i / 4) % 2400 == 2399 || i + 4 >= pcm_len) {
                size_t frames = ((i / 4) % 2400) + 1;
                size_t written = 0;
                i2s_channel_write(s_tx, mono, frames * 2, &written, portMAX_DELAY);
            }
        }
    }

    i2s_channel_disable(s_tx);
    i2s_del_channel(s_tx);
    s_tx = NULL;
    s_tx_ready = false;
    power_off();
    ESP_LOGI(TAG, "播放完成");
    return ESP_OK;
}
