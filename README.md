# AgentTrace

🚀 **AI IDE 会话监控与 Trace 上报工具**

将 Kimi Code CLI、Claude Code 等 AI IDE 的会话数据自动上报到 Coze 罗盘进行观测和分析。

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

---

## 📋 功能特性

### ✅ 当前版本 v0.3.4

| 特性 | 状态 | 说明 |
|-----|------|------|
| Kimi Code CLI 监控 | ✅ | 完整的 Wire 协议支持 |
| 事件去重 | ✅ | 三层去重机制（内存+SQLite） |
| Offset 持久化 | ✅ | 进程重启不丢数据 |
| 文件指纹检测 | ✅ | 防止 inode 复用问题 |
| 开机自启动 | ✅ | macOS/Linux/Windows 全支持 |
| Trace 层级结构 | ✅ | agent → model → tool 正确嵌套 |
| **TraceContext 管理** | ✅ **v0.3.4 新增** | trace_id/run_id/turn_id 完整追踪 |
| **Span 类型体系** | ✅ **v0.3.4 新增** | entry/prompt/gateway 等 9 种类型 |
| **gen_ai.* 标准** | ✅ **v0.3.4 新增** | OpenTelemetry 兼容的 Token 追踪 |
| **Runtime 信息** | ✅ **v0.3.4 新增** | 动态 Agent 类型检测 |
| **Gateway Span** | ✅ **v0.3.4 新增** | 服务级别可观测性 |
| Claude Code 监控 | 🚧 | v0.5.0 开发中 |

### 🔄 与 OpenClaw 官方实现对齐

