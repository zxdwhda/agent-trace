# 测试指南

*文档版本: v0.3.5*  
*最后更新: 2026-03-18*

本文档描述 AgentTrace 的测试方法和流程。

---

## 📋 目录

- [手动测试](#手动测试)
- [单元测试](#单元测试)
- [集成测试](#集成测试)
- [端到端测试](#端到端测试)
- [CI/CD 测试](#cicd-测试)
- [测试最佳实践](#测试最佳实践)

---

## 手动测试

### 环境准备

```bash
# 1. 安装依赖
pip install -e ".[dev]"

# 2. 配置环境变量
export COZELOOP_WORKSPACE_ID="your-workspace-id"
export COZELOOP_API_TOKEN="your-api-token"
export COZELOOP_API_BASE="https://api.coze.cn"

# 3. 确保 Kimi Code CLI 已安装
which kimi
```

### 基础功能测试

#### 测试 1: 服务启动与状态检查

```bash
# 启动服务
agent-trace --log-level DEBUG

# 在另一个终端检查状态
agent-trace --status

# 预期输出:
# ✅ AgentTrace is running (PID: xxxxx)
#    PID file: /tmp/agent_trace.pid
#    Log file: /tmp/agent-trace.log
```

#### 测试 2: 单实例锁测试

```bash
# 终端 1: 启动服务
agent-trace

# 终端 2: 尝试启动第二个实例
agent-trace

# 预期输出:
# ❌ Error: Another instance is already running (PID: xxxxx)
#    Use --force to override, or run 'agent-trace --status' to check status

# 终端 2: 使用 --force 强制启动
agent-trace --force

# 预期: 旧进程被终止，新进程启动
```

#### 测试 3: Trace 上报测试

```bash
# 1. 启动服务（后台运行）
agent-trace --log-level DEBUG &

# 2. 执行 kimi 命令触发会话
kimi --prompt "你好，请简单介绍一下自己" --yolo --print

# 3. 查看日志确认事件被正确处理
tail -f /tmp/agent-trace.log

# 预期日志输出:
# [WIRE] 解析事件: TurnBegin
# [EVENT:xxxx] TurnBegin: 你好，请简单介绍一下自己 (root_span=✓)
# [EVENT:xxxx] StepBegin: step=1 (current_step=✓)
# [EVENT:xxxx] TurnEnd - Trace completed
```

#### 测试 4: 多轮对话测试

```bash
# 在同一个会话中执行多轮对话
kimi --prompt "1+1 等于几" --yolo --print
kimi --prompt "2+2 等于几" --yolo --print

# 检查日志中是否每个 TurnBegin 都创建了 root_span
# 不应出现 "No root span, cannot start step" 警告
```

#### 测试 5: 工具调用测试

```bash
# 触发工具调用
kimi --prompt "帮我查看当前目录的文件列表" --yolo --print

# 检查日志中是否有 ToolCall 和 ToolResult 事件
# 预期:
# [EVENT:xxxx] ToolCall: Shell
# [EVENT:xxxx] ToolResult: Shell
```

### 日志检查清单

执行测试后，检查日志中是否包含以下内容：

```bash
# 检查关键日志
grep -E "(TurnBegin|StepBegin|TurnEnd)" /tmp/agent-trace.log

# 检查错误日志
grep -E "(ERROR|Error|No root span)" /tmp/agent-trace.log
# 预期: 无 "No root span" 错误

# 检查事件解析日志
grep "\[WIRE\]" /tmp/agent-trace.log

# 检查去重统计
grep "\[DEDUP\]" /tmp/agent-trace.log
```

---

## 单元测试

### 运行单元测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_dedup.py -v

# 运行并生成覆盖率报告
pytest tests/ --cov=agent_trace --cov-report=html
```

### 测试文件结构

```
tests/
├── test_dedup.py          # 去重逻辑测试
├── test_session_state.py   # Session 状态测试
├── test_wire_parser.py     # Wire 协议解析测试
├── test_jsonl_reader.py    # JSONL 读取器测试
├── test_offset_store.py    # Offset 存储测试
└── test_singleton.py       # 单实例锁测试
```

### 关键测试用例

#### 事件 ID 生成测试

```python
def test_event_id_uniqueness():
    """测试事件 ID 唯一性"""
    from agent_trace.core.session_state import SessionState
    import time
    
    state = SessionState("test-session")
    
    # 生成两个事件 ID（不同时间戳）
    ts1 = time.time()
    time.sleep(0.1)
    ts2 = time.time()
    
    eid1 = state._generate_event_id("turn_begin", int(ts1), ts1)
    eid2 = state._generate_event_id("turn_begin", int(ts2), ts2)
    
    assert eid1 != eid2, "事件 ID 应该唯一"
```

#### Wire 事件解析测试

```python
def test_wire_event_parsing():
    """测试 Wire 事件解析"""
    from agent_trace.parsers.wire_parser import WireEvent, WireEventType
    
    record = {
        'timestamp': 1234567890.0,
        'message': {
            'type': 'TurnBegin',
            'payload': {'user_input': 'Hello'}
        }
    }
    
    event = WireEvent.from_record(record)
    assert event is not None
    assert event.event_type == WireEventType.TURN_BEGIN
    assert event.payload['user_input'] == 'Hello'
```

---

## 集成测试

### 数据库集成测试

```bash
# 测试 SQLite 数据库操作
python -c "
from agent_trace.core.dedup import EventDeduplicator
from agent_trace.core.persistent_offset import PersistentOffsetStore

# 测试去重数据库
dedup = EventDeduplicator()
event_id = 'test-event-123'
assert not dedup.is_duplicate(event_id)
dedup.mark_processed(event_id, 'test-session', 0, 0, 'test')
assert dedup.is_duplicate(event_id)
print('✅ 去重数据库测试通过')

# 测试 offset 存储
offset_store = PersistentOffsetStore()
offset_store.save_offset('/tmp/test.log', 100, 1000, 12345, 'abc123')
offset = offset_store.get_offset('/tmp/test.log')
assert offset.offset == 100
print('✅ Offset 存储测试通过')
"
```

### CozeLoop SDK 集成测试

```python
# tests/test_cozeloop_integration.py
import os
import pytest
import cozeloop

@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv('COZELOOP_API_TOKEN'),
    reason="需要设置 COZELOOP_API_TOKEN"
)
def test_cozeloop_connection():
    """测试 CozeLoop SDK 连接"""
    client = cozeloop.new_client(
        workspace_id=os.getenv('COZELOOP_WORKSPACE_ID'),
        api_token=os.getenv('COZELOOP_API_TOKEN'),
        api_base_url=os.getenv('COZELOOP_API_BASE', 'https://api.coze.cn')
    )
    
    # 创建测试 span
    span = cozeloop.start_span("test_span", "test")
    span.set_input("test input")
    span.set_output("test output")
    span.end()
    
    # 刷新缓冲区
    cozeloop.flush()
    print("✅ CozeLoop SDK 连接测试通过")
```

---

## 端到端测试

### 完整流程测试脚本

```bash
#!/bin/bash
# scripts/e2e_test.sh

set -e

echo "=== AgentTrace E2E 测试 ==="

# 1. 清理环境
pkill -f "agent_trace" 2>/dev/null || true
rm -f /tmp/agent-trace.log
rm -rf ~/.agenttrace/test_*

# 2. 启动服务
echo "启动服务..."
agent-trace --log-level DEBUG &
PID=$!
sleep 3

# 3. 检查服务状态
if ! ps -p $PID > /dev/null; then
    echo "❌ 服务启动失败"
    exit 1
fi
echo "✅ 服务已启动 (PID: $PID)"

# 4. 执行 kimi 命令
echo "执行 kimi 命令..."
kimi --prompt "E2E测试：你好" --yolo --print

# 5. 等待事件处理
sleep 5

# 6. 验证日志
echo "验证日志..."
if grep -q "TurnBegin" /tmp/agent-trace.log; then
    echo "✅ TurnBegin 事件已处理"
else
    echo "❌ 未找到 TurnBegin 事件"
    kill $PID
    exit 1
fi

if grep -q "No root span" /tmp/agent-trace.log; then
    echo "❌ 发现 root span 错误"
    kill $PID
    exit 1
else
    echo "✅ 无 root span 错误"
fi

# 7. 停止服务
kill $PID
echo "✅ E2E 测试通过"
```

---

## CI/CD 测试

### GitHub Actions 配置

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.9', '3.10', '3.11', '3.12']

    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        pip install -e ".[dev]"
    
    - name: Run linting
      run: |
        ruff check src tests
        black --check src tests
        mypy src
    
    - name: Run unit tests
      run: |
        pytest tests/ -v --cov=agent_trace --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

---

## 测试最佳实践

### 1. 使用 Mock 进行单元测试

避免在单元测试中依赖外部服务：

```python
from unittest.mock import Mock, patch

def test_session_state_without_sdk():
    """不依赖 CozeLoop SDK 测试 SessionState"""
    with patch('agent_trace.core.session_state.cozeloop') as mock_cozeloop:
        mock_span = Mock()
        mock_cozeloop.start_span.return_value = mock_span
        
        state = SessionState("test-session")
        state.start_turn(1234567890, "Hello")
        
        assert state.root_span is not None
        mock_cozeloop.start_span.assert_called_once()
```

### 2. 使用 Fixtures

```python
import pytest

@pytest.fixture
def temp_dedup_db(tmp_path):
    """创建临时去重数据库"""
    from agent_trace.core.dedup import EventDeduplicator
    db_path = tmp_path / "test_dedup.db"
    return EventDeduplicator(db_path=str(db_path))

@pytest.fixture
def mock_session_state():
    """创建 Mock SessionState"""
    from unittest.mock import Mock
    state = Mock()
    state.root_span = None
    state.current_step = None
    return state
```

### 3. 参数化测试

```python
import pytest

@pytest.mark.parametrize("event_type,payload,expected", [
    ("TurnBegin", {"user_input": "Hello"}, True),
    ("StepBegin", {"n": 1}, True),
    ("Unknown", {}, False),
])
def test_wire_event_parsing(event_type, payload, expected):
    """测试不同类型事件的解析"""
    from agent_trace.parsers.wire_parser import WireEvent
    
    record = {
        'timestamp': 1234567890.0,
        'message': {'type': event_type, 'payload': payload}
    }
    
    event = WireEvent.from_record(record)
    assert (event is not None) == expected
```

### 4. 性能测试

```python
import time

def test_event_processing_performance():
    """测试事件处理性能"""
    from agent_trace.core.session_state import SessionState
    
    state = SessionState("perf-test")
    
    start = time.time()
    for i in range(1000):
        state._generate_event_id("test", i, time.time())
    duration = time.time() - start
    
    assert duration < 1.0, f"生成 1000 个事件 ID 耗时 {duration:.2f}s，超过 1s"
```

### 5. 建议的测试工具

| 工具 | 用途 | 安装 |
|------|------|------|
| pytest | 测试框架 | `pip install pytest` |
| pytest-cov | 覆盖率 | `pip install pytest-cov` |
| pytest-asyncio | 异步测试 | `pip install pytest-asyncio` |
| pytest-xdist | 并行测试 | `pip install pytest-xdist` |
| factory-boy | 测试数据 | `pip install factory-boy` |
| freezegun | 时间冻结 | `pip install freezegun` |

### 6. 更好的自动化测试方案

#### 方案 A: 使用 Docker 进行隔离测试

```dockerfile
# Dockerfile.test
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -e ".[dev]"

CMD ["pytest", "tests/", "-v"]
```

```bash
# 运行隔离测试
docker build -f Dockerfile.test -t agenttrace-test .
docker run agenttrace-test
```

#### 方案 B: 使用 VCR.py 录制/回放 HTTP 请求

```python
# 录制 CozeLoop API 调用
import vcr

@vcr.use_cassette('tests/fixtures/cozeloop_api.yaml')
def test_cozeloop_with_recorded_response():
    """使用录制的响应测试"""
    # 测试代码，实际不会调用 API
    pass
```

#### 方案 C: 使用 Playwright 进行 UI 测试（未来 Web UI）

```python
from playwright.sync_api import sync_playwright

def test_web_ui():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("http://localhost:8080")
        # UI 测试代码
        browser.close()
```

---

## 故障排除

### 常见问题

#### 1. 测试时提示 "No module named 'agent_trace'"

```bash
# 解决方案：安装为可编辑模式
pip install -e .
```

#### 2. 测试时数据库锁定

```bash
# 解决方案：清理数据库文件
rm -f ~/.agenttrace/*.db
```

#### 3. 端口被占用

```bash
# 解决方案：查找并终止占用端口的进程
lsof -ti:5494 | xargs kill -9
```

---

*如需更多帮助，请参考 [FAQ.md](FAQ.md) 或提交 Issue。*
