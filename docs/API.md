# AgentTrace API 文档

本文档介绍 AgentTrace 的 Python API 和命令行接口。

## 目录

- [命令行接口 (CLI)](#命令行接口-cli)
- [Python API](#python-api)
- [配置类](#配置类)
- [事件类型](#事件类型)

---

## 命令行接口 (CLI)

### 基本用法

```bash
agent-trace [选项]
```

### 命令行参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--workspace-id` | `-w` | Coze Workspace ID | 从环境变量读取 |
| `--api-token` | `-t` | Coze API Token | 从环境变量读取 |
| `--api-base` | `-b` | API 基础 URL | https://api.coze.cn |
| `--sessions-dir` | `-s` | 会话目录 | ~/.kimi/sessions/ |
| `--poll-interval` | `-p` | 轮询间隔（秒） | 2.0 |
| `--log-level` | `-l` | 日志级别 | INFO |
| `--log-file` | | 日志文件 | /tmp/agent-trace.log |
| `--disable-dedup` | | 禁用去重 | false |
| `--disable-offset` | | 禁用 offset 持久化 | false |
| `--version` | `-v` | 显示版本 | |
| `--help` | `-h` | 显示帮助 | |

### 使用示例

```bash
# 基本启动
agent-trace

# 使用命令行参数配置
agent-trace \
    --workspace-id xxx \
    --api-token yyy \
    --log-level DEBUG

# 禁用去重（调试用）
agent-trace --disable-dedup

# 自定义轮询间隔
agent-trace --poll-interval 5.0
```

### 自启动管理

```bash
# 安装开机自启动
agent-trace autostart install

# 卸载自启动
agent-trace autostart uninstall

# 查看自启动状态
agent-trace autostart status
```

---

## Python API

### AgentTraceMonitor

监控服务主类。

```python
from agent_trace.core.monitor import AgentTraceMonitor

# 创建监控实例
monitor = AgentTraceMonitor(
    sessions_dir="~/.kimi/sessions/",
    poll_interval=2.0,
    active_timeout_minutes=30,
    enable_deduplication=True,
    enable_persistent_offset=True
)

# 启动监控（阻塞）
monitor.start()

# 停止监控
monitor.stop()

# 获取统计信息
stats = monitor.get_stats()
print(stats)
```

**参数说明：**

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `sessions_dir` | str | 会话目录 | ~/.kimi/sessions/ |
| `poll_interval` | float | 轮询间隔（秒） | 2.0 |
| `active_timeout_minutes` | int | 活跃会话超时（分钟） | 30 |
| `enable_deduplication` | bool | 启用事件去重 | True |
| `enable_persistent_offset` | bool | 启用 offset 持久化 | True |

**返回值：**

```python
# get_stats() 返回示例
{
    "active_sessions": 5,
    "monitored_files": 5,
    "deduplication_enabled": True,
    "persistent_offset_enabled": True,
    "deduplicator": {
        "memory_cache_size": 100,
        "db_total_events": 1000,
        "db_sessions": 10,
        "db_path": "/Users/xxx/.kimi/monitor/dedup.db"
    },
    "offset_store": {
        "tracked_files": 5,
        "total_reads": 1500,
        "last_read_at": 1712345678.0,
        "total_size": 1024000,
        "db_path": "/Users/xxx/.kimi/monitor/offsets.db"
    }
}
```

### EventDeduplicator

事件去重管理器。

```python
from agent_trace.core.dedup import EventDeduplicator, EventID

# 创建去重器
dedup = EventDeduplicator(
    db_path="~/.kimi/monitor/dedup.db",
    memory_cache_size=10000,
    ttl_hours=24
)

# 生成事件 ID
event_id = EventID(
    session_id="session-123",
    turn_index=0,
    step_n=1,
    event_type="StepBegin"
).to_string()

# 检查是否重复
if dedup.is_duplicate(event_id):
    print("事件已处理过，跳过")
else:
    # 处理事件...
    
    # 标记为已处理
    dedup.mark_processed(
        event_id=event_id,
        session_id="session-123",
        turn_index=0,
        step_n=1,
        event_type="StepBegin",
        span_id="span-456"
    )

# 清理过期记录
deleted = dedup.cleanup_expired()
print(f"清理了 {deleted} 条过期记录")

# 获取统计
stats = dedup.get_stats()
print(stats)

# 获取会话事件列表
events = dedup.get_session_events("session-123")
```

### PersistentOffsetStore

Offset 持久化管理器。

```python
from agent_trace.core.persistent_offset import PersistentOffsetStore

# 创建存储
store = PersistentOffsetStore(
    db_path="~/.kimi/monitor/offsets.db"
)

# 保存 offset
store.save_offset(
    filepath="/path/to/wire.jsonl",
    offset=1024,
    file_size=2048,
    inode=12345,
    fingerprint="abc123..."
)

# 获取 offset
offset_info = store.get_offset("/path/to/wire.jsonl")
print(f"当前 offset: {offset_info.offset}")
print(f"文件大小: {offset_info.file_size}")
print(f"inode: {offset_info.inode}")

# 检查文件截断
is_truncated = store.check_truncation("/path/to/wire.jsonl", current_size=1000)

# 检查 inode 复用
is_reused = store.check_inode_reuse(
    "/path/to/wire.jsonl",
    current_inode=12345,
    current_fingerprint="xyz789..."
)

# 验证并修正 offset
valid_offset = store.validate_offset("/path/to/wire.jsonl", current_size=2048)

# 删除 offset 记录
store.delete_offset("/path/to/wire.jsonl")

# 清理旧记录
deleted = store.cleanup_old_records(max_age_hours=168)

# 获取统计
stats = store.get_stats()
```

### SessionState

会话状态管理。

```python
from agent_trace.core.session_state import SessionState
from agent_trace.core.dedup import EventDeduplicator

# 创建状态实例（通常在内部使用）
dedup = EventDeduplicator()
state = SessionState(
    session_id="session-123",
    deduplicator=dedup,
    turn_index=0
)

# 开始 Turn
state.start_turn(
    timestamp=time.time(),
    user_input="分析代码"
)

# 开始 Step
state.start_step(
    timestamp=time.time(),
    step_n=1,
    model="kimi-k2"
)

# 开始 Tool 调用
state.start_tool_call(
    timestamp=time.time(),
    tool_call={
        "name": "ReadFile",
        "arguments": {"path": "main.py"}
    }
)

# 结束 Tool 调用
state.end_tool_call(
    timestamp=time.time(),
    tool_result={
        "content": "file content..."
    }
)

# 添加内容
state.add_content(
    timestamp=time.time(),
    content_type="text",
    content="分析结果..."
)

# 更新 Token 使用
state.update_token_usage({
    "input_tokens": 100,
    "output_tokens": 200
})

# 结束 Turn
state.end_turn(timestamp=time.time())
```

### IncrementalJSONLReader

增量 JSONL 文件读取器。

```python
from agent_trace.parsers.jsonl_reader import IncrementalJSONLReader
from agent_trace.core.persistent_offset import PersistentOffsetStore

# 创建 offset 存储
offset_store = PersistentOffsetStore()

# 创建读取器
reader = IncrementalJSONLReader(
    filepath="/path/to/wire.jsonl",
    offset_store=offset_store,
    auto_save_offset=True
)

# 读取新记录
for record in reader.read_new_records():
    print(f"Offset: {record.offset}")
    print(f"Data: {record.record}")

# 跳到文件末尾（不读历史）
reader.skip_to_end()

# 读取最后 N 条
reader.skip_to_last_n_records(n=10)

# 手动保存 offset
reader.save_offset()

# 获取当前 offset
current_offset = reader.get_current_offset()
```

### WireParser

Wire 协议解析器。

```python
from agent_trace.parsers.wire_parser import WireParser, WireEvent, WireEventType

# 解析事件
event = WireEvent.from_record({
    "type": "TurnBegin",
    "timestamp": 1712345678,
    "data": {"user_input": "分析代码"}
})

print(f"类型: {event.event_type}")  # WireEventType.TURN_BEGIN
print(f"时间戳: {event.timestamp}")
print(f"数据: {event.payload}")

# 解析特定字段
user_input = WireParser.parse_user_input(event.payload)
tool_call = WireParser.parse_tool_call(event.payload)
tool_result = WireParser.parse_tool_result(event.payload)
content_info = WireParser.parse_content_part(event.payload)
token_info = WireParser.parse_token_usage(event.payload)
```

### AutoStartManager

开机自启动管理器。

```python
from agent_trace.autostart import AutoStartManager

# 创建管理器
manager = AutoStartManager()

# 安装自启动
manager.install()

# 卸载自启动
manager.uninstall()

# 查看状态
status = manager.status()
print(f"已安装: {status['installed']}")
print(f"运行中: {status['running']}")
```

---

## 配置类

### Config

```python
from agent_trace.utils.config import Config

# 从环境变量加载
config = Config.from_env()

# 使用默认值创建
config = Config.with_defaults(
    workspace_id="your-workspace-id",
    api_token="your-api-token"
)

# 访问配置
print(config.workspace_id)
print(config.api_token)
print(config.api_base)
print(config.sessions_dir)
print(config.poll_interval)

# 设置环境变量
config.setup_env()
```

**配置项：**

| 属性 | 环境变量 | 默认值 |
|------|----------|--------|
| `workspace_id` | `COZELOOP_WORKSPACE_ID` | "" |
| `api_token` | `COZELOOP_API_TOKEN` | "" |
| `api_base` | `COZELOOP_API_BASE` | https://api.coze.cn |
| `sessions_dir` | `KIMI_SESSIONS_DIR` | ~/.kimi/sessions/ |
| `poll_interval` | `KIMI_POLL_INTERVAL` | 2.0 |
| `active_session_timeout_minutes` | `KIMI_ACTIVE_TIMEOUT` | 30 |
| `log_level` | `KIMI_LOG_LEVEL` | INFO |
| `log_file` | `KIMI_LOG_FILE` | /tmp/agent-trace.log |

---

## 事件类型

### WireEventType

```python
from agent_trace.parsers.wire_parser import WireEventType

# 事件类型枚举
WireEventType.TURN_BEGIN        # Turn 开始
WireEventType.TURN_END          # Turn 结束
WireEventType.STEP_BEGIN        # Step 开始
WireEventType.STEP_END          # Step 结束
WireEventType.CONTENT_PART      # 内容片段
WireEventType.TOOL_CALL         # 工具调用
WireEventType.TOOL_RESULT       # 工具结果
WireEventType.STATUS_UPDATE     # 状态更新
WireEventType.APPROVAL_REQUEST  # 批准请求
WireEventType.APPROVAL_RESPONSE # 批准响应
WireEventType.ERROR             # 错误
WireEventType.UNKNOWN           # 未知
```

### 事件结构

```python
from dataclasses import dataclass
from typing import Dict, Any
from enum import Enum

class WireEventType(Enum):
    TURN_BEGIN = "TurnBegin"
    TURN_END = "TurnEnd"
    # ...

@dataclass
class WireEvent:
    event_type: WireEventType
    timestamp: float
    payload: Dict[str, Any]
    raw_data: Dict[str, Any]
    
    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> Optional["WireEvent"]:
        """从原始记录创建事件对象"""
        pass
```

### 事件映射关系

| Wire 事件 | Span 操作 | Span 类型 |
|-----------|-----------|-----------|
| `TurnBegin` | 创建 Root Span | agent |
| `StepBegin` | 创建 Model Span | model |
| `ToolCall` | 创建 Tool Span | tool |
| `ToolResult` | 结束 Tool Span | - |
| `TurnEnd` | 结束所有 Span | - |

---

## 完整示例

### 自定义监控

```python
import time
import logging
from agent_trace.core.monitor import AgentTraceMonitor
from agent_trace.utils.config import Config

# 配置日志
logging.basicConfig(level=logging.INFO)

# 加载配置
config = Config.from_env()
config.setup_env()

# 创建监控器
monitor = AgentTraceMonitor(
    sessions_dir=config.sessions_dir,
    poll_interval=2.0,
    enable_deduplication=True,
    enable_persistent_offset=True
)

try:
    # 启动监控
    print("启动监控...")
    monitor.start()
except KeyboardInterrupt:
    print("\n停止监控...")
    monitor.stop()
    
    # 打印统计
    stats = monitor.get_stats()
    print(f"\n统计信息:")
    print(f"  活跃会话: {stats['active_sessions']}")
    print(f"  监控文件: {stats['monitored_files']}")
```

### 自定义事件处理器

```python
from agent_trace.handlers.event_handler import EventHandler
from agent_trace.core.session_state import SessionState
from agent_trace.parsers.wire_parser import WireEvent

class CustomHandler(EventHandler):
    """自定义事件处理器"""
    
    def handle(self, state: SessionState, event: WireEvent) -> bool:
        print(f"处理事件: {event.event_type}")
        print(f"Session: {state.session_id}")
        print(f"Payload: {event.payload}")
        return True

# 注册处理器
from agent_trace.parsers.wire_parser import WireEventType

monitor.handlers[WireEventType.CUSTOM] = CustomHandler()
```

---

*文档版本: v0.3.3*  
*最后更新: 2026-03-18*
