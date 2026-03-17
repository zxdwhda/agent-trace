# AgentTrace 架构设计文档

## 目录

- [概述](#概述)
- [系统架构图](#系统架构图)
- [核心组件](#核心组件)
- [数据流说明](#数据流说明)
- [技术选型](#技术选型)
- [扩展性设计](#扩展性设计)

---

## 概述

AgentTrace 是一个将 Kimi Code CLI 的会话数据自动上报到 Coze 罗盘进行观测和分析的监控服务。它通过监听 Kimi CLI 生成的 Wire 协议事件，构建完整的 Trace 层级结构，并使用 CozeLoop SDK 上报到 Coze 罗盘平台。

### 设计目标

| 目标 | 说明 |
|------|------|
| **实时性** | 近实时捕获和处理 Kimi CLI 事件 |
| **可靠性** | 进程重启不丢数据，支持事件去重 |
| **可观测性** | 完整的日志和统计信息 |
| **跨平台** | 支持 macOS、Linux、Windows |
| **低侵入** | 后台运行，不干扰正常使用 |

---

## 系统架构图

### 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AgentTrace 监控服务                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌──────────────────────────────────────────────────┐   │
│  │  File       │───▶│  KimiSessionMonitor                              │   │
│  │  Watcher    │    │  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │   │
│  │             │    │  │ SessionState│  │ EventDedupli│  │ Persistent│ │   │
│  │ 监视        │    │  │    Manager  │  │   cator     │  │ OffsetStore│ │   │
│  │ ~/.kimi/    │    │  │             │  │             │  │            │ │   │
│  │ sessions/   │    │  │ - Turn管理   │  │ - L1:内存缓存 │  │ - Offset存储│ │   │
│  │ 变化        │    │  │ - Step跟踪   │  │ - L2:SQLite │  │ - 文件指纹  │ │   │
│  │             │    │  │ - Span层级   │  │ - TTL清理   │  │ - 截断检测  │ │   │
│  └─────────────┘    │  └─────────────┘  └─────────────┘  └──────────┘ │   │
│                     └──────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │                        Event Handler Chain                          │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐│   │
│  │  │TurnBegin │─▶│StepBegin │─▶│ToolCall  │─▶│ToolResult│─▶│TurnEnd ││   │
│  │  │ Handler  │  │ Handler  │  │ Handler  │  │ Handler  │  │Handler ││   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └────────┘│   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │                      CozeLoop Python SDK                            │   │
│  │                     (trace/span 上报)                               │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
└────────────────────────────────────┼────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Coze 罗盘平台                                   │
│                    (https://loop.coze.cn/console)                           │
│                                                                             │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐    │
│   │  Trace 列表  │   │  Span 详情   │   │  性能分析   │   │  调用链路    │    │
│   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 去重与持久化架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    EventDeduplicator (分层去重)                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  L0: Session Memory Cache (Set)                                │
│      └── 当前会话已处理的 Span ID                               │
│      └── 最快，内存级检查                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  L1: Global Memory Cache (LRU, 10000 items)                   │
│      └── 最近处理的事件 ID，快速去重                            │
│      └── 避免频繁查询数据库                                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  L2: SQLite Persistent Store (WAL mode)                        │
│      └── 长期存储，进程重启后恢复                               │
│      └── dedup.db: 已处理事件表                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              PersistentOffsetStore (Offset 持久化)               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  offsets.db                                              │   │
│  │  ┌─────────────────────────────────────────────────┐    │   │
│  │  │  file_offsets 表                                 │    │   │
│  │  │  - filepath    : 文件路径                        │    │   │
│  │  │  - offset      : 读取位置                        │    │   │
│  │  │  - inode       : 文件 inode                      │    │   │
│  │  │  - fingerprint : 文件指纹（MD5）                  │    │   │
│  │  │  - file_size   : 文件大小                        │    │   │
│  │  │  - last_read_at: 最后读取时间                    │    │   │
│  │  └─────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  功能：                                                         │
│  1. 文件截断检测（size 变小）                                    │
│  2. inode 复用检测（相同 inode，不同内容）                       │
│  3. 进程重启后恢复读取位置                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心组件

### 1. KimiSessionMonitor

监控服务主类，负责协调所有组件。

**职责：**
- 扫描和监控 Session 文件
- 管理文件读取器生命周期
- 协调事件处理器
- 定期清理过期数据

**关键配置：**
```python
monitor = KimiSessionMonitor(
    sessions_dir="~/.kimi/sessions/",    # 会话目录
    poll_interval=2.0,                    # 轮询间隔（秒）
    active_timeout_minutes=30,            # 活跃会话超时
    enable_deduplication=True,            # 启用去重
    enable_persistent_offset=True         # 启用 Offset 持久化
)
```

### 2. EventDeduplicator

事件去重管理器，采用三层去重策略。

**分层设计：**

| 层级 | 存储 | 容量 | 用途 |
|------|------|------|------|
| L0 | Session Set | 无限制 | 当前会话已处理事件 |
| L1 | LRU Cache | 10,000 | 全局快速去重 |
| L2 | SQLite | 无限制 | 持久化存储 |

**确定性事件 ID 生成：**
```python
event_id = hashlib.sha256(
    f"{session_id}:turn:{turn_index}:step:{step_n}:type:{event_type}".encode()
).hexdigest()[:32]
```

### 3. PersistentOffsetStore

Offset 持久化管理器，确保进程重启后不重复读取。

**文件指纹检测：**
```python
# 计算文件指纹（头部 1KB 的 MD5）
def compute_fingerprint(filepath):
    with open(filepath, 'rb') as f:
        head = f.read(1024)
        return hashlib.md5(head).hexdigest()
```

**变化检测场景：**

| 场景 | 检测方法 | 处理策略 |
|------|----------|----------|
| 文件截断 | `current_size < stored_size` | 从头开始读取 |
| inode 复用 | `inode 相同 && fingerprint 不同` | 视为新文件 |
| 正常追加 | `current_size > stored_offset` | 从 offset 继续 |

### 4. SessionState

会话状态管理器，维护 Trace 的层级结构。

**Trace 层级：**
```
agent_turn (root_span, span_type="agent")
├── step_1 (model_span, span_type="model")
│   ├── tool:Glob (tool_span, span_type="tool")
│   └── tool:ReadFile (tool_span, span_type="tool")
├── step_2 (model_span, span_type="model")
│   └── tool:Shell (tool_span, span_type="tool")
└── step_3 (model_span, span_type="model")
```

### 5. 事件处理器链

| 处理器 | 事件类型 | 功能 |
|--------|----------|------|
| TurnBeginHandler | TurnBegin | 创建 Root Span |
| StepBeginHandler | StepBegin | 创建 Model Span |
| ToolCallHandler | ToolCall | 创建 Tool Span |
| ToolResultHandler | ToolResult | 结束 Tool Span |
| ContentPartHandler | ContentPart | 累积输出内容 |
| StatusUpdateHandler | StatusUpdate | 更新 Token 使用 |
| TurnEndHandler | TurnEnd | 结束所有 Span |

### 6. IncrementalJSONLReader

增量 JSONL 文件读取器。

**特性：**
- 支持从指定 offset 开始读取
- 自动保存和恢复 offset
- 支持跳过历史数据
- 文件变化检测

---

## 数据流说明

### 完整数据流

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Kimi CLI   │────▶│ wire.jsonl  │────▶│   Monitor   │────▶│   CozeLoop  │
│   运行      │     │  事件文件    │     │   服务      │     │    SDK      │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
     │                    │                   │                   │
     │                    │                   │                   │
     ▼                    ▼                   ▼                   ▼
 用户输入              JSON 事件          Span 构建            Trace 上报
 "分析代码"           {"type":"TurnBegin"}  create_span()       loop.coze.cn
                                          set_attributes()    
                                          add_event()         
```

### 事件处理流程

```
1. 文件变化检测
   ↓
2. 读取新记录 (IncrementalJSONLReader)
   ↓
3. 解析 Wire 事件 (WireParser)
   ↓
4. 事件去重检查 (EventDeduplicator)
   ├─ 重复事件 → 丢弃
   └─ 新事件 → 继续处理
   ↓
5. 路由到对应 Handler
   ↓
6. 更新 SessionState
   ├─ 创建/结束 Span
   ├─ 更新层级关系
   └─ 累积属性
   ↓
7. 标记事件已处理
   ↓
8. 保存 Offset
```

### Wire 事件映射

| Wire 事件 | Span 操作 | 说明 |
|-----------|-----------|------|
| `TurnBegin` | `start_turn()` | 创建 Root Span (agent) |
| `StepBegin` | `start_step()` | 创建 Model Span，parent=root |
| `ToolCall` | `start_tool_call()` | 创建 Tool Span，parent=step |
| `ToolResult` | `end_tool_call()` | 结束 Tool Span |
| `ContentPart` | `add_content()` | 累积到 Span 属性 |
| `StatusUpdate` | `update_token_usage()` | 更新 Span 属性 |
| `TurnEnd` | `end_turn()` | 结束所有 Span，flush |

---

## 技术选型

### 核心技术栈

| 技术 | 用途 | 选型理由 |
|------|------|----------|
| **Python 3.8+** | 开发语言 | 生态丰富，异步支持好 |
| **CozeLoop SDK** | 上报客户端 | 官方 SDK，稳定可靠 |
| **SQLite** | 本地存储 | 零配置，WAL 模式性能好 |
| **watchdog** | 文件监控 | 跨平台，事件驱动 |

### 设计模式借鉴

| 来源项目 | 借鉴点 | 应用场景 |
|----------|--------|----------|
| **OTel FileLog Receiver** | Fingerprint + Offset 机制 | 文件读取位置持久化 |
| **Fluent Bit** | SQLite WAL 模式 | 提高并发写入性能 |
| **Vector** | checksum fingerprint | 检测 inode 复用 |
| **LangSmith** | run_id 幂等性 | 事件去重策略 |

### 存储设计

#### dedup.db 结构

```sql
CREATE TABLE processed_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_index INTEGER,
    step_n INTEGER,
    event_type TEXT,
    span_id TEXT,
    processed_at REAL NOT NULL
);

CREATE INDEX idx_session ON processed_events(session_id);
CREATE INDEX idx_processed_at ON processed_events(processed_at);
```

#### offsets.db 结构

```sql
CREATE TABLE file_offsets (
    filepath TEXT PRIMARY KEY,
    offset INTEGER NOT NULL DEFAULT 0,
    inode INTEGER,
    fingerprint TEXT,
    file_size INTEGER NOT NULL DEFAULT 0,
    last_read_at REAL NOT NULL,
    read_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_last_read ON file_offsets(last_read_at);
```

---

## 扩展性设计

### 插件化事件处理器

```python
# 自定义处理器
class CustomHandler(EventHandler):
    def handle(self, state: SessionState, event: WireEvent) -> bool:
        # 自定义处理逻辑
        return True

# 注册处理器
monitor.handlers[WireEventType.CUSTOM] = CustomHandler()
```

### 多 Sink 支持（未来）

```
┌─────────────┐     ┌─────────────┐
│   Events    │────▶│  CozeLoop   │
│             │     │    Sink     │
│             │     └─────────────┘
│             │     ┌─────────────┐
│             │────▶│   OTLP      │
│             │     │    Sink     │
│             │     └─────────────┘
│             │     ┌─────────────┐
│             │────▶│  Console    │
│             │     │    Sink     │
└─────────────┘     └─────────────┘
```

### 配置热加载（未来）

```python
# 监听配置文件变化
config_watcher.watch("~/.kimi/monitor/config.yaml")

# 动态更新
monitor.update_config(new_config)
```

---

## 部署架构

### 单机部署

```
┌─────────────────────────────────────┐
│            用户机器                  │
│  ┌─────────────────────────────┐   │
│  │   AgentTrace 服务            │   │
│  │   ┌─────────────────────┐   │   │
│  │   │  kimimonitor.service│   │   │
│  │   │  (systemd/launchd)  │   │   │
│  │   └─────────────────────┘   │   │
│  └─────────────────────────────┘   │
│              │                      │
│              ▼                      │
│  ┌─────────────────────────────┐   │
│  │   ~/.kimi/sessions/         │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
              │
              ▼ Internet
    ┌─────────────────────┐
    │   Coze 罗盘平台      │
    │  loop.coze.cn       │
    └─────────────────────┘
```

### 开机自启动支持

| 平台 | 服务类型 | 配置位置 |
|------|----------|----------|
| macOS | launchd | `~/Library/LaunchAgents/com.kimicode.monitor.plist` |
| Linux | systemd | `~/.config/systemd/user/kimi-monitor.service` |
| Windows | Windows Service | 系统服务注册表 |

---

*文档版本: v0.3.2*  
*最后更新: 2026-03-18*
