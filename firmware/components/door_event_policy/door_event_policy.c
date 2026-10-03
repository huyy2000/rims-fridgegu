#include "door_event_policy.h"

void depo_init(depo_ctx_t *ctx) {
    ctx->state = DEPO_STATE_IDLE;
    ctx->armed_since_ms = 0;
    ctx->last_trigger_ms = 0;
    ctx->ever_triggered = false;
}

bool depo_step(depo_ctx_t *ctx, const depo_config_t *cfg, depo_event_t ev, uint32_t now_ms) {
    bool trigger = false;

    switch (ev) {
    case DEPO_EV_DOOR_OPEN:
        /* 一次开门至多问一次：录音/询问中再来 OPEN 一律忽略 */
        if (ctx->state == DEPO_STATE_IDLE) {
            ctx->state = DEPO_STATE_ARMED;
            ctx->armed_since_ms = now_ms;
        }
        break;

    case DEPO_EV_DOOR_CLOSE:
        /* 只有去抖挂起阶段关门才取消；ASKING/RECORDING 让录音链路自己走完 */
        if (ctx->state == DEPO_STATE_ARMED) {
            ctx->state = DEPO_STATE_IDLE;
        }
        break;

    case DEPO_EV_TICK:
        if (ctx->state == DEPO_STATE_ARMED &&
            now_ms - ctx->armed_since_ms >= cfg->debounce_ms) {
            bool allowed = !ctx->ever_triggered ||
                           cfg->min_retrigger_ms == 0 ||
                           now_ms - ctx->last_trigger_ms >= cfg->min_retrigger_ms;
            if (allowed) {
                ctx->state = DEPO_STATE_ASKING;
                ctx->last_trigger_ms = now_ms;
                ctx->ever_triggered = true;
                trigger = true;
            } else {
                ctx->state = DEPO_STATE_IDLE; /* 被节流，本次开门静默 */
            }
        }
        break;

    case DEPO_EV_RECORD_STARTED:
        if (ctx->state == DEPO_STATE_ASKING) {
            ctx->state = DEPO_STATE_RECORDING;
        }
        break;

    case DEPO_EV_RECORD_DONE:
        /* RECORD_DONE 在 ASKING 也接受：录音启动失败/中止时防止状态机卡死 */
        if (ctx->state == DEPO_STATE_RECORDING || ctx->state == DEPO_STATE_ASKING) {
            ctx->state = DEPO_STATE_IDLE;
        }
        break;
    }

    return trigger;
}
