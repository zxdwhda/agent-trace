#!/usr/bin/env python3
"""
AgentTrace 监控服务（v0.3.2）

新特性：
1. 事件去重机制（借鉴 LangSmith run_id 幂等性）
2. Offset 持久化（借鉴 OTel FileLog Receiver）
3. 文件指纹检测（借鉴 Vector）
4. 截断检测（借鉴 Fluent Bit）
5. 增强日志输出（用于调试重复问题）
"""

import os
import time
from pathlib import Path
from typing import Dict, Optional
import logging

import cozeloop

from ..parsers.jsonl_reader import IncrementalJSONLReader, JSONLRecord
from ..parsers.wire_parser import WireEvent, WireEventType
from ..handlers.event_handler import (
    TurnBeginHandler, TurnEndHandler, StepBeginHandler,
    ContentPartHandler, ToolCallHandler, ToolResultHandler,
    StatusUpdateHandler, ApprovalRequestHandler, ApprovalResponseHandler
)
from .session_state import SessionState
from .dedup import EventDeduplicator
from .persistent_offset import PersistentOffsetStore

logger = logging.getLogger("agent_trace")


class AgentTraceMonitor:
    """AgentTrace 监控服务"""
    
    def __init__(
        self,
        sessions_dir: str,
        poll_interval: float = 2.0,
        active_timeout_minutes: int = 30,
        enable_deduplication: bool = True,
        enable_persistent_offset: bool = True
    ):
        """
        初始化监控服务
        
        Args:
            sessions_dir: 会话目录
            poll_interval: 轮询间隔（秒）
            active_timeout_minutes: 活跃会话超时时间（分钟）
            enable_deduplication: 是否启用事件去重
            enable_persistent_offset: 是否启用 offset 持久化
        """
        self.sessions_dir = Path(sessions_dir).expanduser()
        self.poll_interval = poll_interval
        self.active_timeout_minutes = active_timeout_minutes
        self.enable_deduplication = enable_deduplication
        self.enable_persistent_offset = enable_persistent_offset
        
        # 去重管理器
        self.deduplicator: Optional[EventDeduplicator] = None
        if enable_deduplication:
            self.deduplicator = EventDeduplicator()
        
        # Offset 存储
        self.offset_store: Optional[PersistentOffsetStore] = None
        if enable_persistent_offset:
            self.offset_store = PersistentOffsetStore()
        
        # 文件读取器映射
        self.file_readers: Dict[str, IncrementalJSONLReader] = {}
        # Session 状态映射
        self.session_states: Dict[str, SessionState] = {}
        
        # 事件处理器映射
        self.handlers = {
            WireEventType.TURN_BEGIN: TurnBeginHandler(),
            WireEventType.TURN_END: TurnEndHandler(),
            WireEventType.STEP_BEGIN: StepBeginHandler(),
            WireEventType.CONTENT_PART: ContentPartHandler(),
            WireEventType.TOOL_CALL: ToolCallHandler(),
            WireEventType.TOOL_RESULT: ToolResultHandler(),
            WireEventType.STATUS_UPDATE: StatusUpdateHandler(),
            WireEventType.APPROVAL_REQUEST: ApprovalRequestHandler(),
            WireEventType.APPROVAL_RESPONSE: ApprovalResponseHandler(),
        }
        
        self.running = False
        self._scan_counter = 0
        # 每 30 次轮询扫描一次新会话
        self._scan_interval = 30
        # 清理计数器
        self._cleanup_counter = 0
        # 每 300 次轮询执行一次清理（约10分钟）
        self._cleanup_interval = 300
    
    def start(self):
        """启动监控服务"""
        logger.info("=" * 60)
        logger.info("AgentTrace Monitor v0.3.2 Starting...")
        logger.info(f"Sessions dir: {self.sessions_dir}")
        logger.info(f"Poll interval: {self.poll_interval}s")
        logger.info(f"Deduplication: {'enabled' if self.enable_deduplication else 'disabled'}")
        logger.info(f"Persistent offset: {'enabled' if self.enable_persistent_offset else 'disabled'}")
        logger.info("=" * 60)
        
        # 打印去重统计
        if self.deduplicator:
            stats = self.deduplicator.get_stats()
            logger.info(f"[INIT] Deduplicator stats: {stats}")
        
        # 扫描现有会话
        self._scan_existing_sessions()
        
        self.running = True
        try:
            while self.running:
                self._scan_counter += 1
                self._cleanup_counter += 1
                
                # 定期扫描新会话
                if self._scan_counter >= self._scan_interval:
                    self._scan_new_sessions()
                    self._scan_counter = 0
                
                # 定期清理过期数据
                if self._cleanup_counter >= self._cleanup_interval:
                    self._cleanup_old_data()
                    self._cleanup_counter = 0
                
                self._process_all_files()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            logger.info("Received KeyboardInterrupt")
        finally:
            self.stop()
    
    def stop(self):
        """停止监控服务"""
        if not self.running:
            return
        
        logger.info("Stopping monitor...")
        self.running = False
        
        # 结束所有会话
        for session_id, state in self.session_states.items():
            logger.info(f"Ending session: {session_id[:16]}...")
            try:
                state.end_turn(time.time())
            except Exception as e:
                logger.error(f"Error ending session {session_id}: {e}")
        
        # 刷新 SDK 缓冲区
        try:
            cozeloop.flush()
            logger.info("Flush completed")
        except Exception as e:
            logger.error(f"Error flushing: {e}")
        
        # 打印最终统计
        if self.deduplicator:
            stats = self.deduplicator.get_stats()
            logger.info(f"[FINAL] Deduplicator stats: {stats}")
        
        if self.offset_store:
            stats = self.offset_store.get_stats()
            logger.info(f"[FINAL] Offset store stats: {stats}")
        
        logger.info("Monitor stopped")
    
    def _cleanup_old_data(self):
        """清理过期数据"""
        if self.deduplicator:
            cleaned = self.deduplicator.cleanup_expired()
            if cleaned > 0:
                logger.info(f"[CLEANUP] Cleaned up {cleaned} expired dedup records")
        
        if self.offset_store:
            cleaned = self.offset_store.cleanup_old_records()
            if cleaned > 0:
                logger.info(f"[CLEANUP] Cleaned up {cleaned} old offset records")
    
    def _scan_existing_sessions(self):
        """扫描现有会话，只处理最近5分钟内的活跃会话"""
        if not self.sessions_dir.exists():
            logger.warning(f"Sessions dir does not exist: {self.sessions_dir}")
            return
        
        count = 0
        now = time.time()
        startup_scan_minutes = 5
        
        try:
            for workdir_dir in self.sessions_dir.iterdir():
                if not workdir_dir.is_dir():
                    continue
                
                for session_dir in workdir_dir.iterdir():
                    if not session_dir.is_dir():
                        continue
                    
                    wire_file = session_dir / 'wire.jsonl'
                    if not wire_file.exists():
                        continue
                    
                    # 检查文件修改时间
                    try:
                        mtime = wire_file.stat().st_mtime
                        age_minutes = (now - mtime) / 60
                        
                        if age_minutes < startup_scan_minutes:
                            logger.info(
                                f"[SCAN] Found active session: {session_dir.name[:16]}... "
                                f"({age_minutes:.1f}min ago)"
                            )
                            self._register_file(str(wire_file), skip_to_end=True)
                            count += 1
                    except Exception as e:
                        logger.error(f"[SCAN] Error checking session {session_dir}: {e}")
        
        except Exception as e:
            logger.error(f"[SCAN] Error scanning sessions: {e}")
        
        logger.info(f"[SCAN] Registered {count} active session(s) within {startup_scan_minutes}min")
    
    def _scan_new_sessions(self):
        """扫描新创建的会话（只扫描最近1分钟内创建的）"""
        if not self.sessions_dir.exists():
            return
        
        count = 0
        now = time.time()
        try:
            for workdir_dir in self.sessions_dir.iterdir():
                if not workdir_dir.is_dir():
                    continue
                
                for session_dir in workdir_dir.iterdir():
                    if not session_dir.is_dir():
                        continue
                    
                    wire_file = session_dir / 'wire.jsonl'
                    if not wire_file.exists():
                        continue
                    
                    # 检查是否已注册
                    if str(wire_file) in self.file_readers:
                        continue
                    
                    # 只处理最近1分钟内创建的会话
                    try:
                        mtime = wire_file.stat().st_mtime
                        age_seconds = now - mtime
                        
                        if age_seconds < 60:
                            logger.info(f"[SCAN] Found new session: {session_dir.name[:16]}... ({age_seconds:.0f}s ago)")
                            # 新会话从文件末尾开始，不读取历史数据
                            self._register_file(str(wire_file), start_from_end=True)
                            count += 1
                    except Exception as e:
                        logger.error(f"[SCAN] Error registering new session {session_dir}: {e}")
        
        except Exception as e:
            logger.error(f"[SCAN] Error scanning new sessions: {e}")
        
        if count > 0:
            logger.info(f"[SCAN] Registered {count} new session(s)")
    
    def _register_file(
        self,
        filepath: str,
        skip_to_end: bool = False,
        read_last_n: int = 0,
        start_from_end: bool = False
    ):
        """
        注册监控文件
        
        Args:
            filepath: 文件路径
            skip_to_end: 是否跳到末尾（完全跳历史）
            read_last_n: 读取最后 N 条记录
            start_from_end: 新会话从末尾开始（完全不读历史）
        """
        if filepath in self.file_readers:
            return
        
        # 验证文件路径
        filepath_obj = Path(filepath)
        if not filepath_obj.name == 'wire.jsonl':
            logger.warning(f"[REGISTER] Unexpected file name: {filepath_obj.name}, expected 'wire.jsonl'")
        
        # 获取 session_id
        session_dir = filepath_obj.parent
        session_id = session_dir.name
        
        # 创建读取器
        reader = IncrementalJSONLReader(
            filepath,
            offset_store=self.offset_store,
            auto_save_offset=True
        )
        
        # 配置读取位置
        if start_from_end:
            # 新会话：从文件末尾开始，完全不读历史
            reader.skip_to_end()
            logger.info(f"[REGISTER] New session registered from end: {session_id[:16]}...")
        elif skip_to_end:
            reader.skip_to_end()
        elif read_last_n > 0:
            reader.skip_to_last_n_records(read_last_n)
        
        self.file_readers[filepath] = reader
        
        # 创建 Session 状态（传入去重管理器）
        self.session_states[session_id] = SessionState(
            session_id=session_id,
            deduplicator=self.deduplicator,
            turn_index=0
        )
        
        logger.info(f"[REGISTER] Registered file: {session_id[:16]}... (filepath={filepath})")
    
    def _process_all_files(self):
        """处理所有监控的文件"""
        for filepath, reader in list(self.file_readers.items()):
            if not os.path.exists(filepath):
                # 文件被删除，清理
                session_id = Path(filepath).parent.name
                del self.file_readers[filepath]
                
                # 清理 offset 记录
                if self.offset_store:
                    self.offset_store.delete_offset(filepath)
                
                # 清理 session 状态
                if session_id in self.session_states:
                    try:
                        self.session_states[session_id].end_turn(time.time())
                    except Exception as e:
                        logger.warning(f"[CLEANUP] Error ending session {session_id[:16]}...: {e}")
                    del self.session_states[session_id]
                    logger.info(f"[CLEANUP] Cleaned up session: {session_id[:16]}...")
                continue
            
            try:
                for record_data in reader.read_new_records():
                    self._process_record(filepath, record_data)
            except Exception as e:
                logger.error(f"[PROCESS] Error processing {filepath}: {e}")
    
    def _process_record(self, filepath: str, record_data: JSONLRecord):
        """处理单条记录"""
        session_id = Path(filepath).parent.name
        state = self.session_states.get(session_id)
        
        if not state:
            logger.warning(f"[PROCESS] No session state for {session_id[:16]}...")
            return
        
        record = record_data.record
        
        # 解析事件
        event = WireEvent.from_record(record)
        if not event:
            # 记录原始数据以便调试
            record_type = record.get('type', 'unknown')
            if record_type != 'metadata':
                logger.debug(f"[PROCESS] 无法解析事件: type={record_type}, keys={list(record.keys())}")
            return
        
        # 获取处理器
        handler = self.handlers.get(event.event_type)
        if not handler:
            logger.debug(f"[PROCESS] 无处理器: {event.event_type}")
            return
        
        # 处理事件
        try:
            result = handler.handle(state, event)
            
            # 日志记录关键事件
            if event.event_type == WireEventType.TURN_BEGIN:
                user_input = event.payload.get('user_input', '')
                if isinstance(user_input, str):
                    preview = user_input[:50] + "..." if len(user_input) > 50 else user_input
                else:
                    preview = "[complex input]"
                root_span_status = "✓" if state.root_span else "✗"
                logger.info(f"[EVENT:{session_id[:8]}] TurnBegin: {preview} (root_span={root_span_status})")
            
            elif event.event_type == WireEventType.STEP_BEGIN:
                step_n = event.payload.get('n', 0)
                current_step_status = "✓" if state.current_step else "✗"
                logger.info(f"[EVENT:{session_id[:8]}] StepBegin: step={step_n} (current_step={current_step_status})")
            
            elif event.event_type == WireEventType.TURN_END:
                logger.info(f"[EVENT:{session_id[:8]}] TurnEnd - Trace completed")
        
        except Exception as e:
            logger.error(f"[EVENT:{session_id[:8]}] Error handling event {event.event_type}: {e}", exc_info=True)
    
    def get_stats(self) -> Dict:
        """获取监控统计信息"""
        stats = {
            "active_sessions": len(self.session_states),
            "monitored_files": len(self.file_readers),
            "deduplication_enabled": self.enable_deduplication,
            "persistent_offset_enabled": self.enable_persistent_offset,
        }
        
        if self.deduplicator:
            stats["deduplicator"] = self.deduplicator.get_stats()
        
        if self.offset_store:
            stats["offset_store"] = self.offset_store.get_stats()
        
        return stats
