# fridgepal · 局部协作约定(Claude Code / Codex 共用入口)

> 本文件只适用于 `fridgepal/` 及其子目录。
> 总体项目合同见 `../AGENTS.md`;总体计划、交接和文档分别见 `../flow/`、`../docs/`。
> 同目录 `CLAUDE.md` 指向本文件,两个工具读取同一份局部规则。

## 职责边界

- **负责**:录音豆云端链路——录音接收、ASR、LLM 整理(库存/购物清单)、库存数据存储、公众号图片卡片推送、设备模拟器。
- **不负责**:固件采集与上传逻辑(→ `firmware/` 或 rims-mvp);公众号卡片视觉模板的最终定稿由需求文档拍板。
- **输入 / 依赖**:固件上传的录音/事件;`录音豆_需求与开发计划_v3.md` 的功能定义。
- **输出 / 对外契约**:设备上传 API 与库存 schema(将沉淀到 `../docs/contracts/`,固件侧 `inventory_payload` 组件按它做 wire test)。

## 本模块入口

- **源码**:`backend/`(FastAPI)
- **测试 / 运行**:`README.md`;Mock LLM 链路当前已能跑通,`scripts/` 含设备模拟器
- **关键配置**:`backend/app/`(models / services / api)

## 局部约束

- 跨模块约定(上传协议、schema 变更)写入根级 `../docs/contracts/`,并同步受影响模块的局部入口。
- 总体目标、计划、任务卡、决策、问题和交接只写根级 `../flow/`,不在本模块重复建立控制层。

## 局部知识(durable,随模块积累)

- Mock LLM 先行:云端链路不依赖真实模型 key 就能整链路验证(见 `backend/app/services/llm_service.py`)。
