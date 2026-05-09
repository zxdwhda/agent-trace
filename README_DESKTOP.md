# AgentTrace Desktop

AgentTrace 的桌面端应用 —— 基于 Tauri 2 的轻量监控面板，实时追踪 AI IDE 会话、Token 消耗和提示词优化建议。

![Dashboard](docs/assets/dashboard.png)

## 功能特性

| 页面 | 功能 |
|------|------|
| **Dashboard** | 实时统计卡片 + Token 趋势图 + 模型分布饼图 |
| **Sessions** | 活跃/历史会话列表 + 调用链详情 |
| **Live** | WebSocket 实时事件流 |
| **Import** | 批量导入历史会话（按日期范围筛选，自动去重）|
| **Skills** | 各 Skill 使用频率、Token 占比分析 |
| **Prompts** | 智能提示词优化建议（启发式本地分析）|
| **Settings** | CozeLoop 配置持久化（官方/开源/双平台）|

## 快速开始（macOS）

### 方式一：一键安装脚本

```bash
# 1. 克隆项目
git clone https://github.com/yourname/agent-trace.git
cd agent-trace

# 2. 运行安装脚本
./scripts/setup-mac.sh

# 3. 打开应用
open src-tauri/target/release/bundle/macos/AgentTrace.app
```

### 方式二：手动安装

**依赖要求：**
- Python 3.9+
- Rust 1.70+
- Node.js 20+
- pnpm 9+

```bash
# 1. 安装 Python 依赖
pip install -e ".[desktop]"

# 2. 安装前端依赖
cd web && pnpm install

# 3. 构建前端
pnpm build

# 4. 构建并运行桌面端
cd ../src-tauri
cargo tauri dev
```

## CozeLoop 配置

打开应用后，在 **Settings** 页面配置：

| 配置项 | 说明 |
|--------|------|
| Mode | `official` (官方), `opensource` (开源), `dual` (双写) |
| Workspace ID | CozeLoop 工作区 ID |
| API Token | CozeLoop API Token |
| Open Source URL | 开源版 CozeLoop 地址（默认 `http://localhost:8082`）|

配置会自动保存到 `~/.agent_trace/config.json`。

## 批量导入历史数据

1. 进入 **Import** 页面
2. 选择日期范围（默认最近 7 天）
3. 点击 **Preview** 预览可导入的会话
4. 点击 **Import Now** 执行导入

导入过程会自动去重：已存在于数据库中的 session 会被跳过。

## 技术栈

- **壳层**: Tauri 2 (Rust)
- **前端**: React 18 + TypeScript + Vite + TailwindCSS + shadcn/ui + Recharts
- **后端**: Python FastAPI + uvicorn
- **数据**: SQLite (metrics.db)

## 项目结构

```
agent-trace/
├── src-tauri/          # Tauri Rust 项目
│   ├── src/main.rs     # 入口：窗口管理 + Python sidecar
│   └── Cargo.toml
├── web/                # React 前端
│   ├── src/
│   │   ├── components/ # 页面组件
│   │   ├── lib/api.ts  # API 客户端
│   │   └── App.tsx
│   └── package.json
├── src/agent_trace/    # Python 核心
│   ├── web/            # FastAPI 服务器
│   │   ├── server.py
│   │   ├── metrics_store.py
│   │   └── api/        # API 路由
│   └── core/           # 监控逻辑
└── scripts/
    └── setup-mac.sh    # macOS 安装脚本
```

## 自动构建

每次推送到 `main` 分支或打 tag 时，GitHub Actions 会自动构建：
- macOS: `.dmg` (Universal)
- Windows: `.msi`
- Linux: `.AppImage`

构建产物可在 [Actions 页面](../../actions) 下载。

## 许可证

MIT License
