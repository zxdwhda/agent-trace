#!/usr/bin/env python3
"""
事件去重管理器

基于 SQLite 持久化存储 + 内存缓存，防止 Span 重复上报
借鉴：OTel FileLog Receiver Fingerprint + Offset 机制
"""

import hashlib
import os
import sqlite3
import threading
import time
import logging
from collections import OrderedDict
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger("agent_trace")


@dataclass
class EventID:
    """事件唯一标识"""
    session_id: str
    turn_index: int
    step_n: int
    event_type: str
    timestamp: int = 0  # 添加时间戳字段以确保唯一性
    
    def to_string(self) -> str:
        """生成确定性事件 ID"""
        # 如果有时间戳，使用它来确保唯一性
        unique_key = f"{self.session_id}:turn:{self.turn_index}:step:{self.step_n}:ts:{self.timestamp}:type:{self.event_type}"
        return hashlib.sha256(unique_key.encode()).hexdigest()[:32]


class EventDeduplicator:
    """
    事件去重管理器
    
    采用分层去重策略：
    1. 内存缓存：快速检查最近事件（L1 缓存）
    2. SQLite 持久化：长期存储已处理事件（L2 存储）
    3. TTL 清理：自动清理过期记录
    
    借鉴自：Fluent Bit SQLite offset 存储 + LangSmith run_id 幂等性
    """
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        memory_cache_size: int = 10000,
        ttl_hours: int = 24
    ):
        """
        初始化去重管理器
        
        Args:
            db_path: SQLite 数据库路径，默认 ~/.agenttrace/dedup.db
            memory_cache_size: 内存缓存最大条目数
            ttl_hours: 记录过期时间（小时）
        """
        self.memory_cache_size = memory_cache_size
        self.ttl_hours = ttl_hours
        
        # 内存缓存（L1）：使用 OrderedDict 实现真正的 LRU
        self._memory_cache: OrderedDict[str, None] = OrderedDict()
        
        # 统计信息
        self._stats = {
            "checked": 0,
            "duplicates": 0,
            "new_events": 0,
            "memory_hits": 0,
            "db_hits": 0
        }
        
        # 线程锁
        self._lock = threading.RLock()
        
        # 初始化 SQLite 存储（L2）
        if db_path is None:
            db_dir = Path.home() / ".agenttrace"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "dedup.db")
        
        self.db_path = db_path
        self._init_db()
        
        logger.info(f"[DEDUP] Initialized: db={db_path}, cache_size={memory_cache_size}, ttl={ttl_hours}h")
    
    def _init_db(self):
        """初始化 SQLite 数据库"""
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            # WAL 模式提高并发性能（借鉴 Fluent Bit）
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            
            # 已处理事件表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    turn_index INTEGER,
                    step_n INTEGER,
                    event_type TEXT,
                    span_id TEXT,
                    processed_at REAL NOT NULL
                )
            """)
            
            # 索引优化查询
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session ON processed_events(session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_processed_at ON processed_events(processed_at)
            """)
            
            conn.commit()
    
    def is_duplicate(self, event_id: str) -> bool:
        """
        检查事件是否重复
        
        Args:
            event_id: 事件 ID
            
        Returns:
            True 表示重复（已处理过）
        """
        with self._lock:
            self._stats["checked"] += 1
            
            # L1: 内存缓存快速检查
            if event_id in self._memory_cache:
                # LRU: 移到末尾（最近使用）
                self._memory_cache.move_to_end(event_id)
                self._stats["memory_hits"] += 1
                self._stats["duplicates"] += 1
                logger.debug(f"[DEDUP] Memory cache hit: {event_id[:16]}...")
                return True
            
            # L2: SQLite 持久化检查
            try:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    cursor = conn.execute(
                        "SELECT 1 FROM processed_events WHERE event_id = ?",
                        (event_id,)
                    )
                    if cursor.fetchone():
                        # 加入内存缓存加速后续查询
                        self._add_to_memory_cache(event_id)
                        self._stats["db_hits"] += 1
                        self._stats["duplicates"] += 1
                        logger.debug(f"[DEDUP] DB hit: {event_id[:16]}...")
                        return True
            except sqlite3.Error as e:
                logger.warning(f"[DEDUP] SQLite error checking duplicate: {e}")
            
            self._stats["new_events"] += 1
            return False
    
    def mark_processed(
        self,
        event_id: str,
        session_id: str,
        turn_index: int,
        step_n: int,
        event_type: str,
        span_id: Optional[str] = None
    ):
        """
        标记事件为已处理
        
        Args:
            event_id: 事件 ID
            session_id: 会话 ID
            turn_index: Turn 索引
            step_n: Step 编号
            event_type: 事件类型
            span_id: 对应的 Span ID
        """
        with self._lock:
            # 加入内存缓存
            self._add_to_memory_cache(event_id)
            
            # 持久化到 SQLite
            try:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO processed_events 
                        (event_id, session_id, turn_index, step_n, event_type, span_id, processed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (event_id, session_id, turn_index, step_n, event_type, span_id, time.time())
                    )
                    conn.commit()
                    logger.debug(f"[DEDUP] Marked processed: {event_id[:16]}... ({event_type})")
            except sqlite3.Error as e:
                logger.warning(f"[DEDUP] SQLite error marking processed: {e}")
    
    def _add_to_memory_cache(self, event_id: str):
        """添加事件 ID 到内存缓存（LRU 淘汰）"""
        if event_id in self._memory_cache:
            # 已存在，更新为最近使用
            self._memory_cache.move_to_end(event_id)
            return
        
        # 淘汰最旧的条目
        while len(self._memory_cache) >= self.memory_cache_size:
            self._memory_cache.popitem(last=False)
        
        self._memory_cache[event_id] = None
    
    def cleanup_expired(self) -> int:
        """
        清理过期记录
        
        Returns:
            清理的记录数
        """
        cutoff_time = time.time() - (self.ttl_hours * 3600)
        
        with self._lock:
            try:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    cursor = conn.execute(
                        "DELETE FROM processed_events WHERE processed_at < ?",
                        (cutoff_time,)
                    )
                    conn.commit()
                    deleted = cursor.rowcount
                    if deleted > 0:
                        logger.info(f"[DEDUP] Cleaned up {deleted} expired records")
                    return deleted
            except sqlite3.Error as e:
                logger.warning(f"[DEDUP] SQLite error during cleanup: {e}")
                return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """获取去重统计信息"""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    cursor = conn.execute(
                        "SELECT COUNT(*), COUNT(DISTINCT session_id) FROM processed_events"
                    )
                    total, sessions = cursor.fetchone()
                    
                    return {
                        "checked": self._stats["checked"],
                        "duplicates": self._stats["duplicates"],
                        "new_events": self._stats["new_events"],
                        "memory_hits": self._stats["memory_hits"],
                        "db_hits": self._stats["db_hits"],
                        "duplicate_rate": f"{(self._stats['duplicates'] / max(self._stats['checked'], 1) * 100):.2f}%",
                        "memory_cache_size": len(self._memory_cache),
                        "db_total_events": total or 0,
                        "db_sessions": sessions or 0,
                        "db_path": self.db_path
                    }
            except sqlite3.Error as e:
                logger.warning(f"[DEDUP] SQLite error getting stats: {e}")
                return {
                    **self._stats,
                    "memory_cache_size": len(self._memory_cache),
                    "db_total_events": -1,
                    "db_sessions": -1,
                    "db_path": self.db_path,
                    "error": str(e)
                }
    
    def get_session_events(self, session_id: str) -> list:
        """获取会话的所有已处理事件（用于调试）"""
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                cursor = conn.execute(
                    """
                    SELECT event_id, turn_index, step_n, event_type, span_id, processed_at
                    FROM processed_events
                    WHERE session_id = ?
                    ORDER BY processed_at DESC
                    LIMIT 100
                    """,
                    (session_id,)
                )
                return [
                    {
                        "event_id": row[0],
                        "turn_index": row[1],
                        "step_n": row[2],
                        "event_type": row[3],
                        "span_id": row[4],
                        "processed_at": row[5]
                    }
                    for row in cursor.fetchall()
                ]
        except sqlite3.Error as e:
            logger.warning(f"[DEDUP] SQLite error getting session events: {e}")
            return []