AgentTrace v0.3.4 参考扣子官方 [OpenClaw CozeLoop Trace 插件](https://www.coze.cn/docs/developer_guides/openclaw_cozeloop_trace) 进行了深度重构，实现与官方 OpenClaw 同等级别的 Trace 上报能力：

| 功能 | OpenClaw 官方插件 | AgentTrace (v0.3.4) |
|------|------------------|---------------------|
| **Trace 层级结构** | `openclaw_request` → `agent` → `model` → `tool` | ✅ `entry` → `agent` → `model` → `tool` |
| **Span 类型** | entry, prompt, model, tool, gateway... | ✅ 9 种类型完整对齐 |
| **Token 追踪** | `gen_ai.usage.*` 标准属性 | ✅ OpenTelemetry 兼容 |
| **上下文管理** | `trace_id`/`run_id`/`turn_id` | ✅ TraceContext 完整实现 |
| **Runtime 信息** | 自动检测 OpenClaw 版本和环境 | ✅ 动态 Agent 类型检测 |
| **Gateway 监控** | 网关级别服务监控 | ✅ Gateway Span 实现 |
| **逐步上报** | 已完成节点先上报 | ✅ 实时上报机制 |
| **目标平台** | CozeLoop 罗盘 | ✅ CozeLoop 罗盘 |

**应用场景对比**:

| 应用场景 | OpenClaw | AgentTrace |
|----------|----------|------------|
| **Token 消耗统计** | 观测 > 统计页面查看模型 Token 消耗 | ✅ 同样支持，按模型维度统计 |
| **问题排查** | All Span 视图实时跟进执行状态 | ✅ 同样支持，实时查看 Tool 调用链 |
| **工具调用分析** | 查看 read/write 等 tool 的执行详情 | ✅ 支持 Shell/Glob/ReadFile 等所有工具 |
| **多轮对话追踪** | 通过 `turn_id` 区分多轮 | ✅ 同样支持 `turn_id` 递增 |

**AgentTrace 的独特优势**:
- 🎯 **多 IDE 支持**: 不仅支持 Kimi CLI，还可扩展支持 Claude Code 等其他 AI IDE
- 🔄 **去重机制**: 三层去重（内存+SQLite），防止重复上报
- 💾 **断点续传**: Offset 持久化，重启后从断点继续
- 🚀 **开机自启**: 跨平台自启动支持（macOS/Linux/Windows）

---

## 📚 文档导航

| 文档 | 说明 | 适合人群 |
|------|------|----------|
| [📖 使用指南](README.md) | 本文件，快速上手 | 所有用户 |
| [🏗️ 架构设计](docs/ARCHITECTURE.md) | 系统架构与技术选型 | 开发者、架构师 |
| [⚙️ 实现细节](docs/DESIGN.md) | 去重机制、持久化实现 | 开发者、贡献者 |
| [🤝 贡献指南](docs/CONTRIBUTING.md) | 开发环境、代码规范 | 贡献者 |
| [📖 API 文档](docs/API.md) | Python API 和 CLI 参考 | 开发者 |
| [❓ 常见问题](docs/FAQ.md) | 故障排查、最佳实践 | 所有用户 |
| [🗺️ 版本规划](ROADMAP.md) | 版本路线图 | 关注项目进展者 |
| [📚 参考资料](REFERENCES.md) | 致谢与引用 | 研究者 |

---

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                         AgentTrace                               │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Kimi CLI     │    │ Claude Code  │    │ 其他 AI IDE  │      │
│  │ Wire JSONL   │    │ Stream JSON  │    │ (规划中)     │      │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│         │                   │                   │               │
│         ▼                   ▼                   ▼               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    统一事件解析层                        │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │   │
│  │  │ WireParser  │  │ClaudeParser │  │ 扩展解析器   │     │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘     │   │
│  └────────────────────────┬────────────────────────────────┘   │
│                           │                                     │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   去重与状态管理层                       │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │   │
│  │  │EventDeduplic│  │PersistentOff│  │SessionState │     │   │
│  │  │ator (L1/L2) │  │setStore     │  │             │     │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘     │   │
│  └────────────────────────┬────────────────────────────────┘   │
│                           │                                     │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                CozeLoop SDK 上报层                       │   │
│  │              支持 Trace/Span/Metrics                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📦 安装方法

### 从 PyPI 安装（推荐）

```bash
pip install agent-trace
```

### 从源码安装

```bash
git clone https://github.com/agenttrace/agent-trace.git
cd agent-trace
pip install -e .
```

### 开发模式安装

```bash
git clone https://github.com/agenttrace/agent-trace.git
cd agent-trace
pip install -e ".[dev]"
```

---

## ⚙️ 配置

### 环境变量

```bash
export COZELOOP_WORKSPACE_ID="your-workspace-id"
export COZELOOP_API_TOKEN="your-api-token"
export COZELOOP_API_BASE="https://api.coze.cn"  # 可选，默认为国内节点
```

### 可选配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `KIMI_SESSIONS_DIR` | `~/.kimi/sessions/` | Kimi 会话目录 |
| `KIMI_POLL_INTERVAL` | `2.0` | 轮询间隔（秒）|
| `KIMI_LOG_LEVEL` | `INFO` | 日志级别 |
| `KIMI_LOG_FILE` | `/tmp/agent-trace.log` | 日志文件路径 |

---

## 🚀 使用方法

### 方式一：命令行（推荐）

```bash
# 前台运行
agent-trace

# 或简写
atrace

# 指定日志级别
agent-trace --log-level DEBUG

# 守护进程模式
agent-trace --daemon
```

### 方式二：Python 模块

```bash
python -m agent_trace
```

### 方式三：开机自启动

```bash
# 安装自启动服务
agent-trace autostart install

# 检查状态
agent-trace autostart status

# 卸载自启动
agent-trace autostart uninstall
```

### 使用启动脚本

```bash
# 启动监控
./scripts/start.sh start

# 查看日志
./scripts/start.sh logs

# 停止监控
./scripts/start.sh stop

# 查看状态
./scripts/start.sh status

# 重启
./scripts/start.sh restart
```

---

## 📊 Trace 数据结构

### Span 层级关系（v0.3.4 更新）

```
session_entry (entry_span) - 请求入口
├── tags:
│   ├── session_id: "xxx"
│   ├── trace_id: "61ad2bed..." (32位)
│   └── entry_type: "user_request"
└── agent_turn (agent_span) [Runtime]
    ├── tags:
    │   ├── agent_type: "kimi_cli" (动态检测)
    │   ├── agent_version: "0.3.4"
    │   ├── run_id: "session_0_1773818952338"
    │   └── turn_index: "0"
    ├── prompt_1 (prompt_span)
    │   ├── input: {"user_input": "...", "step_n": 1}
    │   └── tags: {"prompt.type": "user_request"}
    └── step_1 (model_span) [gen_ai.* 属性]
        ├── set_input(): 用户输入
        ├── set_output(): 模型输出
        ├── set_model_name(): "kimi-k2"
        ├── set_input_tokens(): 1000
        ├── set_output_tokens(): 500
        ├── tags:
        │   ├── gen_ai.usage.input_tokens: 1000
        │   ├── gen_ai.usage.output_tokens: 500
        │   ├── gen_ai.usage.cache_read_tokens: 200
        │   ├── gen_ai.usage.total_tokens: 1500
        │   ├── gen_ai.provider.name: "moonshot"
        │   └── gen_ai.request.model: "kimi-k2"
        └── tool:Glob (tool_span)
            ├── set_input(): {"tool_name": "Glob", "arguments": {...}}
            └── set_output(): {"result": "..."}
```

**v0.3.4 新增特性**:
- **Entry Span**: 作为请求入口的根节点
- **Prompt Span**: 在每个 Step 前记录用户输入
- **Trace 标签**: `trace_id` 和 `run_id` 支持跨系统关联
- **Runtime 信息**: `agent_type` 动态检测（Kimi CLI / Claude Code）
- **gen_ai.***: OpenTelemetry 标准 Token 追踪属性

---

## 🔧 技术细节

> 💡 **深入了解更多技术细节**：
> - [架构设计文档](docs/ARCHITECTURE.md) - 系统架构、技术选型、数据流
> - [设计实现文档](docs/DESIGN.md) - 去重算法、持久化机制、文件指纹

### 事件去重机制

采用两层去重策略（参考了 LangSmith 和 OpenTelemetry 的设计）：

```
L1: Memory Cache (LRU, 10,000 items)
    └── 内存级快速去重，避免频繁查询数据库
    
L2: SQLite Persistent Store (WAL mode)
    └── 长期存储，进程重启后恢复
```

**详细原理**：👉 [DESIGN.md - 事件去重](docs/DESIGN.md#事件去重机制)

### Offset 持久化

参考 OTel FileLog Receiver 和 Fluent Bit 的实现：

```
┌─────────────────┐
│  File Watcher   │───▶ 监控 ~/.kimi/sessions/**/wire.jsonl
└─────────────────┘
         │
         ▼
┌─────────────────┐
│  JSONL Reader   │───▶ 增量读取，自动保存 offset
└─────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  PersistentOffsetStore      │
│  - offset: 文件读取位置     │
│  - inode: 文件 inode        │
│  - fingerprint: 文件指纹    │
│  - file_size: 文件大小      │
└─────────────────────────────┘
```

**详细原理**：👉 [DESIGN.md - Offset 持久化](docs/DESIGN.md#offset-持久化机制)

---

## 📁 项目结构

```
agent-trace/
├── src/
│   └── agent_trace/           # 主代码包
│       ├── __init__.py
│       ├── __main__.py        # 模块入口
│       ├── cli.py             # CLI 实现
│       ├── autostart/         # 开机自启动管理
│       ├── core/              # 核心模块
│       │   ├── dedup.py       # 事件去重管理器
│       │   ├── monitor.py     # 监控服务
│       │   ├── persistent_offset.py
│       │   └── session_state.py
│       ├── handlers/          # 事件处理器
│       ├── parsers/           # 解析器
│       └── utils/             # 工具模块
├── tests/                     # 测试目录
├── scripts/                   # 启动脚本
├── docs/                      # 文档
├── pyproject.toml             # 项目配置
├── README.md                  # 本文件
├── REFERENCES.md              # 参考资料
├── CHANGELOG.md               # 变更日志
└── LICENSE                    # 开源许可证
```

---

## 🗓️ 版本规划

### v0.3.4 (当前版本) - OpenClaw 生态对齐
- ✅ TraceContext 管理机制（trace_id/run_id/turn_id）
- ✅ Span 类型体系完善（entry/prompt/gateway 等 9 种）
- ✅ Token 追踪增强（gen_ai.* 标准属性）
- ✅ Runtime 信息设置（动态 Agent 类型检测）
- ✅ Gateway Span 服务级别追踪
- ✅ Entry → Agent → Prompt → Model → Tool 层级结构

### v0.3.3 (历史版本)
- ✅ Kimi Code CLI 完整支持
- ✅ 事件去重机制（L1 内存缓存 + L2 SQLite）
- ✅ Offset 持久化
- ✅ 开机自启动
- ✅ 修复事件 ID 生成问题
- ✅ 修复 TurnBegin 多轮对话处理
- ✅ 添加命令行安全警告
- ✅ 添加日志轮转（RotatingFileHandler）

### v0.5.0 (开发中) - Claude Code 支持
- 🚧 Claude Code stream-json 解析器
- 🚧 Claude 事件处理器
- 🚧 双模式监控（同时支持 Kimi + Claude）

### v0.6.0 (规划中)
- ⏳ Cursor/Windsurf 支持
- ⏳ Web Dashboard 监控面板
- ⏳ 自定义指标上报

查看完整的版本规划：[ROADMAP.md](ROADMAP.md)

---

## 🤝 贡献指南

欢迎提交 Issue 和 PR！

📖 **详细的贡献指南请查看**：[CONTRIBUTING.md](docs/CONTRIBUTING.md)
- 开发环境搭建
- 代码规范要求
- 提交流程说明
- 测试要求

### 快速开始

```bash
# 1. Fork 仓库
# 2. 克隆到本地
git clone https://github.com/yourusername/agent-trace.git

# 3. 创建分支
git checkout -b feature/your-feature

# 4. 安装开发依赖
pip install -e ".[dev]"

# 5. 运行测试
pytest

# 6. 代码格式化
black src tests
ruff check src tests
mypy src

# 7. 提交修改
git commit -am "Add some feature"

# 8. 推送分支
git push origin feature/your-feature

# 9. 创建 Pull Request
```

### 代码规范

- 遵循 PEP 8 规范
- 使用 black 格式化（行宽 100）
- 使用 ruff 检查代码
- 添加类型注解
- 编写 docstring

---

## 📄 开源许可证

本项目采用 [MIT 许可证](LICENSE)。

---

## 📚 参考资料

本项目在开发过程中参考了众多开源项目和技术文档，详见 [REFERENCES.md](REFERENCES.md)。

---

## 🙏 致谢

- [Coze 罗盘](https://loop.coze.cn) - 强大的 AI 应用观测平台
- [Kimi Code CLI](https://kimi.moonshot.cn) - 优秀的 AI 编程助手
- [Claude Code](https://claude.ai/code) - Anthropic 的 AI IDE

---

## ❓ 常见问题

遇到问题？请查看 [FAQ.md](docs/FAQ.md) 获取帮助：
- 安装问题排查
- 配置问题解答
- 运行问题处理
- 故障排查指南

或者通过以下方式获取帮助：
- **GitHub Issues**: https://github.com/agenttrace/agent-trace/issues
- **GitHub Discussions**: https://github.com/agenttrace/agent-trace/discussions

---

*最后更新: 2026-03-18*
*当前版本: v0.3.4*
