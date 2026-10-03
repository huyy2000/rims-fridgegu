// 引脚分配守卫测试：引脚表是硬件合同，改错任何一位在这里先红
#include <cstdio>
#include <cstdlib>
#include "board_pins.h"

static int g_fail = 0;
#define CHECK(cond) do { \
    if (!(cond)) { printf("  FAIL line %d: %s\n", __LINE__, #cond); ++g_fail; } \
} while (0)

int main(void) {
    const bean_pins_t &p = kBeanPins;

    // 1) 所有外设引脚互不冲突
    int used[] = {
        p.record_button, p.hall_sensor,
        p.mic_sck, p.mic_ws, p.mic_sd,
        p.spk_bclk, p.spk_lrc, p.spk_din,
        p.status_led, p.boot_button, p.usb_dm, p.usb_dp,
    };
    const int n = (int)(sizeof(used) / sizeof(used[0]));
    for (int i = 0; i < n; ++i) {
        for (int j = i + 1; j < n; ++j) {
            CHECK(used[i] != used[j]);
        }
    }

    // 2) 固定引脚（C3 芯片事实，不可协商）
    CHECK(p.boot_button == 9);   // C3 BOOT
    CHECK(p.usb_dm == 18);
    CHECK(p.usb_dp == 19);

    // 3) 不得占用 Flash（GPIO11~17）与未引出的 GPIO12+
    for (int i = 0; i < n; ++i) {
        CHECK(!(used[i] >= 11 && used[i] <= 17));
        CHECK(used[i] >= 0 && used[i] <= 21);
    }

    // 4) 按键与霍尔不许落在 strapping 脚（GPIO2/8/9），
    //    防止上电瞬间外部器件把 strapping 拉偏进错误启动模式
    CHECK(p.record_button != 2 && p.record_button != 8 && p.record_button != 9);
    CHECK(p.hall_sensor != 2 && p.hall_sensor != 8 && p.hall_sensor != 9);

    // 5) 两条 I2S 总线互不共享引脚（已由 1) 覆盖，此处表达意图）
    CHECK(p.mic_sck != p.spk_bclk);

    if (g_fail) { printf("[board_pins] %d assertion(s) FAILED\n", g_fail); return 1; }
    printf("[board_pins] all green\n");
    return 0;
}