class FileFingerprint:
    """
    文件指纹管理
    
    用于检测文件变化（避免 inode 复用问题）
    借鉴：Vector checksum fingerprint
    """
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._inode: Optional[int] = None
        self._size: int = 0
        self._mtime: float = 0
        self._head_hash: Optional[str] = None
    
    def compute(self) -> Dict[str, Any]:
        """计算文件指纹"""
        try:
            stat = os.stat(self.filepath)
            
            self._inode = stat.st_ino
            self._size = stat.st_size
            self._mtime = stat.st_mtime
            
            # 读取文件头部 1KB 计算 hash（用于检测内容变化）
            try:
                with open(self.filepath, 'rb') as f:
                    head = f.read(1024)
                    self._head_hash = hashlib.md5(head).hexdigest()
            except Exception:
                self._head_hash = None
            
            return {
                "inode": self._inode,
                "size": self._size,
                "mtime": self._mtime,
                "head_hash": self._head_hash,
                "fingerprint": hashlib.sha256(
                    f"{self._inode}:{self._size}:{self._mtime}:{self._head_hash}".encode()
                ).hexdigest()[:16]
            }
        except Exception as e:
            logger.debug(f"[FINGERPRINT] Error computing fingerprint for {self.filepath}: {e}")
            return {
                "inode": None,
                "size": 0,
                "mtime": 0,
                "head_hash": None,
                "fingerprint": None
            }
    
    def has_changed(self, other_fingerprint: Dict[str, Any]) -> bool:
        """检查文件是否发生变化"""
        current = self.compute()
        return current["fingerprint"] != other_fingerprint.get("fingerprint")
