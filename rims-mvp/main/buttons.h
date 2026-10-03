#pragma once
/* 按键：S1..S6 低有效 + 30ms 消抖，事件进队列。
 * 语义（小祜 2026-10-03 定义）：
 *   S1 拍大蘑菇=录音开始（静音5秒自动结束）
 *   S2 取下录音豆=持续录音开始
 *   S3 放回录音豆=停止+上传
 *   S4 语音唤醒（小祜小祜）
 *   S5 冷藏室门开（主动询问，本门=冷藏）
 *   S6 冷冻室门开（主动询问，本门=冷冻）
 */
#include <stdbool.h>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    BTN_S1 = 1,         /* 拍大蘑菇 */
    BTN_S2 = 2,         /* 取下录音豆 */
    BTN_S3 = 3,         /* 放回录音豆 */
    BTN_S4 = 4,         /* 语音唤醒 */
    BTN_S5 = 5,         /* 冷藏门开 */
    BTN_S6 = 6,         /* 冷冻门开 */
    BTN_REC_DONE = 10,  /* 内部：录音结束（recorder 任务发出） */
} btn_event_t;

QueueHandle_t buttons_init(void);
void buttons_post(btn_event_t ev);
bool buttons_wait(btn_event_t *out, int timeout_ms);

#ifdef __cplusplus
}
#endif
