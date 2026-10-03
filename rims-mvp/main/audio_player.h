#pragma once
/* 喇叭播放：解析 WAV（16bit PCM）→ I2S TX（BCLK=14/WS=13/DOUT=15）。
 * GPIO8 外设共电：播放前拉高（含 20ms 建立等待，实现策略而非硬件参数），
 * 播放完拉低；调用方需保证没有其他 GPIO8 消费者在用。
 * I2S 配置抄自 easy-input-maker main/platform/speaker_output.cpp 的同板验证实现：
 * Philips + 16bit + mono + LEFT slot。
 */
#include "esp_err.h"
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t player_init(void);
/* 播放内存中的 WAV（阻塞）；返回解析/播放错误。 */
esp_err_t player_play_wav(const uint8_t *data, size_t len);

#ifdef __cplusplus
}
#endif
