# RIMS 录音豆 · AGENTS.md

> 改代码前必读。本文件继承 easy-input-maker 的工程铁律，按录音豆（ESP32-C3）适配。

## 分层铁律

- **纯逻辑放 `components/<名字>/`**：同步/状态机/协议/策略，一律 C 语言、无任何 ESP-IDF 头文件依赖，必须能被 `host_test/` 在电脑上编译运行。
- **硬件适配放 `main/platform/`**：I2S、GPIO、Wi-Fi、Flash 分区等所有与芯片相关的东西只许出现在这里。
- `main/app_main.c` 只做装配（初始化平台层 → 启动服务），不写业务逻辑。

## 验证命令（默认）

```bash
# host_test（Windows 本机需显式指定 winlibs 工具链，原因见 ../flow/踩坑记录.md）
W=D:/easy-input/tools/winlibs/mingw64/bin
cmake -S host_test -B build-host -G Ninja -DCMAKE_MAKE_PROGRAM=$W/ninja.exe \
  -DCMAKE_C_COMPILER=$W/gcc.exe -DCMAKE_CXX_COMPILER=$W/g++.exe -DCMAKE_BUILD_TYPE=Debug
cmake --build build-host
ctest --test-dir build-host --output-on-failure
idf.py build        # 需要 eim 激活的 ESP-IDF 5.5.5 环境，target=esp32c3
```

## 证据分层（不可互相替代）

**静态检查 ≠ 测试通过 ≠ 构建成功 ≠ 烧录成功 ≠ 实板功能正常。**
报告进度时必须分开说清楚到哪一层，禁止用「测试过了」代表「板上能跑」。

## 烧录红线

烧录不可逆：**必须用户明确授权并确认目标设备后才执行，绝不自动烧录。**

## 硬件红线

见 `docs/hardware/recording-bean-safety.md`。速记：
- ESP32-C3 的 **GPIO11~17 被 Flash 占用**，不可接外设。
- **GPIO9 = BOOT**（下载模式用），**GPIO8 = 板载 LED**；GPIO2/8/9 是 strapping 脚，不许接上电时被强行拉低的器件。
- 每次改引脚分配必须同步 `main/platform/board_pins.h` + `host_test/board_pins_tests.cpp`，并更新安全文档。

## flow/ 治理

控制层已上移根级:`D:\easy-input\RIMS\flow\`(2026-09-28 接入 project-flow-cy,见根 decisions D-7)。本目录**不再维护局部 flow/**。
写入 flow/ 的内容一律视为将公开发布:不记内部讨论、隐私、凭据、原始串口日志。
产品需求与云端后端在 `RIMS/` 上一级目录(`录音豆_需求与开发计划_v3.md`、`fridgepal/`)。

## 环境

- ESP-IDF 5.5.5（`C:\esp`），`eim_config.toml` 在本目录，target=esp32c3。
- 宿主机 Windows + Git Bash；host_test 只依赖系统 cmake + C/C++ 编译器，无第三方测试框架。

<!-- project-flow-cy:start -->
## 协作约定(project-flow-cy)
- 总体项目合同:`../AGENTS.md`(根级,CLAUDE.md 同源);总体计划/交接/决策/踩坑:`../flow/`。
- 本文件只写固件模块的局部规则;跨模块契约(如与后端的 API schema)写根级 `docs/contracts/`。
- 收工交接在根级 `../flow/进展.md` 顶部追加,不在本模块记进展。
<!-- project-flow-cy:end -->
