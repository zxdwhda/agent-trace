# AgentTrace

🚀 **AI IDE 会话监控与 Trace 上报工具**

将 Kimi Code CLI、Claude Code 等 AI IDE 的会话数据自动上报到 Coze 罗盘进行观测和分析。

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

---

## 📋 功能特性

### ✅ 当前版本 v0.3.3

| 特性 | 状态 | 说明 |
|-----|------|------|
| Kimi Code CLI 监控 | ✅ | 完整的 Wire 协议支持 |
| 事件去重 | ✅ | 三层去重机制（内存+SQLite） |
| Offset 持久化 | ✅ | 进程重启不丢数据 |
| 文件指纹检测 | ✅ | 防止 inode 复用问题 |
| 开机自启动 | ✅ | macOS/Linux/Windows 全支持 |
| Trace 层级结构 | ✅ | agent → model → tool 正确嵌套 |
| Claude Code 监控 | 🚧 | v0.4.0 开发中 |

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
./scripts/start.sh

# 查看日志
./scripts/logs.sh

# 停止监控
./scripts/stop.sh
```

---

## 📊 Trace 数据结构

### Span 层级关系

```
agent_turn (root_span)
├── tags:
│   ├── session_id: "xxx"
│   ├── agent_type: "kimi_cli"
│   └── turn_index: "0"
├── step_1 (model_span)
│   ├── set_input(): 用户输入
│   ├── set_output(): 模型输出
│   ├── set_model_name(): "kimi-k2"
│   ├── set_input_tokens(): 1000
│   ├── set_output_tokens(): 500
│   └── tool:Glob (tool_span)
│       ├── set_input(): {"tool_name": "Glob", "arguments": {...}}
│       └── set_output(): {"result": "..."}
├── step_2 (model_span)
│   └── ...
└── output: {"total_tokens": 1500, "context_usage": "80%"}
```

---

## 🔧 技术细节

> 💡 **深入了解更多技术细节**：
> - [架构设计文档](docs/ARCHITECTURE.md) - 系统架构、技术选型、数据流
> - [设计实现文档](docs/DESIGN.md) - 去重算法、持久化机制、文件指纹

### 事件去重机制

采用三层去重策略（参考了 LangSmith 和 OpenTelemetry 的设计）：

```
L0: Session Memory Cache (Set)
    └── 当前会话内已处理的 Span ID
    
L1: Global Memory Cache (LRU, 10,000 items)
    └── 最近处理的事件 ID
    
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

### v0.3.3 (当前版本)
- ✅ 修复事件 ID 生成问题
- ✅ 修复 TurnBegin 多轮对话处理
- ✅ 添加命令行安全警告
- ✅ 添加日志轮转（RotatingFileHandler）
- ✅ 完善测试文档

### v0.3.2
- ✅ Kimi Code CLI 完整支持
- ✅ 事件去重机制
- ✅ Offset 持久化
- ✅ 开机自启动

### v0.4.0 (开发中) - Claude Code 支持
- 🚧 Claude Code stream-json 解析器
- 🚧 Claude 事件处理器
- 🚧 双模式监控（同时支持 Kimi + Claude）

### v0.5.0 (规划中)
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
*当前版本: v0.3.3*
