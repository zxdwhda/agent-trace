#!/usr/bin/env python3
"""
Session 状态管理（v0.3.5 - Root Span 修复版）

优化内容：
1. 补充 Span 类型常量（entry/message/prompt/rag/session/gateway）
2. 增强 Token 追踪（gen_ai.* 标准属性）
3. 添加 Runtime 信息设置（动态 Agent 类型检测）
4. 引入 TraceContext 管理机制
5. 事件唯一 ID 生成（借鉴 LangSmith run_id）
6. 去重检查集成
7. Span 创建幂等性保证
"""

import hashlib
import os
import time
import logging
import threading
from typing import Optional, Dict, Any, List

import cozeloop
from cozeloop.spec import tracespec
from cozeloop.spec.tracespec import Runtime

from ..utils.retry import retry_sdk_call
from .dedup import EventDeduplicator, EventID
from .trace_context import TraceContext, TraceContextManager, trace_manager

logger = logging.getLogger("agent_trace")


class SessionState:
    """管理单个 Session 的 Trace 状态（v0.3.5 - Root Span 修复版）""
    
    # ========== Span 类型常量（完整版）==========
    # 原有类型
    SPAN_TYPE_AGENT = "agent"
    SPAN_TYPE_MODEL = tracespec.V_MODEL_SPAN_TYPE  # "model"
    SPAN_TYPE_TOOL = tracespec.V_TOOL_SPAN_TYPE    # "tool"
    
    # 新增类型（P0）
    SPAN_TYPE_ENTRY = "entry"           # 请求入口
    SPAN_TYPE_MESSAGE = "message"       # 消息记录
    SPAN_TYPE_PROMPT = "prompt"         # 提示词
    SPAN_TYPE_RAG = "rag"               # 检索增强生成
    SPAN_TYPE_SESSION = "session"       # 会话生命周期
    SPAN_TYPE_GATEWAY = "gateway"       # 网关层面
    
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
        
        # P0: TraceContext 集成
        self.trace_context: Optional[TraceContext] = None
        self._context_manager = trace_manager
        
        # Span 引用 - 层级结构: entry -> root -> step -> tool
        self.entry_span: Optional[Any] = None      # 新增：entry span
        self.root_span: Optional[Any] = None
        self.current_step: Optional[Any] = None
        self.active_tools: Dict[str, Any] = {}
        
        # Token 累计
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_read_tokens = 0
        self.total_cache_write_tokens = 0
        self.total_tokens = 0
        self.context_usage = 0.0
        
        # 模型信息
        self.model_name = "unknown"
        self.model_provider = "moonshot"
        
        # P0: 动态 Agent 类型检测
        self.agent_type = self._detect_agent_type()
        self.agent_version = "0.3.5"
        
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
    
    # ========== P0: Agent 类型检测 ==========
    
    def _detect_agent_type(self) -> str:
        """
        检测 Agent 类型（Kimi CLI vs Claude Code）
        
        检测优先级：
        1. 环境变量 AGENT_TYPE（最高优先级）
        2. 父进程名称
        3. 默认值 kimi_cli
        """
        # 1. 环境变量（最高优先级）
        env_agent = os.getenv('AGENT_TYPE')
        if env_agent:
            return env_agent.lower()
        
        # 2. 进程名称检测
        try:
            import psutil
            parent = psutil.Process().parent()
            if parent:
                name = parent.name().lower()
                if 'claude' in name or 'claude-code' in name:
                    return "claude_code"
                if 'kimi' in name or 'kimi-cli' in name:
                    return "kimi_cli"
        except Exception:
            pass
        
        # 3. 默认值
        return "kimi_cli"
    
    def _create_runtime(self) -> Runtime:
        """创建 Runtime 对象"""
        runtime = Runtime()
        runtime.language = "python"
        runtime.library = "agent-trace"
        runtime.scene = os.getenv('COZELOOP_SCENE', 'CLI')
        runtime.loop_sdk_version = self.agent_version
        return runtime
    
    # ========== 事件 ID 生成与去重 ==========
    
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
    
    # ========== Turn/Span 生命周期管理 ==========
    
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
            # P0: 创建 TraceContext
            run_id = f"{self.session_id}_{self.turn_index}_{int(timestamp * 1000)}"
            self.trace_context = self._context_manager.start_turn(
                run_id=run_id,
                channel_id=self.session_id,
                turn_id=run_id,
            )
            self.trace_context.turn_state.user_input = user_input
            
            # P0: 创建 Entry Span 作为真正的根节点
            # 关键：使用 start_new_trace=True 确保这是一个 Root Span（parent_span_id="0"）
            # 注意：必须使用 client 实例调用，全局 cozeloop.start_span() 不支持 start_new_trace 参数
            from cozeloop._client import get_default_client
            client = get_default_client()
            self.entry_span = client.start_span(
                "session_entry",
                self.SPAN_TYPE_ENTRY,
                start_new_trace=True,
            )
            self.entry_span.set_tags({
                "session_id": self.session_id,
                "entry_type": "user_request",
                "trace_id": self.trace_context.trace_id,
            })
            self.entry_span.set_input(user_input)
            
            # P0: Agent Span 作为 Entry 的子节点
            self.root_span = client.start_span(
                "agent_turn",
                self.SPAN_TYPE_AGENT,
                child_of=self.entry_span,
            )
            
            # P0: 设置 Runtime 信息
            runtime = self._create_runtime()
            self.root_span.set_runtime(runtime)
            
            # P0: 设置标签（使用动态检测的 agent_type）
            self.root_span.set_tags({
                "session_id": self.session_id,
                "agent_type": self.agent_type,  # 动态检测，非硬编码
                "agent_version": self.agent_version,
                "turn_index": str(self.turn_index),
                "event_id": event_id[:16],
                "trace_id": self.trace_context.trace_id,
                "run_id": self.trace_context.run_id,
            })
            
            self.root_span.set_input(user_input)
            
            # 重置累计值
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            self.total_cache_read_tokens = 0
            self.total_cache_write_tokens = 0
            self.total_tokens = 0
            self._accumulated_output = ""
            self._think_content = ""
            
            # 标记为已处理
            self._mark_processed(event_id, "turn_begin", 0)
            
            logger.info(f"[SESSION:{self.session_id[:8]}] ✓ TurnBegin started (trace_id={self.trace_context.trace_id[:8]}..., turn={self.turn_index})")
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
        
        try:
            # 获取 client 实例
            from cozeloop._client import get_default_client
            client = get_default_client()
            
            # P0: 创建 Prompt Span（在 Model Span 之前记录提示词）
            prompt_span = client.start_span(
                f"prompt_{step_n}",
                self.SPAN_TYPE_PROMPT,
                child_of=self.root_span,
            )
            prompt_span.set_input({
                "user_input": self.last_user_message,
                "step_n": step_n,
            })
            prompt_span.set_tags({
                "prompt.type": "user_request",
                "prompt.step_n": str(step_n),
            })
            prompt_span.finish()
            
            # 创建 Model Span，指定 child_of 建立层级关系
            self.current_step = client.start_span(
                f"step_{step_n}",
                self.SPAN_TYPE_MODEL,
                child_of=self.root_span,
            )
            
            # 设置输入（使用字符串，与官方示例一致）
            self.current_step.set_input(self.last_user_message)
            
            # 设置模型信息
            if model:
                self.model_name = model
                if self.trace_context:
                    self.trace_context.turn_state.model_name = model
            
            self.current_step.set_model_provider(self.model_provider)
            self.current_step.set_model_name(self.model_name)
            
            # 添加去重标签和 trace 信息
            self.current_step.set_tags({
                "event_id": event_id[:16],
                "step_n": str(step_n),
                "trace_id": self.trace_context.trace_id if self.trace_context else "",
                "run_id": self.trace_context.run_id if self.trace_context else "",
            })
            
            # 标记为已处理
            self._mark_processed(event_id, "step_begin", step_n)
            
            logger.info(f"[SESSION:{self.session_id[:8]}] Step {step_n} started (model={self.model_name})")
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
            from cozeloop._client import get_default_client
            client = get_default_client()
            tool_span = client.start_span(
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
            
            logger.info(f"[SESSION:{self.session_id[:8]}] Tool {tool_name} started")
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
        if not tool_call_id:
            logger.warning(f"[SESSION:{self.session_id[:8]}] Tool result missing tool_call_id")
            return
        
        if tool_call_id not in self.active_tools:
            logger.warning(f"[SESSION:{self.session_id[:8]}] Tool {tool_call_id[:16]}... not found in active_tools (keys: {list(self.active_tools.keys())})")
            return
        
        tool_span = self.active_tools[tool_call_id]
        
        content = tool_result.get('content', '')
        tool_span.set_output({"result": content})
        
        if tool_result.get('is_error'):
            tool_span.set_error(Exception("Tool execution failed"))
        
        tool_span.finish()
        del self.active_tools[tool_call_id]
        
        logger.info(f"[SESSION:{self.session_id[:8]}] Tool finished")
    
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
            if self.trace_context:
                self.trace_context.turn_state.assistant_output += content
    
    # ========== P0: 增强 Token 追踪 ==========
    
    def update_token_usage(self, token_info: Dict[str, Any]):
        """
        更新 Token 使用量（增强版）
        
        支持 OpenTelemetry gen_ai.* 标准属性
        """
        if not self.current_step:
            return
        
        # 提取原始数据
        input_other = token_info.get('input_other', 0)
        input_cache_read = token_info.get('input_cache_read', 0)
        input_cache_creation = token_info.get('input_cache_creation', 0)
        output_tokens = token_info.get('output', 0)
        context_usage = token_info.get('context_usage', 0)
        
        # 计算标准指标
        input_tokens = input_other + input_cache_read
        total_tokens = input_tokens + output_tokens + input_cache_creation
        
        # 更新累计值
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cache_read_tokens += input_cache_read
        self.total_cache_write_tokens += input_cache_creation
        self.total_tokens += total_tokens
        self.context_usage = context_usage
        
        # 更新 TraceContext 中的 TurnState
        if self.trace_context:
            self.trace_context.turn_state.add_tokens(
                input_tokens, output_tokens, input_cache_read, input_cache_creation
            )
        
        # 设置到 SDK 标准字段
        self.current_step.set_input_tokens(input_tokens)
        self.current_step.set_output_tokens(output_tokens)
        
        # === P0: 设置标准 gen_ai.* 属性 ===
        self.current_step.set_tags({
            # 标准 OpenTelemetry 属性
            "gen_ai.usage.input_tokens": input_tokens,
            "gen_ai.usage.output_tokens": output_tokens,
            "gen_ai.usage.cache_read_tokens": input_cache_read,
            "gen_ai.usage.cache_write_tokens": input_cache_creation,
            "gen_ai.usage.total_tokens": total_tokens,
            
            # 模型信息（确保一致性）
            "gen_ai.provider.name": self.model_provider,
            "gen_ai.request.model": self.model_name,
            
            # 保留原有信息作为补充
            "input_other": input_other,
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
        结束 Turn（模仿 OpenClaw 延迟结束机制）
        
        OpenClaw 实现参考：
        1. 先结束 Agent Span（root_span）
        2. 延迟 100ms 后结束 Entry Span（真正的 Root）
        3. 延迟期间确保所有子 Span 先上报
        4. 强制 flush 队列确保数据立即发送
        
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
        
        # 保存需要在延迟中使用的数据
        root_span_ref = self.root_span
        entry_span_ref = self.entry_span
        trace_context_ref = self.trace_context
        session_id = self.session_id
        event_counter = self._event_counter.copy()
        
        # 立即结束 Agent Span（child span）
        if root_span_ref:
            # 包含 gen_ai.* 标准属性的最终统计
            root_span_ref.set_output({
                "total_tokens": self.total_tokens,
                "input_tokens": self.total_input_tokens,
                "output_tokens": self.total_output_tokens,
                "cache_read_tokens": self.total_cache_read_tokens,
                "cache_write_tokens": self.total_cache_write_tokens,
                "context_usage": f"{self.context_usage:.2%}",
                "gen_ai.usage.total_tokens": self.total_tokens,
            })
            root_span_ref.finish()
            logger.info(f"[SESSION:{session_id[:8]}] Agent span finished (will delay entry span)")
        
        # 清除引用（避免重复结束）
        self.root_span = None
        self.active_tools.clear()
        
        # 延迟 100ms 后结束 Entry Span（Root Span）并 flush
        # 模仿 OpenClaw: index.js:553-573
        def delayed_finish_root():
            try:
                # 结束 Entry Span（真正的 Root）
                if entry_span_ref:
                    entry_span_ref.finish()
                    logger.info(f"[SESSION:{session_id[:8]}] Entry span (Root) finished (delayed)")
                
                # 强制刷新队列（关键！）
                try:
                    import cozeloop
                    cozeloop.flush()
                    logger.info(f"[SESSION:{session_id[:8]}] CozeLoop queue flushed")
                except Exception as e:
                    logger.warning(f"[SESSION:{session_id[:8]}] Failed to flush cozeloop: {e}")
                
                # 结束 TraceContext
                if trace_context_ref:
                    self._context_manager.end_turn(trace_context_ref.run_id)
                    logger.info(f"[SESSION:{session_id[:8]}] TraceContext ended (delayed)")
                
                logger.info(f"[SESSION:{session_id[:8]}] Turn ended and session cache cleared (delayed)")
                
            except Exception as e:
                logger.error(f"[SESSION:{session_id[:8]}] Error in delayed finish: {e}", exc_info=True)
        
        # 启动延迟定时器（500ms，确保所有子 Span 先上报完成）
        # 注意：OpenClaw 使用 100ms，但我们增加到 500ms 以确保可靠性
        timer = threading.Timer(0.5, delayed_finish_root)
        timer.daemon = True  # 设置为守护线程，避免阻塞程序退出
        timer.start()
        
        # 立即清理当前会话缓存（非关键数据）
        self._processed_spans.clear()
        self.entry_span = None
        self.trace_context = None
