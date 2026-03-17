#!/usr/bin/env python3
"""
Session 状态管理（v0.3.2 增强版）

新增功能：
1. 事件唯一 ID 生成（借鉴 LangSmith run_id）
2. 去重检查集成
3. Span 创建幂等性保证
4. 增强日志输出（用于调试重复问题）
"""

import hashlib
import time
import logging
from typing import Optional, Dict, Any, List

import cozeloop
from cozeloop.spec import tracespec

from ..utils.retry import retry_sdk_call
from .dedup import EventDeduplicator, EventID

logger = logging.getLogger("agent_trace")


class SessionState:
    """管理单个 Session 的 Trace 状态"""
    
    # Span 类型常量
    SPAN_TYPE_AGENT = "agent"
    SPAN_TYPE_MODEL = tracespec.V_MODEL_SPAN_TYPE  # "model"
    SPAN_TYPE_TOOL = tracespec.V_TOOL_SPAN_TYPE    # "tool"
    
    def __init__(
        self,
        session_id: str,
        deduplicator: Optional[EventDeduplicator] = None,
        turn_index: int = 0
    ):
        """
        初始化 Session 状态
        
        Args:
            session_id: 会话 ID
            deduplicator: 去重管理器
            turn_index: 当前 Turn 索引
        """
        self.session_id = session_id
        self.deduplicator = deduplicator
        self.turn_index = turn_index
        
        # Span 引用 - 层级结构: root -> step -> tool
        self.root_span: Optional[Any] = None
        self.current_step: Optional[Any] = None
        self.active_tools: Dict[str, Any] = {}
        
        # Token 累计
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.context_usage = 0.0
        
        # 模型信息
        self.model_name = "unknown"
        self.model_provider = "moonshot"
        
        # 内容累积
        self.last_user_message = ""
        self._accumulated_output = ""
        self._think_content = ""
        
        # 等待批准的工具
        self._pending_approvals: Dict[str, Any] = {}
        
        # 已处理的 Span 记录（用于当前会话内去重）
        self._processed_spans: set = set()
        
        # 调试计数器
        self._event_counter = {
            "turn_begin": 0,
            "step_begin": 0,
            "tool_call": 0,
            "duplicate_blocked": 0
        }
    
    def _generate_event_id(self, event_type: str, step_n: int = 0, timestamp: float = 0) -> str:
        """
        生成事件唯一 ID
        
        使用 session_id + turn_index + step_n + event_type + timestamp 生成确定性 ID
        借鉴：LangSmith run_id 幂等性设计
        添加 timestamp 确保同一 turn 内重复事件也能被区分
        """
        # 使用 timestamp 来确保唯一性
        ts_int = int(timestamp * 1000) if timestamp else int(time.time() * 1000)
        event_id = EventID(
            session_id=self.session_id,
            turn_index=self.turn_index,
            step_n=step_n,
            event_type=event_type,
            timestamp=ts_int  # 传入时间戳确保唯一性
        )
        return event_id.to_string()
    
    def _check_duplicate(self, event_id: str, event_type: str = "") -> bool:
        """
        检查事件是否重复
        
        增强日志输出，便于调试
        """
        # L0: 当前会话缓存检查
        if event_id in self._processed_spans:
            logger.info(f"[DEDUP][L0] Blocked by session cache: {event_type} {event_id[:16]}...")
            return True
        
        # L1/L2: 全局去重管理器检查
        if self.deduplicator:
            is_dup = self.deduplicator.is_duplicate(event_id)
            if is_dup:
                logger.info(f"[DEDUP][L1/L2] Blocked by deduplicator: {event_type} {event_id[:16]}...")
            return is_dup
        
        return False
    
    def _mark_processed(
        self,
        event_id: str,
        event_type: str,
        step_n: int = 0,
        span_id: Optional[str] = None
    ):
        """标记事件为已处理"""
        # 加入当前会话缓存
        self._processed_spans.add(event_id)
        
        # 加入全局去重管理器
        if self.deduplicator:
            self.deduplicator.mark_processed(
                event_id=event_id,
                session_id=self.session_id,
                turn_index=self.turn_index,
                step_n=step_n,
                event_type=event_type,
                span_id=span_id
            )
    
    @retry_sdk_call(max_retries=2, initial_delay=0.5)
    def start_turn(self, timestamp: float, user_input: str) -> Optional[Any]:
        """
        开始一个新的 Turn (Root Span)
        
        Args:
            timestamp: 时间戳
            user_input: 用户输入
            
        Returns:
            Root span 实例（重复时返回 None）
        """
        # 如果已有 root_span，先结束它并开始新的一轮
        if self.root_span:
            logger.debug(f"[SESSION:{self.session_id[:8]}] 检测到已有 root_span，结束当前 turn 并递增 turn_index")
            try:
                self.end_turn(timestamp)
            except Exception as e:
                logger.warning(f"[SESSION:{self.session_id[:8]}] 结束前一个 turn 时出错: {e}")
            # 递增 turn_index 以生成唯一的事件 ID
            self.turn_index += 1
        
        # 生成事件 ID（使用 timestamp 确保唯一性）
        event_id = self._generate_event_id("turn_begin", int(timestamp))
        
        # 检查重复
        if self._check_duplicate(event_id, "turn_begin"):
            self._event_counter["duplicate_blocked"] += 1
            logger.debug(f"[SESSION:{self.session_id[:8]}] TurnBegin 被去重: {event_id[:16]}...")
            return None
        
        self._event_counter["turn_begin"] += 1
        self.last_user_message = user_input
        
        try:
            # 创建 Root Span (agent 类型)
            self.root_span = cozeloop.start_span(
                "agent_turn",
                self.SPAN_TYPE_AGENT
            )
            self.root_span.set_input(user_input)
            self.root_span.set_tags({
                "session_id": self.session_id,
                "agent_type": "kimi_cli",
                "agent_version": "1.17.0",
                "turn_index": str(self.turn_index),
                "event_id": event_id[:16],
            })
            
            # 重置累计值
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            self._accumulated_output = ""
            self._think_content = ""
            
            # 标记为已处理
            self._mark_processed(event_id, "turn_begin", 0)
            
            logger.info(f"[SESSION:{self.session_id[:8]}] ✓ TurnBegin started (event_id={event_id[:16]}..., turn={self.turn_index})")
            return self.root_span
            
        except Exception as e:
            logger.error(f"[SESSION:{self.session_id[:8]}] Failed to start turn: {e}", exc_info=True)
            return None
    
    @retry_sdk_call(max_retries=2, initial_delay=0.5)
    def start_step(self, timestamp: float, step_n: int, model: str = "") -> Optional[Any]:
        """
        开始一个 Step (Model Span)
        
        Args:
            timestamp: 时间戳
            step_n: 步骤编号
            model: 模型名称
            
        Returns:
            Model span 实例（重复时返回 None）
        """
        # 生成事件 ID（使用 timestamp 确保唯一性）
        event_id = self._generate_event_id("step_begin", step_n, timestamp)
        
        # 检查重复
        if self._check_duplicate(event_id, "step_begin"):
            self._event_counter["duplicate_blocked"] += 1
            logger.debug(f"[SESSION:{self.session_id[:8]}] Step {step_n} blocked by dedup: {event_id[:16]}...")
            return None
        
        self._event_counter["step_begin"] += 1
        
        if not self.root_span:
            logger.warning(f"[SESSION:{self.session_id[:8]}] No root span, cannot start step {step_n} (可能 TurnBegin 未处理或已结束)")
            return None
        
        # 结束之前的 step
        if self.current_step:
            self._finish_current_step()
        
        # 重置内容累积和 token 累计（每个 step 独立计算）
        self._accumulated_output = ""
        self._think_content = ""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        
        try:
            # 创建 Model Span，指定 child_of 建立层级关系
            self.current_step = cozeloop.start_span(
                f"step_{step_n}",
                self.SPAN_TYPE_MODEL,
                child_of=self.root_span,
            )
            
            # 设置输入（使用字符串，与官方示例一致）
            self.current_step.set_input(self.last_user_message)
            
            # 设置模型信息
            if model:
                self.model_name = model
            self.current_step.set_model_provider(self.model_provider)
            self.current_step.set_model_name(self.model_name)
            
            # 添加去重标签
            self.current_step.set_tags({
                "event_id": event_id[:16],
                "step_n": str(step_n),
            })
            
            # 标记为已处理
            self._mark_processed(event_id, "step_begin", step_n)
            
            logger.info(f"[SESSION:{self.session_id[:8]}] Step {step_n} started (event_id={event_id[:16]}...)")
            return self.current_step
            
        except Exception as e:
            logger.error(f"[SESSION:{self.session_id[:8]}] Failed to start step {step_n}: {e}")
            raise
    
    @retry_sdk_call(max_retries=2, initial_delay=0.5)
    def start_tool_call(self, timestamp: float, tool_call: Dict[str, Any]) -> Optional[Any]:
        """
        开始工具调用
        
        Args:
            timestamp: 时间戳
            tool_call: 工具调用信息
            
        Returns:
            Tool span 实例（重复时返回 None）
        """
        tool_name = tool_call.get('name', 'unknown')
        tool_call_id = tool_call.get('id') or str(timestamp)
        
        # 生成事件 ID（使用 tool_call_id 的确定性哈希 + timestamp 确保唯一性）
        step_n = int(hashlib.sha256(str(tool_call_id).encode()).hexdigest()[:8], 16) % 1000000
        event_id = self._generate_event_id(f"tool_call:{tool_name}", step_n, timestamp)
        
        # 检查重复
        if self._check_duplicate(event_id, f"tool_call:{tool_name}"):
            self._event_counter["duplicate_blocked"] += 1
            logger.info(f"[SESSION:{self.session_id[:8]}] Tool {tool_name} blocked by dedup")
            return None
        
        self._event_counter["tool_call"] += 1
        
        if not self.current_step:
            logger.warning(f"[SESSION:{self.session_id[:8]}] No current step, cannot start tool call {tool_name}")
            return None
        
        arguments = tool_call.get('arguments', {})
        
        try:
            # 创建 Tool Span，指定 child_of 建立层级关系
            tool_span = cozeloop.start_span(
                f"tool:{tool_name}",
                self.SPAN_TYPE_TOOL,
                child_of=self.current_step,
            )
            
            tool_span.set_input({
                "tool_name": tool_name,
                "arguments": arguments
            })
            
            # 添加去重标签
            tool_span.set_tags({
                "event_id": event_id[:16],
                "tool_call_id": str(tool_call_id)[:16],
            })
            
            self.active_tools[tool_call_id] = tool_span
            
            # 标记为已处理
            self._mark_processed(event_id, "tool_call", step_n, tool_call_id)
            
            logger.info(f"[SESSION:{self.session_id[:8]}] Tool {tool_name} started (event_id={event_id[:16]}...)")
            return tool_span
            
        except Exception as e:
            logger.error(f"[SESSION:{self.session_id[:8]}] Failed to start tool call {tool_name}: {e}")
            raise
    
    def end_tool_call(self, timestamp: float, tool_result: Dict[str, Any]):
        """
        结束工具调用
        
        Args:
            timestamp: 时间戳
            tool_result: 工具结果信息
        """
        tool_call_id = tool_result.get('tool_call_id')
        if not tool_call_id or tool_call_id not in self.active_tools:
            return
        
        tool_span = self.active_tools[tool_call_id]
        
        content = tool_result.get('content', '')
        tool_span.set_output({"result": content})
        
        if tool_result.get('is_error'):
            tool_span.set_error(Exception("Tool execution failed"))
        
        tool_span.finish()
        del self.active_tools[tool_call_id]
    
    def add_content(self, timestamp: float, content_type: str, content: str):
        """
        添加内容
        
        Args:
            timestamp: 时间戳
            content_type: 内容类型 (think/text)
            content: 内容文本
        """
        if not self.current_step:
            return
        
        if content_type == 'think':
            self._think_content += content
            # 思考内容作为 tag 记录
            self.current_step.set_tags({
                "think_content": self._think_content[:2000]  # 限制长度
            })
        elif content_type == 'text':
            self._accumulated_output += content
    
    def update_token_usage(self, token_info: Dict[str, Any]):
        """
        更新 Token 使用量
        
        Args:
            token_info: Token 使用信息
        """
        if not self.current_step:
            return
        
        # 计算输入 tokens
        input_tokens = (
            token_info.get('input_other', 0) +
            token_info.get('input_cache_read', 0)
        )
        output_tokens = token_info.get('output', 0)
        context_usage = token_info.get('context_usage', 0)
        
        # 累计
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.context_usage = context_usage
        
        # 设置到当前 step
        self.current_step.set_input_tokens(input_tokens)
        self.current_step.set_output_tokens(output_tokens)
        
        # 额外信息作为 tags
        self.current_step.set_tags({
            "input_cache_read": token_info.get('input_cache_read', 0),
            "input_cache_creation": token_info.get('input_cache_creation', 0),
            "context_usage": f"{context_usage:.2%}",
            "message_id": token_info.get('message_id', ''),
        })
    
    def _finish_current_step(self):
        """结束当前 step"""
        if not self.current_step:
            return
        
        # 设置输出（使用字符串，与官方示例一致）
        if self._accumulated_output:
            self.current_step.set_output(self._accumulated_output[:32000])  # 限制长度
        
        self.current_step.finish()
        self.current_step = None
    
    def add_approval_request(self, timestamp: float, approval_info: Dict[str, Any]):
        """
        添加批准请求
        
        Args:
            timestamp: 时间戳
            approval_info: 批准请求信息
        """
        request_id = approval_info.get('request_id', '')
        if not request_id:
            return
        
        self._pending_approvals[request_id] = {
            'info': approval_info,
            'timestamp': timestamp,
            'status': 'pending'
        }
        
        # 在 root_span 上记录批准请求
        if self.root_span:
            self.root_span.set_tags({
                f"approval_request_{request_id}": approval_info.get('tool_name', 'unknown'),
                f"approval_desc_{request_id}": approval_info.get('description', '')[:100],
            })
    
    def add_approval_response(self, timestamp: float, response_info: Dict[str, Any]):
        """
        添加批准响应
        
        Args:
            timestamp: 时间戳
            response_info: 批准响应信息
        """
        request_id = response_info.get('request_id', '')
        if not request_id:
            return
        
        approved = response_info.get('approved', False)
        
        # 更新待处理批准状态
        if request_id in self._pending_approvals:
            self._pending_approvals[request_id]['status'] = 'approved' if approved else 'rejected'
            self._pending_approvals[request_id]['response_time'] = timestamp
        
        # 在 root_span 上记录批准响应
        if self.root_span:
            self.root_span.set_tags({
                f"approval_response_{request_id}": 'approved' if approved else 'rejected',
                f"approval_reason_{request_id}": response_info.get('reason', '')[:100],
            })
    
    def end_turn(self, timestamp: float):
        """
        结束 Turn
        
        Args:
            timestamp: 时间戳
        """
        # 输出调试统计
        logger.info(f"[SESSION:{self.session_id[:8]}] Turn ending. Stats: {self._event_counter}")
        
        # 结束当前 step
        self._finish_current_step()
        
        # 结束所有未完成的 tool
        for tool_id, tool_span in list(self.active_tools.items()):
            tool_span.set_error(Exception("Tool not completed before turn end"))
            tool_span.finish()
        self.active_tools.clear()
        
        # 结束 root span
        if self.root_span:
            self.root_span.set_output({
                "total_tokens": self.total_input_tokens + self.total_output_tokens,
                "context_usage": f"{self.context_usage:.2%}",
            })
            self.root_span.finish()
            self.root_span = None
        
        # 清理当前会话缓存
        self._processed_spans.clear()
        logger.info(f"[SESSION:{self.session_id[:8]}] Turn ended and session cache cleared")
