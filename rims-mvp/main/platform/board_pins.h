#pragma once
/* RIMS 录音豆 MVP 引脚表 —— EasyInput V2 板（ESP32-S3）临时载体。
 * 所有数值抄自 components/keyboard/include/keyboard/board_pins.h 的
 * EASY_INPUT_BOARD_V2 分支（原理图事实），不得另行发明。
 * C3 录音豆（最终形态）到货后另建板型，本表作废但不迁移。
 * 硬件红线见 easy-input-maker/docs/hardware/easyinput-v2-safety.md。
 */
#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int periph_power;          /* 外设共电 GPIO8，高有效：LED/麦/喇叭共享 */
    int record_button;         /* KEY1=GPIO2，录音键，低有效 */
    int sim_door_open_button;  /* KEY2=GPIO47，模拟开门事件（板上无霍尔） */
    int mic_sck;               /* INMP441 BCLK=9 */
    int mic_ws;                /* WS=10 */
    int mic_sd;                /* DATA IN=11 */
    int spk_bclk;              /* 喇叭 BCLK=14 */
    int spk_ws;                /* WS=13 */
    int spk_sd;                /* DATA OUT=15 */
    int ws2812;                /* GPIO12，状态灯（可选） */
    int boot0;                 /* GPIO0=BOOT，固定 */
    int usb_dm;                /* GPIO19，固定 */
    int usb_dp;                /* GPIO20，固定 */
} bean_pins_t;

extern const bean_pins_t kBeanPins;

#ifdef __cplusplus
}
#endif
