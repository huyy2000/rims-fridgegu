# 冰箱菇 · RIMS 🍄

> Recording & Inventory Mushroom System —— 贴在冰箱上的语音记账"蘑菇家族"

**一句话**：拍大蘑菇随手记，开门它主动问，AI 把冰箱管起来，微信卡片一眼看清。

这是 WaytoAGI 第七期 AI 硬件基础训练营的**毕业作品**（第八课）：
- **产品定义**：[冰箱菇_产品定义_v4.md](冰箱菇_产品定义_v4.md)（三件套：基座大蘑菇 + 录音豆小蘑菇 + 单件门磁超小蘑菇）
- **毕业作业文档**：[作业-冰箱菇-第八课毕业大作业.md](作业-冰箱菇-第八课毕业大作业.md)（0→1 七环节 + 设计亮点 + 证据分层）
- **硬件真相源**：[docs/hardware/](docs/hardware/)（总览、BOM、安全文档，均标日期）
- **后端 + 展示软件**：[fridgepal/](fridgepal/)（FastAPI：语音→ASR→替换规则→LLM→库存→卡片；web 五页管理界面）
- **固件**：[rims-mvp/](rims-mvp/)（ESP-IDF 5.5.5 / ESP32-S3：SoftAP 配网、I2S 录音、TTS 播放、VAD 静音收音、6 键交互、WS2812 状态灯）

## 方法

资料先行（原理图/GPIO/BOM 标日期）→ AI 协同（给边界给真相源给验收标准）→ 真机验证（证据分层：静态检查 ≠ 测试 ≠ 构建 ≠ 烧录 ≠ 实板）→ 软硬件迭代。

## 快速跑起来

```powershell
cd fridgepal/backend
python -m venv .venv && .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --port 8000
# 浏览器打开 http://127.0.0.1:8000/web/
```

固件构建、烧录与恢复见 [rims-mvp/README.md](rims-mvp/README.md)。

## 许可

[PolyForm Noncommercial 1.0.0](LICENSE) —— 个人学习与非商业使用免费，商用需授权。
