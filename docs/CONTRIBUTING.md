# AgentTrace 贡献指南

感谢您对 AgentTrace 项目的关注！本文档将帮助您快速搭建开发环境并参与贡献。

## 目录

- [开发环境搭建](#开发环境搭建)
- [项目结构](#项目结构)
- [代码规范](#代码规范)
- [提交流程](#提交流程)
- [测试要求](#测试要求)
- [调试技巧](#调试技巧)

---

## 开发环境搭建

### 环境要求

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Python | 3.8+ | 核心运行环境 |
| pip | 最新版 | 包管理 |
| SQLite | 3.24+ | 本地存储 |
| git | 任意 | 版本控制 |

### 1. 克隆仓库

```bash
# 克隆项目
git clone <repository-url>
cd agent-trace

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

### 2. 安装依赖

```bash
# 安装核心依赖
pip install cozeloop

# 安装开发依赖（如果有 requirements-dev.txt）
pip install -r requirements-dev.txt
```

### 3. 配置环境变量

```bash
# 创建 .env 文件 或 直接设置环境变量
export COZELOOP_WORKSPACE_ID="your-workspace-id"
export COZELOOP_API_TOKEN="your-api-token"
export COZELOOP_API_BASE="https://api.coze.cn"

# 可选配置
export KIMI_LOG_LEVEL="DEBUG"
export KIMI_LOG_FILE="/tmp/kimi-cozeloop-dev.log"
```

### 4. 验证安装

```bash
# 运行测试
python -m pytest tests/ -v

# 或直接运行监控服务
python -m kimi_monitor --help
```

---

## 项目结构

```
agent-trace/
├── src/
│   └── kimi_monitor/              # 主代码目录
│       ├── __init__.py            # 版本信息
│       ├── __main__.py            # CLI 入口
│       ├── autostart/             # 开机自启动管理
│       │   ├── __init__.py
│       │   ├── macos/             # macOS launchd
│       │   ├── linux/             # Linux systemd
│       │   └── windows/           # Windows Service
│       ├── core/                  # 核心模块
│       │   ├── __init__.py
│       │   ├── monitor.py         # 监控服务主类
│       │   ├── dedup.py           # 事件去重
│       │   ├── persistent_offset.py  # Offset 持久化
│       │   └── session_state.py   # Session 状态管理
│       ├── handlers/              # 事件处理器
│       │   ├── __init__.py
│       │   └── event_handler.py   # 各类事件处理
│       ├── parsers/               # 解析器
│       │   ├── __init__.py
│       │   ├── jsonl_reader.py    # JSONL 增量读取
│       │   └── wire_parser.py     # Wire 协议解析
│       └── utils/                 # 工具模块
│           ├── __init__.py
│           ├── config.py          # 配置管理
│           ├── logging_config.py  # 日志配置
│           └── retry.py           # 重试机制
├── tests/                         # 测试目录
├── docs/                          # 文档目录
├── scripts/                       # 脚本目录
└── README.md                      # 项目说明
```

### 模块职责

| 模块 | 职责 | 关键文件 |
|------|------|----------|
| `core` | 核心业务逻辑 | `monitor.py`, `dedup.py`, `persistent_offset.py` |
| `handlers` | 事件处理 | `event_handler.py` |
| `parsers` | 数据解析 | `jsonl_reader.py`, `wire_parser.py` |
| `utils` | 通用工具 | `config.py`, `logging_config.py` |
| `autostart` | 自启动管理 | 平台相关实现 |

---

## 代码规范

### Python 代码风格

遵循 PEP 8 规范，使用以下配置：

```python
# 文件头模板
#!/usr/bin/env python3
"""
模块简短描述

详细描述模块的功能、用途和设计思路。
"""

import  # 标准库
import  

from  # 第三方库
import  

from  # 本地模块
import  

# 模块级日志
logger = logging.getLogger("kimi_monitor")
```

### 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 类名 | PascalCase | `EventDeduplicator`, `SessionState` |
| 函数/方法 | snake_case | `is_duplicate()`, `mark_processed()` |
| 变量 | snake_case | `memory_cache`, `file_offset` |
| 常量 | UPPER_SNAKE_CASE | `DEFAULT_CACHE_SIZE`, `TTL_HOURS` |
| 私有成员 | 前缀下划线 | `_init_db()`, `_memory_cache` |
| 模块 | 小写 | `dedup.py`, `config.py` |

### 代码注释

```python
class EventDeduplicator:
    """
    事件去重管理器
    
    采用分层去重策略：
    1. 内存缓存：快速检查最近事件（L1 缓存）
    2. SQLite 持久化：长期存储已处理事件（L2 存储）
    3. TTL 清理：自动清理过期记录
    
    借鉴自：Fluent Bit SQLite offset 存储 + LangSmith run_id 幂等性
    
    Attributes:
        memory_cache_size: 内存缓存最大条目数
        ttl_hours: 记录过期时间（小时）
        db_path: SQLite 数据库路径
    """
    
    def is_duplicate(self, event_id: str) -> bool:
        """
        检查事件是否重复
        
        Args:
            event_id: 事件 ID，由 generate_event_id() 生成
            
        Returns:
            True 表示重复（已处理过），False 表示新事件
            
        Example:
            >>> dedup = EventDeduplicator()
            >>> dedup.is_duplicate("abc123...")
            False
        """
        pass
```

### 类型注解

```python
from typing import Optional, Dict, Any, List, Set

def process_event(
    event_id: str,
    session_id: str,
    turn_index: int,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    处理事件
    
    Args:
        event_id: 事件唯一标识
        session_id: 会话 ID
        turn_index: Turn 索引
        metadata: 可选的元数据
        
    Returns:
        处理是否成功
    """
    pass
```

### 错误处理

```python
# 使用 try-except 捕获具体异常
try:
    with sqlite3.connect(self.db_path, timeout=10.0) as conn:
        cursor = conn.execute("SELECT ...")
        return cursor.fetchone()
except sqlite3.Error as e:
    logger.warning(f"SQLite error: {e}")
    return None
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    raise
```

---

## 提交流程

### 分支管理

```bash
# 1. 从 main 分支创建功能分支
git checkout main
git pull origin main
git checkout -b feature/your-feature-name

# 2. 开发完成后提交
git add .
git commit -m "feat: 添加新功能描述"

# 3. 推送到远程
git push origin feature/your-feature-name

# 4. 创建 Pull Request
```

### 提交信息规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**类型说明：**

| 类型 | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(dedup): 添加内存缓存 TTL 支持` |
| `fix` | Bug 修复 | `fix(offset): 修复文件截断检测` |
| `docs` | 文档更新 | `docs: 更新架构设计文档` |
| `style` | 代码格式 | `style: 格式化 import 语句` |
| `refactor` | 重构 | `refactor(monitor): 重构扫描逻辑` |
| `test` | 测试相关 | `test: 添加去重单元测试` |
| `chore` | 构建/工具 | `chore: 更新依赖版本` |

**示例：**

```bash
# 新功能
git commit -m "feat(dedup): 添加分层去重机制

- L0: Session 内存缓存
- L1: Global LRU 缓存 (10000 items)
- L2: SQLite 持久化存储

Fixes #123"

# Bug 修复
git commit -m "fix(offset): 修复 inode 复用检测

在文件被替换但 inode 不变时，
现在能正确识别并从开始读取。

Closes #456"
```

### Code Review 检查清单

- [ ] 代码符合 PEP 8 规范
- [ ] 新增函数包含文档字符串
- [ ] 类型注解完整
- [ ] 错误处理完善
- [ ] 单元测试通过
- [ ] 无明显的性能问题
- [ ] 文档已更新（如需要）

---

## 测试要求

### 测试框架

```bash
# 安装测试依赖
pip install pytest pytest-cov pytest-asyncio

# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试
python -m pytest tests/test_dedup.py -v

# 生成覆盖率报告
python -m pytest tests/ --cov=kimi_monitor --cov-report=html
```

### 测试目录结构

```
tests/
├── __init__.py
├── conftest.py              # pytest 配置和 fixture
├── test_dedup.py            # 去重模块测试
├── test_offset.py           # Offset 持久化测试
├── test_monitor.py          # 监控服务测试
├── test_handlers.py         # 事件处理器测试
├── test_parsers.py          # 解析器测试
└── test_integration.py      # 集成测试
```

### 测试示例

```python
# tests/test_dedup.py
import pytest
from kimi_monitor.core.dedup import EventDeduplicator

@pytest.fixture
def dedup(tmp_path):
    """创建测试用的去重器"""
    db_path = tmp_path / "test_dedup.db"
    return EventDeduplicator(db_path=str(db_path))

class TestEventDeduplicator:
    def test_is_duplicate_new_event(self, dedup):
        """测试新事件不应被标记为重复"""
        event_id = "test_event_123"
        assert dedup.is_duplicate(event_id) is False
    
    def test_is_duplicate_processed_event(self, dedup):
        """测试已处理事件应被标记为重复"""
        event_id = "test_event_123"
        dedup.mark_processed(event_id, "session_1", 0, 1, "StepBegin")
        assert dedup.is_duplicate(event_id) is True
    
    def test_memory_cache_lru(self, dedup):
        """测试 LRU 缓存淘汰"""
        dedup.memory_cache_size = 3
        
        # 添加 3 个事件
        for i in range(3):
            dedup.mark_processed(f"event_{i}", "session_1", 0, i, "StepBegin")
        
        # 前 3 个都在缓存中
        assert dedup.is_duplicate("event_0") is True
        
        # 添加第 4 个，应该淘汰 event_0
        dedup.mark_processed("event_3", "session_1", 0, 3, "StepBegin")
        
        # event_0 被从内存缓存淘汰，但仍在数据库中
        assert dedup.is_duplicate("event_0") is True
```

### 测试覆盖率要求

| 模块 | 覆盖率要求 |
|------|-----------|
| `core` | >= 80% |
| `handlers` | >= 70% |
| `parsers` | >= 75% |
| `utils` | >= 60% |

---

## 调试技巧

### 日志级别

```bash
# 开发调试（最详细）
export KIMI_LOG_LEVEL="DEBUG"
python -m kimi_monitor

# 正常运行
export KIMI_LOG_LEVEL="INFO"
python -m kimi_monitor

# 生产环境
export KIMI_LOG_LEVEL="WARNING"
python -m kimi_monitor
```

### 常用调试命令

```python
# 查看去重统计
from kimi_monitor.core.dedup import EventDeduplicator
dedup = EventDeduplicator()
print(dedup.get_stats())
# {'memory_cache_size': 100, 'db_total_events': 1000, ...}

# 查看 offset 统计
from kimi_monitor.core.persistent_offset import PersistentOffsetStore
store = PersistentOffsetStore()
print(store.get_stats())
# {'tracked_files': 5, 'total_reads': 1500, ...}

# 查看会话事件
print(dedup.get_session_events("session-id"))
```

### 使用断点调试

```python
# 在代码中插入断点
import pdb; pdb.set_trace()

# 或使用 ipdb（推荐）
import ipdb; ipdb.set_trace()
```

### 调试常见场景

#### 1. 事件重复上报

```bash
# 1. 检查去重统计
./src/start_monitor_v3.sh stats

# 2. 查看详细日志
tail -f /tmp/kimi-cozeloop-v3.log | grep "duplicate"

# 3. 检查数据库
sqlite3 ~/.kimi/monitor/dedup.db "SELECT * FROM processed_events LIMIT 10;"
```

#### 2. Offset 不生效

```bash
# 1. 检查 offset 数据库
sqlite3 ~/.kimi/monitor/offsets.db "SELECT * FROM file_offsets;"

# 2. 检查文件指纹
python -c "
from kimi_monitor.core.dedup import FileFingerprint
fp = FileFingerprint('~/.kimi/sessions/xxx/wire.jsonl')
print(fp.compute())
"
```

#### 3. 文件读取问题

```bash
# 1. 检查文件权限
ls -la ~/.kimi/sessions/

# 2. 检查文件内容
head ~/.kimi/sessions/xxx/wire.jsonl

# 3. 手动测试解析
python -c "
from kimi_monitor.parsers.jsonl_reader import IncrementalJSONLReader
reader = IncrementalJSONLReader('~/.kimi/sessions/xxx/wire.jsonl')
for record in reader.read_new_records():
    print(record)
"
```

---

## 发布流程

### 版本号规则

遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)：

```
主版本号.次版本号.修订号

例如：0.3.0
```

| 版本类型 | 说明 | 示例 |
|----------|------|------|
| 主版本号 | 不兼容的 API 修改 | 1.0.0 |
| 次版本号 | 向下兼容的功能新增 | 0.4.0 |
| 修订号 | 向下兼容的问题修复 | 0.3.1 |

### 发布步骤

1. 更新版本号（`src/kimi_monitor/__init__.py`）
2. 更新 CHANGELOG.md
3. 创建 Release PR
4. 合并后打标签
5. 创建 GitHub Release

---

## 获取帮助

- **Issue**: 在 GitHub 上创建 Issue
- **文档**: 查看 `docs/` 目录
- **调试**: 参考 [DEBUG_GUIDE.md](../DEBUG_GUIDE.md)

---

*文档版本: v0.3.0*  
*最后更新: 2026-03-18*
