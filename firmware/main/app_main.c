#include <stdio.h>

/* 装配层：只做初始化与启动，业务逻辑一律在 components/。
 * TODO(Step 3)：platform_init（I2S/按键/霍尔/Wi-Fi）→ 服务装配。 */
void app_main(void) {
    printf("[recording-bean] boot ok (skeleton v0)\n");
}
