"""
Trace Context 管理机制

参考 OpenClaw 设计，适配 Python Agent 追踪场景
提供全局唯一追踪 ID、run_id/turn_id 生命周期管理、跨 Hook 数据传递
"""

import uuid
import time
from typing import Dict, Optional, Any, List, Callable
from dataclasses import dataclass, field
from contextvars import ContextVar
from threading import Lock
import logging

logger = logging.getLogger(__name__)

# 全局上下文变量 - 用于异步/线程间传递
current_trace_context: ContextVar[Optional["TraceContext"]] = ContextVar(
    "current_trace_context", default=None
)


def generate_trace_id() -> str:
    """生成 32 位十六进制 trace_id"""
    return uuid.uuid4().hex + uuid.uuid4().hex[:16]


def generate_span_id() -> str:
    """生成 16 位十六进制 span_id"""
    return uuid.uuid4().hex[:16]


def generate_run_id() -> str:
    """生成运行 ID"""
    return f"run_{uuid.uuid4().hex[:12]}"


@dataclass
class SpanInfo:
    """Span 信息"""
    span_id: str
    span_name: str
    start_time: float
    parent_id: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "span_name": self.span_name,
            "start_time": self.start_time,
            "parent_id": self.parent_id,
            "attributes": self.attributes,
        }


@dataclass  
class TurnState:
    """单次 Turn 的状态（从 SessionState 分离）"""
    turn_id: str
    start_time: float = field(default_factory=time.time)
    
    # Token 累计（Turn 级别）
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    
    # 内容
    user_input: str = ""
    assistant_output: str = ""
    think_content: str = ""
    
    # 模型信息
    model_name: str = "unknown"
    model_provider: str = "moonshot"
    
    def add_tokens(self, input_tokens: int, output_tokens: int, 
                   cache_read: int = 0, cache_write: int = 0):
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cache_read_tokens += cache_read
        self.cache_write_tokens += cache_write
        self.total_tokens += input_tokens + output_tokens + cache_write


class TraceContext:
    """
    追踪上下文 - 单次 Turn 的完整追踪信息
    
    对应 OpenClaw 的 ctx 对象，包含：
    - trace_id: 全局唯一追踪 ID
    - root_span_id: 根 Span ID
    - run_id: 运行实例 ID
    - turn_id: Turn ID（多轮对话）
    - channel_id: 通道/租户 ID
    """
    
    def __init__(
        self,
        run_id: str,
        channel_id: str,
        original_channel_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        turn_id: Optional[str] = None,
    ):
        # 核心 ID（参考 OpenClaw）
        self.trace_id = trace_id or generate_trace_id()
        self.root_span_id = generate_span_id()
        self.run_id = run_id
        self.turn_id = turn_id or run_id
        self.channel_id = channel_id
        self.original_channel_id = original_channel_id or channel_id
        
        # 时间戳
        self.created_at = time.time()
        self.root_span_start_time = self.created_at
        
        # Span 栈（支持并发）
        self._span_stack: List[SpanInfo] = []
        self._active_spans: Dict[str, SpanInfo] = {}  # span_id -> SpanInfo
        self._span_lock = Lock()
        
        # Turn 级别状态
        self.turn_state = TurnState(turn_id=self.turn_id)
        
        # 用户自定义属性
        self.attributes: Dict[str, Any] = {}
        
        # Hook 标记
        self._processed_hooks: set = set()
    
    # ============ Span 管理 ============
    
    def start_span(self, span_name: str, parent_id: Optional[str] = None) -> SpanInfo:
        """开始一个新的 Span"""
        with self._span_lock:
            parent = parent_id or (self._span_stack[-1].span_id if self._span_stack else None)
            span = SpanInfo(
                span_id=generate_span_id(),
                span_name=span_name,
                start_time=time.time(),
                parent_id=parent,
            )
            self._span_stack.append(span)
            self._active_spans[span.span_id] = span
            return span
    
    def end_span(self, span_id: Optional[str] = None) -> Optional[SpanInfo]:
        """结束 Span"""
        with self._span_lock:
            if span_id:
                span = self._active_spans.pop(span_id, None)
                if span and span in self._span_stack:
                    self._span_stack.remove(span)
                return span
            elif self._span_stack:
                span = self._span_stack.pop()
                self._active_spans.pop(span.span_id, None)
                return span
            return None
    
    def get_current_span(self) -> Optional[SpanInfo]:
        """获取当前 Span"""
        with self._span_lock:
            return self._span_stack[-1] if self._span_stack else None
    
    def get_span_stack(self) -> List[SpanInfo]:
        """获取 Span 栈副本"""
        with self._span_lock:
            return self._span_stack.copy()
    
    # ============ 属性管理 ============
    
    def set_attribute(self, key: str, value: Any):
        """设置属性"""
        self.attributes[key] = value
    
    def get_attribute(self, key: str, default: Any = None) -> Any:
        """获取属性"""
        return self.attributes.get(key, default)
    
    def mark_hook_processed(self, hook_name: str):
        """标记 Hook 已处理"""
        self._processed_hooks.add(hook_name)
    
    def is_hook_processed(self, hook_name: str) -> bool:
        """检查 Hook 是否已处理"""
        return hook_name in self._processed_hooks
    
    # ============ 序列化 ============
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "trace_id": self.trace_id,
            "root_span_id": self.root_span_id,
            "run_id": self.run_id,
            "turn_id": self.turn_id,
            "channel_id": self.channel_id,
            "original_channel_id": self.original_channel_id,
            "created_at": self.created_at,
            "span_count": len(self._active_spans),
            "turn_state": {
                "input_tokens": self.turn_state.input_tokens,
                "output_tokens": self.turn_state.output_tokens,
                "cache_read_tokens": self.turn_state.cache_read_tokens,
                "cache_write_tokens": self.turn_state.cache_write_tokens,
                "total_tokens": self.turn_state.total_tokens,
                "model_name": self.turn_state.model_name,
            },
        }
    
    def __repr__(self) -> str:
        return f"TraceContext(trace_id={self.trace_id[:8]}..., run_id={self.run_id})"


