# AgentTrace 详细设计文档

## 目录

- [概述](#概述)
- [事件去重机制](#事件去重机制)
- [Offset 持久化机制](#offset-持久化机制)
- [文件指纹检测](#文件指纹检测)
- [分层去重策略](#分层去重策略)
- [故障恢复](#故障恢复)

---

## 概述

本文档详细描述 AgentTrace v0.3.2 的核心设计机制，包括事件去重、Offset 持久化、文件指纹检测等关键技术点。这些设计借鉴了多个开源项目的最佳实践，确保系统在各种边界情况下都能可靠运行。

### 问题背景

在 v0.2.3 及之前的版本中，存在以下问题：

1. **重启后重复读取**：进程重启后会重新读取已处理的数据
2. **同一事件多次处理**：在快速轮询时可能重复处理同一事件
3. **没有持久化状态**：所有状态保存在内存中，重启后丢失

### 解决方案概览

通过对 6 个开源项目的调研，我们设计并实现了完整的事件去重和增量读取方案。

| 项目 | 核心发现 | 借鉴点 |
|------|----------|--------|
| Langfuse | 无内置去重，应用层处理 | trace_id 可自定义 |
| OpenTelemetry | BatchSpanProcessor 不去重 | trace_id + span_id 全局唯一 |
| OTel FileLog Receiver | Fingerprint + Offset 机制 | 文件指纹检测、offset 持久化 |
| Fluent Bit | SQLite 存储 offset | WAL 模式、截断检测 |
| Vector | checksum fingerprint | 避免 inode 复用问题 |
| LangSmith | run_id 幂等性 | UUID v7、ContextVar 单例 |

---

## 事件去重机制

### 核心思想

使用确定性事件 ID 确保同一事件只被处理一次，通过三层缓存/存储实现高效去重。

### 事件 ID 生成

```python
def generate_event_id(session_id: str, turn_index: int, step_n: int, event_type: str) -> str:
    """
    生成确定性事件 ID
    
    使用 SHA256 哈希确保：
    1. 同一事件总是生成相同的 ID
    2. 不同事件生成不同的 ID
    3. ID 长度固定，便于存储和索引
    """
    return hashlib.sha256(
        f"{session_id}:turn:{turn_index}:step:{step_n}:type:{event_type}".encode()
    ).hexdigest()[:32]
```

**设计要点：**
- 使用 `session_id` 作为命名空间，避免不同会话冲突
- 包含 `turn_index` 和 `step_n` 确保同一 Turn 内的不同 Step 有唯一 ID
- 包含 `event_type` 区分同一 Step 内的不同类型事件
- 截取前 32 字符，平衡唯一性和存储空间

### 去重流程

```
收到事件
    │
    ▼
生成 event_id
    │
    ▼
┌─────────────────┐
│ L0: Session Cache│ ──Yes──▶ 丢弃事件
│ (内存 Set)      │
│ O(1) 查询       │
└────────┬────────┘
         │ No
         ▼
┌─────────────────┐
│ L1: Global Cache │ ──Yes──▶ 丢弃事件
│ (LRU, 10000)    │
│ O(1) 查询       │
└────────┬────────┘
         │ No
         ▼
┌─────────────────┐
│ L2: SQLite DB   │ ──Yes──▶ 加入 L1 Cache, 丢弃事件
│ (持久化)        │
│ 索引查询        │
└────────┬────────┘
         │ No
         ▼
    处理事件
         │
         ▼
    标记已处理
    ├─ 加入 L0 Cache
    ├─ 加入 L1 Cache
    └─ 写入 SQLite
```

### 代码实现

```python
class EventDeduplicator:
    def __init__(self, memory_cache_size: int = 10000, ttl_hours: int = 24):
        # L1: 内存缓存
        self._memory_cache: Set[str] = set()
        self._memory_cache_order: list = []  # LRU 淘汰队列
        self.memory_cache_size = memory_cache_size
        
        # L2: SQLite 持久化
        self.db_path = db_path
        self._init_db()
    
    def is_duplicate(self, event_id: str) -> bool:
        # L1 检查
        if event_id in self._memory_cache:
            return True
        
        # L2 检查
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_events WHERE event_id = ?",
                (event_id,)
            )
            if cursor.fetchone():
                # 加入内存缓存加速后续查询
                self._add_to_memory_cache(event_id)
                return True
        
        return False
    
    def mark_processed(self, event_id: str, ...):
        # 加入内存缓存
        self._add_to_memory_cache(event_id)
        
        # 持久化到 SQLite
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_events 
                (event_id, session_id, turn_index, step_n, event_type, span_id, processed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, session_id, turn_index, step_n, event_type, span_id, time.time())
            )
```

### LRU 缓存实现

```python
def _add_to_memory_cache(self, event_id: str):
    """添加事件 ID 到内存缓存（LRU 淘汰）"""
    if event_id in self._memory_cache:
        return
    
    # 淘汰旧条目
    while len(self._memory_cache) >= self.memory_cache_size:
        if self._memory_cache_order:
            oldest = self._memory_cache_order.pop(0)
            self._memory_cache.discard(oldest)
    
    self._memory_cache.add(event_id)
    self._memory_cache_order.append(event_id)
```

---

## Offset 持久化机制

### 核心思想

将每个文件的读取位置（offset）持久化到 SQLite，进程重启后从上次位置继续读取，避免重复处理。

### 数据模型

```python
@dataclass
class FileOffset:
    filepath: str        # 文件路径
    offset: int          # 读取位置（字节）
    inode: Optional[int] # 文件 inode
    fingerprint: Optional[str]  # 文件指纹
    file_size: int       # 文件大小
    last_read_at: float  # 最后读取时间
    read_count: int      # 读取次数
```

### 持久化流程

```
读取新记录
    │
    ▼
处理记录
    │
    ▼
更新内存 offset
    │
    ▼
定时/定量保存到 SQLite
    │
    ▼
写入 file_offsets 表
```

### 代码实现

```python
class PersistentOffsetStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or "~/.kimi/monitor/offsets.db"
        self._init_db()
    
    def _init_db(self):
        """初始化数据库，启用 WAL 模式"""
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            # WAL 模式提高并发性能
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_offsets (
                    filepath TEXT PRIMARY KEY,
                    offset INTEGER NOT NULL DEFAULT 0,
                    inode INTEGER,
                    fingerprint TEXT,
                    file_size INTEGER NOT NULL DEFAULT 0,
                    last_read_at REAL NOT NULL,
                    read_count INTEGER NOT NULL DEFAULT 0
                )
            """)
    
    def save_offset(self, filepath: str, offset: int, file_size: int, 
                    inode: Optional[int] = None, fingerprint: Optional[str] = None):
        """保存 offset"""
        with sqlite3.connect(self.db_path, timeout=10.0) as conn:
            conn.execute(
                """
                INSERT INTO file_offsets 
                (filepath, offset, inode, fingerprint, file_size, last_read_at, read_count)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(filepath) DO UPDATE SET
                offset = excluded.offset,
                inode = excluded.inode,
                fingerprint = excluded.fingerprint,
                file_size = excluded.file_size,
                last_read_at = excluded.last_read_at,
                read_count = file_offsets.read_count + 1
                """,
                (filepath, offset, inode, fingerprint, file_size, time.time())
            )
    
    def get_offset(self, filepath: str) -> FileOffset:
        """获取 offset"""
        with sqlite3.connect(self.db_path, timeout=10.0) as conn:
            cursor = conn.execute(
                "SELECT offset, inode, fingerprint, file_size, last_read_at, read_count "
                "FROM file_offsets WHERE filepath = ?",
                (filepath,)
            )
            row = cursor.fetchone()
            if row:
                return FileOffset(filepath, *row)
        
        # 默认返回初始状态
        return FileOffset(filepath, 0, None, None, 0, 0, 0)
```

### 读取策略

```python
class IncrementalJSONLReader:
    def __init__(self, filepath: str, offset_store: PersistentOffsetStore):
        self.filepath = filepath
        self.offset_store = offset_store
        self.current_offset = 0
        
        # 恢复 offset
        self._restore_offset()
    
    def _restore_offset(self):
        """从持久化存储恢复 offset"""
        offset_info = self.offset_store.get_offset(self.filepath)
        
        # 检查文件是否被截断
        current_size = os.path.getsize(self.filepath)
        if current_size < offset_info.file_size:
            logger.warning(f"File truncated, starting from beginning")
            self.current_offset = 0
            return
        
        # 检查 inode 复用
        current_inode = os.stat(self.filepath).st_ino
        if offset_info.inode == current_inode:
            if offset_info.fingerprint != current_fingerprint:
                logger.warning(f"Inode reuse detected, starting from beginning")
                self.current_offset = 0
                return
        
        self.current_offset = offset_info.offset
    
    def read_new_records(self) -> Iterator[JSONLRecord]:
        """读取新记录"""
        with open(self.filepath, 'r') as f:
            f.seek(self.current_offset)
            
            for line in f:
                record = parse_json(line)
                self.current_offset = f.tell()
                yield record
                
                # 保存 offset
                self.offset_store.save_offset(
                    self.filepath, 
                    self.current_offset,
                    os.path.getsize(self.filepath),
                    os.stat(self.filepath).st_ino,
                    compute_fingerprint(self.filepath)
                )
```

---

## 文件指纹检测

### 核心思想

使用文件指纹检测文件变化，避免因 inode 复用导致的错误读取。

### inode 复用问题

```
场景：
1. 文件 A (inode=12345) 被监控，offset=1000
2. 文件 A 被删除
3. 新文件 B 被创建，恰好复用 inode=12345
4. 如果不检测，会从 offset=1000 开始读取文件 B，导致数据丢失！
```

### 指纹计算

```python
class FileFingerprint:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._inode: Optional[int] = None
        self._size: int = 0
        self._mtime: float = 0
        self._head_hash: Optional[str] = None
    
    def compute(self) -> Dict[str, Any]:
        """计算文件指纹"""
        stat = os.stat(self.filepath)
        
        self._inode = stat.st_ino
        self._size = stat.st_size
        self._mtime = stat.st_mtime
        
        # 读取文件头部 1KB 计算 hash
        with open(self.filepath, 'rb') as f:
            head = f.read(1024)
            self._head_hash = hashlib.md5(head).hexdigest()
        
        # 综合指纹
        fingerprint = hashlib.sha256(
            f"{self._inode}:{self._size}:{self._mtime}:{self._head_hash}".encode()
        ).hexdigest()[:16]
        
        return {
            "inode": self._inode,
            "size": self._size,
            "mtime": self._mtime,
            "head_hash": self._head_hash,
            "fingerprint": fingerprint
        }
```

### 变化检测逻辑

```python
def has_changed(self, other_fingerprint: Dict[str, Any]) -> bool:
    """检查文件是否发生变化"""
    current = self.compute()
    return current["fingerprint"] != other_fingerprint.get("fingerprint")

def check_inode_reuse(self, filepath: str, current_inode: int, current_fingerprint: str) -> bool:
    """检查是否发生 inode 复用"""
    stored = self.get_offset(filepath)
    
    # inode 相同但指纹不同，说明文件被替换了
    if stored.inode is not None and stored.inode == current_inode:
        if stored.fingerprint and stored.fingerprint != current_fingerprint:
            logger.warning(
                f"Inode reuse detected: {filepath} "
                f"(inode={current_inode}, fingerprint changed)"
            )
            return True
    
    return False
```

---

## 分层去重策略

### 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│                    EventDeduplicator                        │
├─────────────────────────────────────────────────────────────┤
│  L0: Session Memory Cache (Set)                            │
│      └── 当前会话已处理的 Span ID                           │
│      └── 范围：单个 Session 生命周期                        │
│      └── 容量：无限制（随 Session 结束清理）                │
│      └── 查询：O(1)                                         │
├─────────────────────────────────────────────────────────────┤
│  L1: Global Memory Cache (LRU, 10000 items)                │
│      └── 最近处理的事件 ID，快速去重                        │
│      └── 范围：全局，进程生命周期                           │
│      └── 容量：10,000 条                                    │
│      └── 淘汰：LRU                                          │
│      └── 查询：O(1)                                         │
├─────────────────────────────────────────────────────────────┤
│  L2: SQLite Persistent Store (WAL mode)                    │
│      └── 长期存储，进程重启后恢复                           │
│      └── 范围：永久（TTL 清理）                             │
│      └── 容量：无限制                                       │
│      └── 查询：O(log n)，有索引                             │
└─────────────────────────────────────────────────────────────┘
```

### 各层作用

| 层级 | 作用 | 命中率目标 | 性能 |
|------|------|-----------|------|
| L0 | 防止同一 Session 内重复 | 80% | < 1μs |
| L1 | 防止短时间内重复 | 15% | < 1μs |
| L2 | 持久化，跨进程去重 | 5% | < 10ms |

### 去重统计

```python
def get_stats(self) -> Dict[str, Any]:
    """获取去重统计信息"""
    return {
        "memory_cache_size": len(self._memory_cache),  # L1 缓存大小
        "db_total_events": total,                       # 数据库总事件数
        "db_sessions": sessions,                        # 数据库会话数
        "db_path": self.db_path                         # 数据库路径
    }
```

---

## 故障恢复

### 场景与处理

| 场景 | 检测方法 | 处理策略 | 影响 |
|------|----------|----------|------|
| 进程崩溃 | 重启后读取 offset | 从 SQLite 恢复 | 可能重复最后几条 |
| 文件被截断 | `size < stored_size` | 从头开始读取 | 可能重复部分数据 |
| 文件被替换 | `inode 相同 && fingerprint 不同` | 视为新文件 | 无重复 |
| 数据库损坏 | SQLite 异常 | 自动重建数据库 | offset 重置 |
| 系统重启 | 自启动服务 | 自动恢复运行 | 无影响 |

### 自动恢复代码

```python
def _restore_offset(self):
    """恢复 offset，处理各种边界情况"""
    offset_info = self.offset_store.get_offset(self.filepath)
    
    try:
        current_size = os.path.getsize(self.filepath)
        current_inode = os.stat(self.filepath).st_ino
        current_fingerprint = compute_fingerprint(self.filepath)
    except Exception as e:
        logger.error(f"Cannot stat file: {e}")
        self.current_offset = 0
        return
    
    # 1. 检查文件截断
    if current_size < offset_info.file_size:
        logger.warning(f"File truncated: {filepath}")
        self.current_offset = 0
        return
    
    # 2. 检查 inode 复用
    if (offset_info.inode is not None and 
        offset_info.inode == current_inode and
        offset_info.fingerprint != current_fingerprint):
        logger.warning(f"Inode reuse detected: {filepath}")
        self.current_offset = 0
        return
    
    # 3. 检查 offset 有效性
    if offset_info.offset > current_size:
        logger.warning(f"Invalid offset: {offset_info.offset} > {current_size}")
        self.current_offset = 0
        return
    
    # 4. 恢复 offset
    self.current_offset = offset_info.offset
    logger.info(f"Restored offset: {self.current_offset}")
```

### 数据清理

```python
def cleanup_expired(self) -> int:
    """清理过期记录，防止数据库无限增长"""
    cutoff_time = time.time() - (self.ttl_hours * 3600)
    
    with sqlite3.connect(self.db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM processed_events WHERE processed_at < ?",
            (cutoff_time,)
        )
        return cursor.rowcount

def cleanup_old_records(self, max_age_hours: int = 168) -> int:
    """清理旧的 offset 记录"""
    cutoff_time = time.time() - (max_age_hours * 3600)
    
    with sqlite3.connect(self.db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM file_offsets WHERE last_read_at < ?",
            (cutoff_time,)
        )
        return cursor.rowcount
```

---

## 性能优化

### 内存优化

```python
# 1. LRU 缓存限制
memory_cache_size = 10000  # 最多 10,000 条

# 2. TTL 清理
ttl_hours = 24  # 24 小时后自动清理

# 3. 批量操作
BATCH_SIZE = 100  # 批量保存 offset
```

### 数据库优化

```python
# 1. WAL 模式
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")

# 2. 索引优化
CREATE INDEX idx_session ON processed_events(session_id)
CREATE INDEX idx_processed_at ON processed_events(processed_at)
CREATE INDEX idx_last_read ON file_offsets(last_read_at)

# 3. 超时设置
timeout = 10.0  # 10 秒超时，避免死锁
```

---

*文档版本: v0.3.2*  
*最后更新: 2026-03-18*
