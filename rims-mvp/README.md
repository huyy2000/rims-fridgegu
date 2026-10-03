# rims-mvp — 冰箱菇 MVP 固件（EasyInput V2 板临时载体）

> 现行真相源 = 本目录（RIMS 仓库内）。`easy-input-maker` 仓 `rims-mvp` 分支的 worktree 为历史骨架（2026-10-02 起本目录为准）。
> 产品定义：`../冰箱菇_产品定义_v4.md` · 硬件红线：`../docs/hardware/冰箱菇-硬件总览.md`

## 已实现（v1 业务固件）

- **交互**（对应产品定义 §三 交互总纲）：
  - **KEY2（GPIO47，模拟开门）** → 从云端拉取 TTS 问句「拿了什么？」→ 喇叭播放 → 录 6 秒 → multipart 上传 → 播报菇菇回复；
  - **KEY1（GPIO2，拍键）** → 录 6 秒 → 上传 → 播报回复。
- **SoftAP 配网**：首次开机开热点 `fridgegu-XXXX`，浏览器访问 `http://192.168.4.1` 填 Wi-Fi + 后端地址（如 `http://192.168.1.10:8000`），保存后重启连网。
- **硬件事实引用**：I2S 配置逐项对照 keyboard 固件同板验证代码（喇叭 Philips/16bit/LEFT@14/13/15；麦克风 MSB/32bit/RIGHT@9/10/11）；GPIO8 共电域录/放前开、用完即关，不反复拉低。

## 目录

```
rims-mvp/
├── CMakeLists.txt / partitions.csv / sdkconfig.defaults   # 16MB Flash + Octal PSRAM（依板级事实）
├── components/door_event_policy/   # 纯逻辑：开门→询问→录音状态机（host 可测）
├── main/
│   ├── app_main.c                  # 装配与业务编排（KEY1/KEY2 流程）
│   ├── wifi_prov.c/.h              # SoftAP 配网 + NVS + STA 连接
│   ├── cloud_client.c/.h           # GET TTS（PSRAM 缓冲）/ multipart 上传
│   ├── audio_player.c/.h           # WAV 解析 → I2S TX + GPIO8 租约
│   ├── audio_recorder.c/.h         # I2S RX → PSRAM（15s 上限）→ PCM
│   ├── buttons.c/.h                # 低有效按键 + 30ms 消抖队列
│   └── platform/board_pins.*       # 引脚表 = V2 原理图事实（守卫测试锁定）
└── host_test/                      # cmake -S host_test -B build-host …（2/2 通过）
```

## 验证命令

### 宿主测试（winlibs mingw64 + ninja）

```
cmake -S host_test -B build-host -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build build-host
ctest --test-dir build-host --output-on-failure     # 期望 2/2
```

### 固件构建（ESP-IDF 5.5.5 / esp32s3）

本机沙箱会向子进程注入 MSYSTEM 且 `env -u` 派生的进程 stdout 静默丢失——用包装器（本进程内清环境后 runpy 执行 idf.py）：

```
C:/Espressif/tools/python/python.exe  D:/easy-input/tools/_idf_build.py  -B build set-target esp32s3
C:/Espressif/tools/python/python.exe  D:/easy-input/tools/_idf_build.py  -B build build
```

**烧录**：会覆盖板上固件——先验明设备（esp-idf-cy 流程），经使用者确认后执行；进/出下载模式遵守《EasyInput V2 硬件安全边界》（开机短按松开一次 BOOT 进入；恢复=关机再开机）。

## 红线（继承 easy-input-maker AGENTS.md）

- GPIO8 是 LED/麦/喇叭共享高有效电源域，不许反复拉低；
- 设备身份、HID、BLE、键盘业务代码不动；
- 证据分层：host 测试 ≠ idf.py build ≠ 烧录 ≠ 实板功能，报告分开说。
