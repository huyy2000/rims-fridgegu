#pragma once
/* door_event_policy — 冰箱门事件 → 「主动询问 + 录音」触发策略（纯逻辑，host 可测）。
 *
 * ADR-11（2026-09-28 拍板）：MVP 每次开门都问 → min_retrigger_ms = 0。
 * 节流能力保留在配置里，烦了改配置不改代码。
 *
 * 语义：
 * - 门开（OPEN）后去抖确认（debounce_ms 内收到 CLOSE 视为抖动，取消本次）。
 * - 去抖确认后触发一次「询问 + 录音」（step 返回 true，仅该次为 true）。
 * - 录音进行中再开门不重触发；录音结束后门还开着也不再自动问，
 *   直到关门后重新开门（一次开门至多问一次）。
 * - min_retrigger_ms > 0 时，两次触发间隔小于该值则本次开门静默。
 */
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    DEPO_STATE_IDLE = 0,      /* 门关着或无挂起事件 */
    DEPO_STATE_ARMED,         /* 门开，去抖计时中 */
    DEPO_STATE_ASKING,        /* 已触发询问，等录音系统回应 */
    DEPO_STATE_RECORDING,     /* 录音进行中 */
} depo_state_t;

typedef enum {
    DEPO_EV_DOOR_OPEN = 0,
    DEPO_EV_DOOR_CLOSE,
    DEPO_EV_TICK,
    DEPO_EV_RECORD_STARTED,
    DEPO_EV_RECORD_DONE,
} depo_event_t;

typedef struct {
    uint32_t debounce_ms;      /* 开门去抖窗口 */
    uint32_t min_retrigger_ms; /* 两次触发最小间隔；0 = 每次开门都问 */
} depo_config_t;

typedef struct {
    depo_state_t state;
    uint32_t armed_since_ms;
    uint32_t last_trigger_ms;
    bool ever_triggered;
} depo_ctx_t;

void depo_init(depo_ctx_t *ctx);

/* 每个事件喂一次；返回 true = 应当扬声器询问并开启录音 */
bool depo_step(depo_ctx_t *ctx, const depo_config_t *cfg, depo_event_t ev, uint32_t now_ms);

#ifdef __cplusplus
}
#endif
