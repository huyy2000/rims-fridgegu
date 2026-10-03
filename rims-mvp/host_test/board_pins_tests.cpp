// RIMS MVP 引脚守卫：数值必须与 keyboard 组件的 EASY_INPUT_BOARD_V2 一致
#include <cstdio>
#include "board_pins.h"

static int g_fail = 0;
#define CHECK(cond) do { \
    if (!(cond)) { printf("  FAIL line %d: %s\n", __LINE__, #cond); ++g_fail; } \
} while (0)

int main(void) {
    const bean_pins_t &p = kBeanPins;

    // 1) 外设引脚互不冲突
    int used[] = {
        p.periph_power, p.record_button, p.sim_door_open_button,
        p.mic_sck, p.mic_ws, p.mic_sd,
        p.spk_bclk, p.spk_ws, p.spk_sd,
        p.ws2812, p.boot0, p.usb_dm, p.usb_dp,
    };
    const int n = (int)(sizeof(used) / sizeof(used[0]));
    for (int i = 0; i < n; ++i) {
        for (int j = i + 1; j < n; ++j) {
            CHECK(used[i] != used[j]);
        }
    }

    // 2) V2 原理图固定事实（回归保护：改错一位立即红）
    CHECK(p.periph_power == 8);   // LED/麦/喇叭共享电源域，高有效
    CHECK(p.boot0 == 0);          // BOOT
    CHECK(p.usb_dm == 19 && p.usb_dp == 20);
    CHECK(p.mic_sck == 9 && p.mic_ws == 10 && p.mic_sd == 11);
    CHECK(p.spk_bclk == 14 && p.spk_ws == 13 && p.spk_sd == 15);
    CHECK(p.ws2812 == 12);

    // 3) 录音键与模拟开门键不得落在固定功能脚上
    CHECK(p.record_button != p.periph_power && p.record_button != p.boot0);
    CHECK(p.sim_door_open_button != p.periph_power && p.sim_door_open_button != p.boot0);

    if (g_fail) { printf("[board_pins] %d assertion(s) FAILED\n", g_fail); return 1; }
    printf("[board_pins] all green\n");
    return 0;
}
