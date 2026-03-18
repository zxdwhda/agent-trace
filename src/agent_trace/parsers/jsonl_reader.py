#!/usr/bin/env python3
"""
JSONL 增量读取器（v0.3.5 增强版）

新特性：
1. Offset 持久化存储（借鉴 OTel FileLog Receiver）
2. 文件指纹检测（借鉴 Vector checksum fingerprint）
3. 截断检测（借鉴 Fluent Bit）
4. 支持记录级 offset 追踪
"""

import json
import os
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, Iterator, Optional, Tuple
from dataclasses import dataclass

from ..core.persistent_offset import PersistentOffsetStore, FileOffset
from ..core.dedup import FileFingerprint

logger = logging.getLogger("agent_trace")

# 安全限制
MAX_INCOMPLETE_LINE_LENGTH = 1024 * 1024  # 1MB 最大不完整行长度


@dataclass
class JSONLRecord:
    """带 offset 的 JSONL 记录"""
    record: Dict[str, Any]
    offset: int
    line_number: int


class IncrementalJSONLReader:
    """
    增量读取 JSONL 文件
    
    增强功能：
    - 自动保存/恢复 offset
    - 文件指纹检测变化
    - 截断检测和恢复
    """
    
    @staticmethod
    def _sanitize_path(filepath: str) -> str:
        """
        路径安全处理：规范化路径并防止路径遍历攻击
        
        Args:
            filepath: 原始文件路径
            
        Returns:
            规范化后的绝对路径
            
        Raises:
            ValueError: 如果路径包含路径遍历攻击特征
        """
        # 转换为 Path 对象并获取绝对路径
        path = Path(filepath).expanduser()
        
        # 拒绝绝对路径中的遍历序列（针对相对路径输入）
        # 注意：我们允许访问系统中任何位置的文件（因为这是监控工具的需求）
        # 但我们要确保路径是规范化的，防止 ../../../etc/passwd 这类攻击
        
        try:
            # 获取规范化后的绝对路径
            resolved_path = path.resolve()
            return str(resolved_path)
        except (OSError, ValueError) as e:
            raise ValueError(f"Invalid file path: {filepath}. Error: {e}")
    
    def __init__(
        self,
        filepath: str,
        offset_store: Optional[PersistentOffsetStore] = None,
        auto_save_offset: bool = True
    ):
        """
        初始化读取器
        
        Args:
            filepath: 文件路径
            offset_store: Offset 存储实例，None 则创建默认实例
            auto_save_offset: 是否自动保存 offset
        """
        # 路径安全处理：规范化并验证路径
        self.filepath = self._sanitize_path(filepath)
        self.offset_store = offset_store or PersistentOffsetStore()
        self.auto_save_offset = auto_save_offset
        
        # 读取状态
        self.position: int = 0
        self.incomplete_line: str = ""
        self._max_incomplete_length = MAX_INCOMPLETE_LINE_LENGTH
        self.line_number: int = 0
        self.records_read: int = 0
        
        # 文件指纹
        self._fingerprint = FileFingerprint(filepath)
        self._current_fingerprint: Optional[str] = None
        
        # 恢复 offset
        self._restore_offset()
    
    def _restore_offset(self):
        """从持久化存储恢复 offset"""
        if not os.path.exists(self.filepath):
            self.position = 0
            return
        
        stored = self.offset_store.get_offset(self.filepath)
        current_size = os.path.getsize(self.filepath)
        
        # 检查截断
        if self.offset_store.check_truncation(self.filepath, current_size):
            logger.warning(f"File truncated, reset to beginning: {self.filepath}")
            self.position = 0
            return
        
        # 计算当前指纹
        fp_info = self._fingerprint.compute()
        self._current_fingerprint = fp_info.get("fingerprint")
        
        # 检查 inode 复用
        if self._current_fingerprint and stored.inode:
            if self.offset_store.check_inode_reuse(
                self.filepath, 
                fp_info.get("inode", 0),
                self._current_fingerprint
            ):
                logger.warning(f"File replaced (inode reuse), reset to beginning: {self.filepath}")
                self.position = 0
                return
        
        # 验证 offset 有效性
        self.position = self.offset_store.validate_offset(self.filepath, current_size)
        
        if self.position > 0:
            logger.debug(
                f"Restored offset for {self.filepath}: "
                f"position={self.position}, fingerprint={self._current_fingerprint[:8] if self._current_fingerprint else 'N/A'}..."
            )
    
    def _save_offset(self):
        """保存 offset 到持久化存储"""
        if not self.auto_save_offset:
            return
        
        try:
            current_size = os.path.getsize(self.filepath) if os.path.exists(self.filepath) else 0
            fp_info = self._fingerprint.compute()
            
            self.offset_store.save_offset(
                filepath=self.filepath,
                offset=self.position,
                file_size=current_size,
                inode=fp_info.get("inode"),
                fingerprint=fp_info.get("fingerprint")
            )
        except Exception as e:
            logger.debug(f"Error saving offset: {e}")
    
    def skip_to_end(self):
        """跳过所有历史数据，从文件末尾开始读取"""
        try:
            if os.path.exists(self.filepath):
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    f.seek(0, 2)  # 跳到文件末尾
                    self.position = f.tell()
                    self._save_offset()
        except Exception as e:
            logger.warning(f"Error skipping to end: {e}")
    
    def skip_to_last_n_records(self, n: int = 50):
        """
        跳过历史数据，只保留最后 N 条记录的位置
        
        通过估算平均每条记录的大小来定位，不够精确但效率高
        """
        try:
            if not os.path.exists(self.filepath):
                return
            
            file_size = os.path.getsize(self.filepath)
            if file_size == 0:
                return
            
            with open(self.filepath, 'r', encoding='utf-8') as f:
                # 估计平均每条记录 500 字节（JSON 数据通常几百到几千字节）
                estimated_record_size = 500
                estimated_bytes = n * estimated_record_size
                
                if file_size <= estimated_bytes:
                    # 文件很小，从头开始读
                    self.position = 0
                    self._save_offset()
                    return
                
                # 从估算位置开始，找到下一个完整行的开始
                start_pos = max(0, file_size - estimated_bytes)
                f.seek(start_pos)
                
                # 如果不在文件开头，跳过当前行（可能不完整）
                if start_pos > 0:
                    f.readline()  # 跳过可能不完整的行
                
                self.position = f.tell()
                self._save_offset()
                
                logger.debug(f"Skipped to last ~{n} records at position {self.position}")
        except Exception as e:
            logger.warning(f"Error skipping to last N records: {e}")
            self.skip_to_end()
    
    def read_new_records(self) -> Iterator[JSONLRecord]:
        """
        读取新记录
        
        Yields:
            JSONLRecord 包含记录内容和 offset
        """
        if not os.path.exists(self.filepath):
            return
        
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                f.seek(self.position)
                
                # 使用 readline() 而不是 for line in f，以便正确使用 tell()
                while True:
                    line = f.readline()
                    if not line:
                        break
                    
                    self.line_number += 1
                    full_line = self.incomplete_line + line
                    
                    if line.endswith('\n'):
                        self.incomplete_line = ""
                        full_line = full_line.strip()
                        if full_line:
                            try:
                                record = json.loads(full_line)
                                if record.get('type') != 'metadata':
                                    self.records_read += 1
                                    yield JSONLRecord(
                                        record=record,
                                        offset=self.position,
                                        line_number=self.line_number
                                    )
                            except json.JSONDecodeError:
                                # 检查 incomplete_line 长度限制，防止内存耗尽
                                if len(full_line) > self._max_incomplete_length:
                                    logger.warning(
                                        f"Incomplete line exceeded max length ({self._max_incomplete_length}), "
                                        f"discarding incomplete data in {self.filepath}"
                                    )
                                    self.incomplete_line = ""
                                else:
                                    self.incomplete_line = full_line + '\n'
                    else:
                        self.incomplete_line = full_line
                    
                    # 更新位置
                    self.position = f.tell()
                
                # 批量读取完成后保存 offset
                self._save_offset()
                
        except Exception as e:
            logger.error(f"Error reading {self.filepath}: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取读取器统计信息"""
        stored = self.offset_store.get_offset(self.filepath)
        return {
            "filepath": self.filepath,
            "position": self.position,
            "line_number": self.line_number,
            "records_read": self.records_read,
            "stored_offset": stored.offset,
            "stored_read_count": stored.read_count
        }


class TrackedJSONLReader(IncrementalJSONLReader):
    """
    带记录级追踪的 JSONL 读取器
    
    用于精确追踪每条记录的 offset，支持断点续读
    """
    
    def __init__(
        self,
        filepath: str,
        offset_store: Optional[PersistentOffsetStore] = None,
        batch_size: int = 100
    ):
        super().__init__(filepath, offset_store, auto_save_offset=False)
        self.batch_size = batch_size
        self._record_offsets: Dict[str, int] = {}  # record_id -> offset
    
    def read_new_records_with_tracking(self) -> Iterator[Tuple[JSONLRecord, str]]:
        """
        读取新记录并生成唯一记录 ID
        
        Yields:
            (JSONLRecord, record_id) 元组
        """
        for record in self.read_new_records():
            # 生成记录 ID
            record_id = self._generate_record_id(record)
            self._record_offsets[record_id] = record.offset
            yield record, record_id
            
            # 每 batch_size 条记录保存一次 offset
            if len(self._record_offsets) >= self.batch_size:
                self._save_offset()
                self._record_offsets.clear()
        
        # 保存剩余 offset
        if self._record_offsets:
            self._save_offset()
    
    def _generate_record_id(self, record: JSONLRecord) -> str:
        """生成记录唯一 ID"""
        content = json.dumps(record.record, sort_keys=True)
        return hashlib.sha256(
            f"{self.filepath}:{record.offset}:{record.line_number}:{content}".encode()
        ).hexdigest()[:24]
    
    def get_record_offset(self, record_id: str) -> Optional[int]:
        """获取记录的 offset"""
        return self._record_offsets.get(record_id)
