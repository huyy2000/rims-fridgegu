#include "board_pins.h"

/* 数值 = EasyInput V2 原理图事实，改这里之前先对 keyboard 组件 board_pins.h */
const bean_pins_t kBeanPins = {
    .periph_power = 8,
    .record_button = 2,
    .sim_door_open_button = 47,
    .mic_sck = 9,
    .mic_ws = 10,
    .mic_sd = 11,
    .spk_bclk = 14,
    .spk_ws = 13,
    .spk_sd = 15,
    .ws2812 = 12,
    .boot0 = 0,
    .usb_dm = 19,
    .usb_dp = 20,
};
