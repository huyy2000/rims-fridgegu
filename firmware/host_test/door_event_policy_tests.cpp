// door_event_policy 纯逻辑测试（无第三方框架，断言计数即可）
#include <cstdio>
#include <cstdlib>
#include "door_event_policy.h"

static int g_fail = 0;
#define CHECK(cond) do { \
    if (!(cond)) { printf("  FAIL line %d: %s\n", __LINE__, #cond); ++g_fail; } \
} while (0)

// ADR-11：每次开门都问（min_retrigger_ms = 0）
static const depo_config_t kEveryTime = {300, 0};

static void test_single_open_fires_once_after_debounce(void) {
    depo_ctx_t c; depo_init(&c);
    CHECK(depo_step(&c, &kEveryTime, DEPO_EV_DOOR_OPEN, 0) == false);
    CHECK(depo_step(&c, &kEveryTime, DEPO_EV_TICK, 100) == false);
    CHECK(depo_step(&c, &kEveryTime, DEPO_EV_TICK, 299) == false);
    CHECK(depo_step(&c, &kEveryTime, DEPO_EV_TICK, 300) == true);
    CHECK(depo_step(&c, &kEveryTime, DEPO_EV_TICK, 400) == false); // 只在边沿触发一次
    CHECK(c.state == DEPO_STATE_ASKING);
}

static void test_bounce_yields_single_trigger(void) {
    depo_ctx_t c; depo_init(&c);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_DOOR_OPEN, 0);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_DOOR_CLOSE, 50);  // 抖动
    (void)depo_step(&c, &kEveryTime, DEPO_EV_DOOR_OPEN, 80);   // 重新 arm
    CHECK(depo_step(&c, &kEveryTime, DEPO_EV_TICK, 379) == false); // 80+300 未到
    CHECK(depo_step(&c, &kEveryTime, DEPO_EV_TICK, 380) == true);  // 只触发一次
}

static void test_open_during_recording_ignored_and_no_reask(void) {
    depo_ctx_t c; depo_init(&c);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_DOOR_OPEN, 0);
    CHECK(depo_step(&c, &kEveryTime, DEPO_EV_TICK, 300) == true);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_RECORD_STARTED, 310);
    CHECK(depo_step(&c, &kEveryTime, DEPO_EV_DOOR_OPEN, 5000) == false); // 录音中开门
    (void)depo_step(&c, &kEveryTime, DEPO_EV_RECORD_DONE, 8000);
    CHECK(c.state == DEPO_STATE_IDLE);
    CHECK(depo_step(&c, &kEveryTime, DEPO_EV_TICK, 9000) == false); // 门还开着，不重问
}

static void test_close_then_open_asks_again(void) {
    depo_ctx_t c; depo_init(&c);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_DOOR_OPEN, 0);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_TICK, 300);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_RECORD_STARTED, 310);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_RECORD_DONE, 8000);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_DOOR_CLOSE, 10000);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_DOOR_OPEN, 10100);
    CHECK(depo_step(&c, &kEveryTime, DEPO_EV_TICK, 10400) == true); // 新的一次开门再问
}

static void test_throttle_config_still_available(void) {
    const depo_config_t throttled = {300, 60000}; // 能力保留：10 分钟节流
    depo_ctx_t c; depo_init(&c);
    (void)depo_step(&c, &throttled, DEPO_EV_DOOR_OPEN, 0);
    CHECK(depo_step(&c, &throttled, DEPO_EV_TICK, 300) == true);
    (void)depo_step(&c, &throttled, DEPO_EV_RECORD_STARTED, 310); // 真实链路：触发后录音启动
    (void)depo_step(&c, &throttled, DEPO_EV_RECORD_DONE, 320);
    (void)depo_step(&c, &throttled, DEPO_EV_DOOR_CLOSE, 400);
    (void)depo_step(&c, &throttled, DEPO_EV_DOOR_OPEN, 1000);
    CHECK(depo_step(&c, &throttled, DEPO_EV_TICK, 1300) == false); // 被节流
    CHECK(c.state == DEPO_STATE_IDLE);
    (void)depo_step(&c, &throttled, DEPO_EV_DOOR_CLOSE, 2000);
    (void)depo_step(&c, &throttled, DEPO_EV_DOOR_OPEN, 70000);
    CHECK(depo_step(&c, &throttled, DEPO_EV_TICK, 70300) == true); // 间隔过了再问
}

static void test_ask_recovers_when_record_never_starts(void) {
    // 录音启动失败（RECORD_STARTED 丢失）→ RECORD_DONE 兜底回 IDLE，不能死锁
    depo_ctx_t c; depo_init(&c);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_DOOR_OPEN, 0);
    CHECK(depo_step(&c, &kEveryTime, DEPO_EV_TICK, 300) == true);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_RECORD_DONE, 400); // 没有START，直接DONE
    CHECK(c.state == DEPO_STATE_IDLE);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_DOOR_CLOSE, 500);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_DOOR_OPEN, 600);
    CHECK(depo_step(&c, &kEveryTime, DEPO_EV_TICK, 900) == true); // 后续开门仍能正常问
}

static void test_pending_cancelled_by_close(void) {
    depo_ctx_t c; depo_init(&c);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_DOOR_OPEN, 0);
    (void)depo_step(&c, &kEveryTime, DEPO_EV_DOOR_CLOSE, 100);
    CHECK(depo_step(&c, &kEveryTime, DEPO_EV_TICK, 1000) == false); // 去抖中关门取消
    CHECK(c.state == DEPO_STATE_IDLE);
}

int main(void) {
    test_single_open_fires_once_after_debounce();
    test_bounce_yields_single_trigger();
    test_open_during_recording_ignored_and_no_reask();
    test_close_then_open_asks_again();
    test_throttle_config_still_available();
    test_ask_recovers_when_record_never_starts();
    test_pending_cancelled_by_close();
    if (g_fail) { printf("[door_event_policy] %d assertion(s) FAILED\n", g_fail); return 1; }
    printf("[door_event_policy] all green\n");
    return 0;
}
