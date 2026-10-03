#pragma once
/* 录音模块：I2S RX（9/10/11，MSB/32bit/RIGHT——键盘固件同板验证配置）。
 *
 * 两种模式（对应交互总纲）：
 *   REC_MODE_TAP  拍键/唤醒/门开：静音 5 秒自动结束（说过话才算有效），
 *                 上限 15 秒；全程无人声 = has_speech=false（不上传）
 *   REC_MODE_BEAN 小蘑菇取下：持续录音直到 request_stop，上限 60 秒
 *
 * VAD：按 250ms 窗口算 RMS，超阈值视为说话；说话后静音 5 秒收尾。
 * 阈值可经 CONFIG_REC_VAD_RMS 调整（默认 500）。
 */
#include "esp_err.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    REC_MODE_TAP = 0,
    REC_MODE_BEAN = 1,
} rec_mode_t;

#define REC_SAMPLE_RATE 16000
#define REC_TAP_MAX_MS     15000
#define REC_TAP_SILENCE_MS 5000
#define REC_BEAN_MAX_MS    60000

/* 开始录音（已在录音则忽略）。采样在后台任务进行。 */
esp_err_t recorder_begin(rec_mode_t mode);

/* 请求停止（BEAN 模式放回时用；TAP 自动结束无需调用）。 */
void recorder_request_stop(void);

bool recorder_active(void);

/* 取录音结果：*out 为 PSRAM 中 16bit 单声道 PCM，*len 字节，
 * *has_speech = 全程是否检测到人声。调用前应先收到 REC_DONE。 */
esp_err_t recorder_take(const uint8_t **out, size_t *out_len, bool *has_speech);

#ifdef __cplusplus
}
#endif
