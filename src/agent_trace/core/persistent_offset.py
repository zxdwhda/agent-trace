#!/usr/bin/env python3
"""
持久化 Offset 管理器

借鉴：OTel FileLog Receiver + Fluent Bit 的 offset 持久化机制
使用 SQLite 存储文件 offset，确保进程重启后不会重复读取
"""

import sqlite3
import threading
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

from .dedup import FileFingerprint

logger = logging.getLogger("agent_trace")


@dataclass
class FileOffset:
    """文件 Offset 记录"""
    filepath: str
    offset: int
    inode: Optional[int]
    fingerprint: Optional[str]
    file_size: int
    last_read_at: float
    read_count: int


class PersistentOffsetStore:
    """
    持久化 Offset 存储
    
    功能：
    1. 存储每个文件的读取位置
    2. 检测文件截断（truncation）
    3. 检测 inode 复用（文件被替换）
    4. WAL 模式保证数据安全
    
    借鉴：Fluent Bit SQLite WAL 模式 + 截断检测
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        初始化 Offset 存储
        
        Args:
            db_path: SQLite 数据库路径，默认 ~/.kimi/monitor/offsets.db
        """
        if db_path is None:
            db_dir = Path.home() / ".kimi" / "monitor"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "offsets.db")
        
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()
        
        logger.info(f"PersistentOffsetStore initialized: db={db_path}")
    
    def _init_db(self):
        """初始化 SQLite 数据库"""
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            # WAL 模式提高并发性能和数据安全
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            
            # 文件 offset 表
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
            
            # 索引
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_last_read ON file_offsets(last_read_at)
            """)
            
            conn.commit()
    
    def get_offset(self, filepath: str) -> FileOffset:
        """
        获取文件的 offset 信息
        
        Args:
            filepath: 文件路径
            
        Returns:
            FileOffset 对象
        """
        with self._lock:
            try:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    cursor = conn.execute(
                        """
                        SELECT offset, inode, fingerprint, file_size, last_read_at, read_count
                        FROM file_offsets WHERE filepath = ?
                        """,
                        (filepath,)
                    )
                    row = cursor.fetchone()
                    
                    if row:
                        return FileOffset(
                            filepath=filepath,
                            offset=row[0],
                            inode=row[1],
                            fingerprint=row[2],
                            file_size=row[3],
                            last_read_at=row[4],
                            read_count=row[5]
                        )
            except sqlite3.Error as e:
                logger.warning(f"SQLite error getting offset: {e}")
            
            # 默认返回初始状态
            return FileOffset(
                filepath=filepath,
                offset=0,
                inode=None,
                fingerprint=None,
                file_size=0,
                last_read_at=0,
                read_count=0
            )
    
    def save_offset(
        self,
        filepath: str,
        offset: int,
        file_size: int,
        inode: Optional[int] = None,
        fingerprint: Optional[str] = None
    ):
        """
        保存文件 offset
        
        Args:
            filepath: 文件路径
            offset: 读取位置
            file_size: 文件大小
            inode: 文件 inode
            fingerprint: 文件指纹
        """
        with self._lock:
            try:
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
                    conn.commit()
            except sqlite3.Error as e:
                logger.warning(f"SQLite error saving offset: {e}")
    
    def check_truncation(self, filepath: str, current_size: int) -> bool:
        """
        检查文件是否被截断
        
        Args:
            filepath: 文件路径
            current_size: 当前文件大小
            
        Returns:
            True 表示文件被截断
        """
        stored = self.get_offset(filepath)
        
        # 如果当前大小小于存储的大小，说明文件被截断了
        if current_size < stored.file_size:
            logger.warning(
                f"File truncation detected: {filepath} "
                f"(was {stored.file_size}, now {current_size})"
            )
            return True
        
        return False
    
    def check_inode_reuse(self, filepath: str, current_inode: int, current_fingerprint: str) -> bool:
        """
        检查是否发生 inode 复用（文件被替换但 inode 相同）
        
        Args:
            filepath: 文件路径
            current_inode: 当前 inode
            current_fingerprint: 当前文件指纹
            
        Returns:
            True 表示文件被替换
        """
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
    
    def validate_offset(self, filepath: str, current_size: int) -> int:
        """
        验证并修正 offset
        
        Args:
            filepath: 文件路径
            current_size: 当前文件大小
            
        Returns:
            修正后的 offset
        """
        stored = self.get_offset(filepath)
        
        # 如果 offset 超过当前文件大小，从头开始
        if stored.offset > current_size:
            logger.warning(
                f"Invalid offset detected: {filepath} "
                f"(stored={stored.offset}, current_size={current_size})"
            )
            return 0
        
        return stored.offset
    
    def delete_offset(self, filepath: str):
        """删除文件的 offset 记录"""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    conn.execute("DELETE FROM file_offsets WHERE filepath = ?", (filepath,))
                    conn.commit()
            except sqlite3.Error as e:
                logger.warning(f"SQLite error deleting offset: {e}")
    
    def cleanup_old_records(self, max_age_hours: int = 168) -> int:
        """
        清理旧记录
        
        Args:
            max_age_hours: 最大保留时间（小时），默认 7 天
            
        Returns:
            清理的记录数
        """
        cutoff_time = time.time() - (max_age_hours * 3600)
        
        with self._lock:
            try:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    cursor = conn.execute(
                        "DELETE FROM file_offsets WHERE last_read_at < ?",
                        (cutoff_time,)
                    )
                    conn.commit()
                    deleted = cursor.rowcount
                    if deleted > 0:
                        logger.info(f"Cleaned up {deleted} old offset records")
                    return deleted
            except sqlite3.Error as e:
                logger.warning(f"SQLite error during cleanup: {e}")
                return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*),
                        SUM(read_count),
                        MAX(last_read_at),
                        SUM(file_size)
                    FROM file_offsets
                """)
                total, total_reads, last_read, total_size = cursor.fetchone()
                
                return {
                    "tracked_files": total or 0,
                    "total_reads": total_reads or 0,
                    "last_read_at": last_read or 0,
                    "total_size": total_size or 0,
                    "db_path": self.db_path
                }
        except sqlite3.Error as e:
            logger.warning(f"SQLite error getting stats: {e}")
            return {
                "tracked_files": -1,
                "error": str(e)
            }
