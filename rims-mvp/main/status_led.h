#pragma once
/* 状态灯：5 颗 WS2812（GPIO12，GPIO8 供电域）。
 * 语义（小祜 2026-10-03 定义）：
 *   第 5 颗 红色常亮 = 配网中（SoftAP 等待）
 *   第 5 颗 绿色常亮 = 配网成功（Wi-Fi 已连接）
 *   第 1 颗 蓝色闪烁 = 录音进行中；结束熄灭
 * 约定：demo 阶段 GPIO8 常开（LED/麦/喇叭共享域），量产再引入租约。
 */
#include "esp_err.h"
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t led_init(void);
void led_clear_all(void);
void led_set(int idx, uint8_t r, uint8_t g, uint8_t b);
void led_provisioning(void);   /* 第 5 颗红 */
void led_connected(void);      /* 第 5 颗绿 */
void led_rec_blink_tick(size_t frames_recorded); /* 第 1 颗蓝闪（录音循环里调） */
void led_rec_off(void);        /* 第 1 颗灭 */

#ifdef __cplusplus
}
#endif