class TraceContextManager:
    """
    TraceContext 管理器 - 应用级单例
    
    对应 OpenClaw 的 contextByChannelId + contextByRunId
    """
    
    _instance: Optional["TraceContextManager"] = None
    _lock = Lock()
    
    def __new__(cls) -> "TraceContextManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 双向索引（参考 OpenClaw）
        self._context_by_id: Dict[str, TraceContext] = {}      # trace_id -> ctx
        self._context_by_run: Dict[str, TraceContext] = {}     # run_id -> ctx
        self._context_by_channel: Dict[str, TraceContext] = {} # channel_id -> ctx
        
        self._lock = Lock()
        self._initialized = True
    
    def start_turn(
        self,
        run_id: str,
        channel_id: str,
        original_channel_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        turn_id: Optional[str] = None,
    ) -> TraceContext:
        """
        开始一个新的 Turn
        
        对应 OpenClaw 的 startTurn 函数
        """
        ctx = TraceContext(
            run_id=run_id,
            channel_id=channel_id,
            original_channel_id=original_channel_id,
            trace_id=trace_id,
            turn_id=turn_id,
        )
        
        with self._lock:
            self._context_by_id[ctx.trace_id] = ctx
            self._context_by_run[run_id] = ctx
            self._context_by_channel[channel_id] = ctx
        
        # 设置为当前上下文
        current_trace_context.set(ctx)
        
        logger.debug(f"Started turn: {ctx}")
        return ctx
    
    def get_by_trace_id(self, trace_id: str) -> Optional[TraceContext]:
        """通过 trace_id 获取上下文"""
        return self._context_by_id.get(trace_id)
    
    def get_by_run_id(self, run_id: str) -> Optional[TraceContext]:
        """通过 run_id 获取上下文"""
        return self._context_by_run.get(run_id)
    
    def get_by_channel(self, channel_id: str) -> Optional[TraceContext]:
        """通过 channel_id 获取上下文"""
        return self._context_by_channel.get(channel_id)
    
    def get_or_create_context(
        self,
        channel_id: str,
        run_id: Optional[str] = None,
        hook_name: Optional[str] = None,
    ) -> tuple[TraceContext, bool]:
        """
        获取或创建上下文
        
        对应 OpenClaw 的 getOrCreateContext
        
        Returns:
            (ctx, is_new): 上下文对象和是否新创建
        """
        # 优先级 1: channel_id
        ctx = self.get_by_channel(channel_id)
        
        # 优先级 2: run_id
        if ctx is None and run_id:
            ctx = self.get_by_run_id(run_id)
        
        # 优先级 3: 创建新的
        if ctx is None:
            effective_run_id = run_id or generate_run_id()
            ctx = self.start_turn(
                run_id=effective_run_id,
                channel_id=channel_id,
            )
            return ctx, True
        
        return ctx, False
    
    def end_turn(self, run_id: str) -> Optional[TraceContext]:
        """结束 Turn，清理上下文"""
        with self._lock:
            ctx = self._context_by_run.pop(run_id, None)
            if ctx:
                self._context_by_id.pop(ctx.trace_id, None)
                self._context_by_channel.pop(ctx.channel_id, None)
        
        if ctx:
            logger.debug(f"Ended turn: {ctx}")
        return ctx
    
    def get_current_context(self) -> Optional[TraceContext]:
        """获取当前上下文（从 ContextVar）"""
        return current_trace_context.get()
    
    def set_current_context(self, ctx: TraceContext):
        """设置当前上下文"""
        current_trace_context.set(ctx)
    
    def clear_current_context(self):
        """清除当前上下文"""
        current_trace_context.set(None)
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        with self._lock:
            return {
                "total_contexts": len(self._context_by_id),
                "by_trace_id": len(self._context_by_id),
                "by_run_id": len(self._context_by_run),
                "by_channel": len(self._context_by_channel),
            }


# 全局管理器实例
trace_manager = TraceContextManager()


# ============ 便捷函数 ============

def get_current_trace_id() -> Optional[str]:
    """获取当前 trace_id"""
    ctx = trace_manager.get_current_context()
    return ctx.trace_id if ctx else None


def get_current_run_id() -> Optional[str]:
    """获取当前 run_id"""
    ctx = trace_manager.get_current_context()
    return ctx.run_id if ctx else None


def with_trace_context(func: Callable) -> Callable:
    """装饰器：确保函数在 TraceContext 中执行"""
    def wrapper(*args, **kwargs):
        ctx = trace_manager.get_current_context()
        if ctx is None:
            raise RuntimeError("No active trace context. Call start_turn() first.")
        return func(*args, **kwargs)
    return wrapper
