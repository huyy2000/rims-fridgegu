# FridgePal 智能冰箱贴 — 代码仓库

> 对应《智能冰箱贴_开发计划_v2.md》的 M1 行走骨架起步。
> 当前进度：**后端骨架 + 模拟设备已可运行**（本地 SQLite + Mock LLM，不需要任何 API Key）。

## 目录结构

```
fridgepal/
├── backend/                 # 云端后端（FastAPI）
│   ├── app/
│   │   ├── main.py          # 入口
│   │   ├── config.py        # 配置（.env 可覆盖）
│   │   ├── db.py            # 数据库连接
│   │   ├── models.py        # 表结构（用户/设备/库存/日志/清单）
│   │   ├── schemas.py       # 请求/响应模型
│   │   ├── api/             # 路由：device / inventory / shopping / ai
│   │   └── services/        # 业务：llm_service（Mock） / inventory_service
│   ├── tests/               # 冒烟测试
│   └── requirements.txt
├── scripts/
│   ├── init_db.py           # 初始化数据库
│   └── device_simulator.py  # 模拟设备（命令行"说话"）
└── README.md
```

## 快速开始（5 分钟跑起来）

```powershell
# 1) 进入 backend 目录
cd fridgepal\backend

# 2) 创建虚拟环境并安装依赖（只需一次）
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3) 初始化数据库（生成 fridgepal.db）
python ..\scripts\init_db.py

# 4) 启动后端
uvicorn app.main:app --reload

# 5) 打开浏览器看接口文档：http://127.0.0.1:8000/docs
```

## 模拟设备"说话"

新开一个终端（保持后端运行）：

```powershell
cd fridgepal\scripts
python device_simulator.py
```

然后输入，例如：

```
你说> 放了两盒牛奶、一袋鸡蛋大概30个、一块五花肉
你说> 冰箱里有什么
你说> 牛奶喝完了
```

每句都会走一遍「LLM 解析 → 库存更新 → 回复」的完整链路（当前是 Mock 规则解析，后面接 DeepSeek 后换成真 LLM）。

## 跑测试

```powershell
cd fridgepal\backend
.\.venv\Scripts\Activate.ps1
pytest
```

## Windows 中文显示小提示

如果终端里中文变成乱码（``å·²è®°å½`` 这类），是因为 PowerShell 默认用 GBK 显示 UTF-8。在终端先执行：

```powershell
chcp 65001
```

再跑上面的命令即可正常显示中文。（浏览器里的 `/docs` 接口文档不受影响。）

## 交付形态：双击即用的后台管理系统（exe）

无需装 Python——打包成单个文件夹的 exe：

```powershell
cd fridgepal\backend
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --name fridgegu-admin --icon app_icon.ico --add-data "../web;web" --collect-all uvicorn --collect-all dashscope --hidden-import greenlet fridgegu_admin.py
copy .env dist\fridgegu-admin\.env   # 密钥配置随包走（.env 不入 git）
```

- 双击 `dist\fridgegu-admin\fridgegu-admin.exe`：启动服务 + 自动打开管理界面；**关闭窗口即停服务**；
- 数据（`fridgepal.db` / `uploads\` / `.env`）都在 exe 同目录，整文件夹拷走即完成备份迁移；
- 端口默认 8000，可用环境变量 `FRIDGE_GU_PORT` 覆盖；局域网设备（键盘板）用 `http://<本机IP>:8000` 访问。

## 当前状态（2026-10-02）

| 项 | 状态 |
|----|------|
| 数据库 | SQLite（零安装；上线前可换 PostgreSQL） |
| LLM | ✅ DeepSeek Function Call（真模型；mock 规则解析保留为兜底 fallback） |
| ASR/TTS | ✅ 阿里云百炼 DashScope（paraformer-realtime-v2 + cosyvoice-v2 + 热词表） |
| 微信 | ✅ 测试号回调验签 + 消息记账 + 推送接口（绑定已提交） |
| 位置智能 | ✅ 常识库自动分类 + 明说覆盖（D-12）；传感器分区归属方案见硬件总览 |
| 设备鉴权 | 简易 token（MVP），正式发布前换 device token + JWT |
