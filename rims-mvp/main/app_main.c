/* RIMS 录音豆 MVP · 主装配（EasyInput V2 板临时载体）。
 *
 * 交互总纲（小祜 2026-10-03 定稿）：
 *   S1 拍大蘑菇    → 开始录音，静音 5 秒自动结束（上限 15s）
 *   S2 取下录音豆  → 持续录音（上限 60s）
 *   S3 放回录音豆  → 停止 + 上传
 *   S4 语音唤醒    → 播报"我在"，进入聆听
 *   S5 冷藏门开    → TTS 问「拿了什么？」→ 录音，本门=冷藏
 *   S6 冷冻门开    → 同上，本门=冷冻
 *   上传后：放入/消耗不播报，仅查询播报（后端 speak 标志）
 *   录音上传带 zone 字段：门开场景下，用户没说位置的东西按本门归类
 */
#include <string.h>

#include "audio_player.h"
#include "audio_recorder.h"
#include "buttons.h"
#include "cloud_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "sdkconfig.h"
#include "status_led.h"
#include "wifi_prov.h"

static const char *TAG = "main";

static fridgegu_config_t s_cfg;
static const char *s_zone = NULL;   /* 门开场景的分区提示（冷藏/冷冻），随上传消费 */

static void speak_text(const char *text) {
    const uint8_t *tts = NULL;
    size_t tts_len = 0;
    if (cloud_get_tts(s_cfg.server, text, &tts, &tts_len) == ESP_OK) {
        player_play_wav(tts, tts_len);
    } else {
        ESP_LOGW(TAG, "TTS 获取失败");
    }
}

/* 录音结束（BTN_REC_DONE）后的公共上传流程 */
static void finish_and_upload(void) {
    const uint8_t *pcm = NULL;
    size_t pcm_len = 0;
    bool has_speech = false;
    if (recorder_take(&pcm, &pcm_len, &has_speech) != ESP_OK) {
        ESP_LOGE(TAG, "取录音失败");
        return;
    }
    if (pcm_len == 0) {
        ESP_LOGW(TAG, "无录音数据，跳过上传");
        return;
    }

    /* 16bit 单声道 PCM → WAV（44 字节头，size 用真实值） */
    static uint8_t wav_header[44];
    uint32_t data_len = (uint32_t)pcm_len;
    uint32_t riff_len = 36 + data_len;
    memcpy(wav_header, "RIFF", 4);
    memcpy(wav_header + 4, &riff_len, 4);
    memcpy(wav_header + 8, "WAVEfmt ", 8);
    uint32_t fmt_len = 16;
    memcpy(wav_header + 16, &fmt_len, 4);
    uint16_t fmt_pcm = 1, ch = 1;
    memcpy(wav_header + 20, &fmt_pcm, 2);
    memcpy(wav_header + 22, &ch, 2);
    uint32_t rate = REC_SAMPLE_RATE, byte_rate = REC_SAMPLE_RATE * 2;
    memcpy(wav_header + 24, &rate, 4);
    memcpy(wav_header + 28, &byte_rate, 4);
    uint16_t align = 2, bits = 16;
    memcpy(wav_header + 32, &align, 2);
    memcpy(wav_header + 34, &bits, 2);
    memcpy(wav_header + 36, "data", 4);
    memcpy(wav_header + 40, &data_len, 4);

    char reply[192] = {0};
    bool speak = false;
    esp_err_t err = cloud_upload_recording(s_cfg.server, wav_header, sizeof(wav_header),
                                           pcm, pcm_len, s_zone, reply, sizeof(reply), &speak);
    s_zone = NULL;  /* 一次上传消费一次门提示 */
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "上传失败: %s", esp_err_to_name(err));
        return;
    }
    ESP_LOGI(TAG, "菇菇回复: %s (speak=%d)", reply, speak);

    /* 收缩原则：只有查询才语音播报，放入/消耗静默 */
    if (speak && reply[0]) {
        speak_text(reply);
    }
}

static void start_tap_recording(void) {
    if (recorder_active()) {
        ESP_LOGW(TAG, "已在录音中，忽略");
        return;
    }
    recorder_begin(REC_MODE_TAP);
}

static void door_open_flow(const char *zone) {
    ESP_LOGI(TAG, "[%s 门开] 主动询问", zone);
    s_zone = zone;
    speak_text("拿了什么？");
    vTaskDelay(pdMS_TO_TICKS(400));
    start_tap_recording();
}

static void wake_flow(void) {
    ESP_LOGI(TAG, "[语音唤醒] 我在");
    speak_text("我在");
    vTaskDelay(pdMS_TO_TICKS(200));
    start_tap_recording();
}

void app_main(void) {
    ESP_LOGI(TAG, "冰箱菇 MVP 启动（EasyInput V2 载体）");

    esp_err_t nvs_err = nvs_flash_init();
    if (nvs_err == ESP_ERR_NVS_NO_FREE_PAGES || nvs_err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    player_init();
    led_init();
    buttons_init();

    bool missing = false;
    prov_load(&s_cfg, &missing);
    if (missing || s_cfg.server[0] == '\0') {
        ESP_LOGW(TAG, "未配网，进入 SoftAP 配网模式");
        led_provisioning();
        prov_start_softap();
        return;  /* 配网页保存后重启 */
    }

    if (prov_connect_sta(&s_cfg, 20000) != ESP_OK) {
        ESP_LOGW(TAG, "Wi-Fi 连不上，转配网模式");
        led_provisioning();
        prov_start_softap();
        return;
    }
    ESP_LOGI(TAG, "云端地址: %s", s_cfg.server);
    led_connected();

    btn_event_t ev;
    for (;;) {
        if (buttons_wait(&ev, 60000)) {
            switch (ev) {
            case BTN_S1:
                start_tap_recording();
                break;
            case BTN_S2:
                ESP_LOGI(TAG, "[取下录音豆] 持续录音开始");
                recorder_begin(REC_MODE_BEAN);
                break;
            case BTN_S3:
                if (recorder_active()) {
                    ESP_LOGI(TAG, "[放回录音豆] 停止并上传");
                    recorder_request_stop();  /* REC_DONE 事件回主循环统一上传 */
                } else {
                    ESP_LOGW(TAG, "录音豆未在录音，忽略放回");
                }
                break;
            case BTN_S4:
                ESP_LOGI(TAG, "[语音唤醒] 我在");
                speak_text("我在");
                vTaskDelay(pdMS_TO_TICKS(200));
                start_tap_recording();
                break;
            case BTN_S5:
                ESP_LOGI(TAG, "[冷藏门开] 主动询问");
                s_zone = "冷藏";
                speak_text("拿了什么？");
                vTaskDelay(pdMS_TO_TICKS(400));
                start_tap_recording();
                break;
            case BTN_S6:
                ESP_LOGI(TAG, "[冷冻门开] 主动询问");
                s_zone = "冷冻";
                speak_text("拿了什么？");
                vTaskDelay(pdMS_TO_TICKS(400));
                start_tap_recording();
                break;
            case BTN_REC_DONE:
                finish_and_upload();
                break;
            default:
                break;
            }
        }
    }
}
