#!/usr/bin/env python3
"""
Wire 协议解析器

解析 Kimi CLI 的 Wire 协议事件
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class WireEventType(Enum):
    """Wire 协议事件类型"""
    TURN_BEGIN = "TurnBegin"
    TURN_END = "TurnEnd"
    STEP_BEGIN = "StepBegin"
    STEP_INTERRUPTED = "StepInterrupted"  # 步骤中断事件
    CONTENT_PART = "ContentPart"
    TOOL_CALL = "ToolCall"
    TOOL_RESULT = "ToolResult"
    TOOL_CALL_PART = "ToolCallPart"
    STATUS_UPDATE = "StatusUpdate"
    APPROVAL_REQUEST = "ApprovalRequest"
    APPROVAL_RESPONSE = "ApprovalResponse"


@dataclass
class WireEvent:
    """Wire 事件"""
    timestamp: float
    event_type: WireEventType
    payload: Dict[str, Any]
    raw: Dict[str, Any]
    
    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> Optional["WireEvent"]:
        """从原始记录解析事件"""
        import logging
        logger = logging.getLogger("agent_trace")
        
        # 检查 metadata 类型
        record_type = record.get('type')
        if record_type == 'metadata':
            return None
        
        message = record.get('message', {})
        msg_type = message.get('type')
        
        if not msg_type:
            logger.debug(f"[WIRE] 跳过无类型消息: {record.keys()}")
            return None
        
        try:
            event_type = WireEventType(msg_type)
        except ValueError:
            # 未知事件类型，记录日志以便调试
            logger.debug(f"[WIRE] 未知事件类型: {msg_type}")
            return None
        
        logger.debug(f"[WIRE] 解析事件: {msg_type}")
        
        return cls(
            timestamp=record.get('timestamp', 0),
            event_type=event_type,
            payload=message.get('payload', {}),
            raw=record
        )


class WireParser:
    """Wire 协议解析器"""
    
    @staticmethod
    def parse_user_input(payload: Dict[str, Any]) -> str:
        """
        解析用户输入
        
        支持两种格式：
        1. 简单字符串: {"user_input": "文本"}
        2. 数组格式: {"user_input": [{"type": "text", "text": "内容"}]}
        """
        user_input = payload.get('user_input', '')
        
        if isinstance(user_input, list):
            # 数组格式，提取所有文本
            texts = []
            for part in user_input:
                if isinstance(part, dict):
                    if part.get('type') == 'text':
                        texts.append(part.get('text', ''))
                    elif 'text' in part:
                        texts.append(part.get('text', ''))
            return ' '.join(texts)
        
        return str(user_input) if user_input else ""
    
    @staticmethod
    def parse_token_usage(payload: Dict[str, Any]) -> Dict[str, Any]:
        """解析 Token 使用量"""
        token_usage = payload.get('token_usage', {})
        context_usage = payload.get('context_usage', 0)
        
        return {
            'input_other': token_usage.get('input_other', 0),
            'input_cache_read': token_usage.get('input_cache_read', 0),
            'input_cache_creation': token_usage.get('input_cache_creation', 0),
            'output': token_usage.get('output', 0),
            'context_usage': context_usage,
            'message_id': payload.get('message_id', ''),
        }
    
    @staticmethod
    def parse_tool_call(payload: Dict[str, Any]) -> Dict[str, Any]:
        """解析工具调用
        
        支持两种格式:
        1. 直接格式: {"type": "function", "id": "...", "function": {...}}
        2. 嵌套格式: {"tool_call": {"type": "function", "id": "...", "function": {...}}}
        """
        # 检查是否是嵌套格式
        if 'tool_call' in payload:
            tool_call = payload.get('tool_call', {})
        else:
            # 直接格式
            tool_call = payload
        
        function = tool_call.get('function', {})
        
        return {
            'id': tool_call.get('id', ''),
            'name': function.get('name', 'unknown'),
            'arguments': function.get('arguments', {}),
            'type': tool_call.get('type', 'function'),
        }
    
    @staticmethod
    def parse_tool_result(payload: Dict[str, Any]) -> Dict[str, Any]:
        """解析工具结果
        
        支持多种可能的返回格式：
        - 直接格式: {"tool_call_id": "...", "return_value": {...}}
        - 嵌套格式: {"tool_result": {"tool_call_id": "...", "return_value": {...}}}
        - return_value.output / content / result / data
        - return_value.is_error / error / success
        - return_value.message / error_message
        """
        # 检查是否是嵌套格式
        if 'tool_result' in payload:
            tool_result = payload.get('tool_result', {})
        else:
            # 直接格式
            tool_result = payload
        
        return_value = tool_result.get('return_value', {})
        
        # 尝试多种可能的字段名获取内容
        content = (
            return_value.get('output', '') or
            return_value.get('content', '') or
            return_value.get('result', '') or
            return_value.get('data', '') or
            (str(return_value) if return_value else '')
        )
        
        # 尝试多种可能的字段名获取错误状态
        is_error = (
            return_value.get('is_error', False) or
            return_value.get('error', False) or
            not return_value.get('success', True)
        )
        
        # 尝试多种可能的字段名获取消息
        message = (
            return_value.get('message', '') or
            return_value.get('error_message', '') or
            return_value.get('error_msg', '')
        )
        
        return {
            'tool_call_id': tool_result.get('tool_call_id', ''),
            'content': content,
            'is_error': is_error,
            'message': message,
        }
    
    @staticmethod
    def parse_content_part(payload: Dict[str, Any]) -> Dict[str, Any]:
        """解析内容片段"""
        content_type = payload.get('type', '')
        
        if content_type == 'think':
            return {
                'type': 'think',
                'content': payload.get('think', ''),
            }
        elif content_type == 'text':
            return {
                'type': 'text',
                'content': payload.get('text', ''),
            }
        
        return {'type': content_type, 'content': ''}
    
    @staticmethod
    def parse_approval_request(payload: Dict[str, Any]) -> Dict[str, Any]:
        """解析批准请求"""
        return {
            'request_id': payload.get('request_id', ''),
            'tool_name': payload.get('tool_name', ''),
            'tool_input': payload.get('tool_input', {}),
            'description': payload.get('description', ''),
            'timeout_seconds': payload.get('timeout_seconds', 300),
        }
    
    @staticmethod
    def parse_approval_response(payload: Dict[str, Any]) -> Dict[str, Any]:
        """解析批准响应"""
        return {
            'request_id': payload.get('request_id', ''),
            'approved': payload.get('approved', False),
            'reason': payload.get('reason', ''),
        }
