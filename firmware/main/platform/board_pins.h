#pragma once
/* 录音豆 v0 引脚分配 · ESP32-C3 SuperMini
 * 红线与 strapping 说明见 docs/hardware/recording-bean-safety.md。
 * C3 的 GPIO11~17 被 Flash 占用；GPIO9=BOOT、GPIO8=板载 LED（SuperMini）。
 * 每次改这里必须同步 host_test/board_pins_tests.cpp 和安全文档。
 */
#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int record_button; /* 录音键，低有效，内部上拉，下降沿中断 */
    int hall_sensor;   /* 霍尔 AH3144，开漏低有效，外部上拉 10k，下降沿中断 */
    int mic_sck;       /* INMP441 SCK */
    int mic_ws;        /* INMP441 WS */
    int mic_sd;        /* INMP441 SD */
    int spk_bclk;      /* MAX98357A BCLK */
    int spk_lrc;       /* MAX98357A LRC */
    int spk_din;       /* MAX98357A DIN */
    int status_led;    /* 板载 LED（GPIO8，低有效视模组批次而定） */
    int boot_button;   /* 固定 GPIO9，下载模式 */
    int usb_dm;        /* 固定 GPIO18 */
    int usb_dp;        /* 固定 GPIO19 */
} bean_pins_t;

extern const bean_pins_t kBeanPins;

#ifdef __cplusplus
}
#endif
