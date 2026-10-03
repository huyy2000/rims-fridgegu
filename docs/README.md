# docs/ —— 集中内容层

项目需要统一查找的**实际内容产出**写在这里:产品需求、调研、架构、跨模块契约、设计说明、评审和交付说明……

- 单仓多子项目仍共用这一份根级 `docs/`,按需建 `product/`、`architecture/`、`contracts/`、`modules/<module>/`、`reviews/` 等子目录。
- 控制层(charter / plan / 任务卡 / 交接卡)不放这里,放 `flow/`。
- 子项目目录默认放代码、测试和构建配置,不主动重复建立文档体系。
- 已有 README、生成文档或必须紧贴代码维护的说明可以留在子项目里;在下方索引其真实路径,不要为了集中而搬动。
- 判据:需要**统一发现的知识、方案和交付说明** → 根级 `docs/`;**协调 / 推进项目** → 根级 `flow/`;代码 → 对应子项目。

## 局部文档索引

- `冰箱菇_产品定义_v4.md`(根目录) — **现行产品定义**:三件套 + 交互总纲 5 条 + 云栈(2026-10-01 拍板)
- `作业-冰箱菇-第八课毕业大作业.md`(根目录) — 第八课毕业大作业交付文档(0→1 七环节)
- `docs/hardware/冰箱菇-硬件总览.md` — 三件套连接图 / 无线设计 / 单件门磁双方案 / 功耗预算 / 风险清单
- `docs/hardware/冰箱菇-BOM-v0-2026-10-01.md` — 三件套 BOM(标日期 / 采购防呆清单)
- `docs/patent/` — 专利包(墨水屏+吸附同步实施例;产品转向后不受实施例约束,见 decisions D-6;**公开发布时必须剔除**)
- `录音豆_需求与开发计划_v3.md` — 历史参考(v3 单豆形态,已被 v4 取代)
- `firmware/AGENTS.md` — 固件分层铁律 / 验证命令 / 硬件红线(C3)
- `firmware/docs/hardware/recording-bean-safety.md` — C3 豆硬件安全文档(2026-10-01 修订三处数据手册错误)
- `fridgepal/AGENTS.md` — 后端局部规则
- `fridgepal/README.md` — 后端本地开发入口
- `fridgepal/web/index.html` — 展示软件(本地 http://127.0.0.1:8000/web/)
- `rims-mvp/README.md` — MVP 固件(键盘板)入口与构建命令(已迁入本仓库)
- `tools/_github_publish.sh`(仓库外) — GitHub 公开发布脚本(自动剔除 docs/patent)
- 待建:`docs/contracts/` — 固件↔后端 API schema(inventory_payload wire test 的契约真相源,Step 2 时补)
