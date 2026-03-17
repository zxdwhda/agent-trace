#!/usr/bin/env python3
"""
事件处理器基类
"""

from abc import ABC, abstractmethod
from typing import Dict, Any

from ..core.session_state import SessionState
from ..parsers.wire_parser import WireEvent


class EventHandler(ABC):
    """事件处理器接口"""
    
    @abstractmethod
    def handle(self, state: SessionState, event: WireEvent) -> bool:
        """
        处理事件
        
        Args:
            state: Session 状态
            event: Wire 事件
            
        Returns:
            是否成功处理
        """
        pass


class TurnBeginHandler(EventHandler):
    """Turn 开始处理器"""
    
    def handle(self, state: SessionState, event: WireEvent) -> bool:
        from ..parsers.wire_parser import WireParser
        
        user_input = WireParser.parse_user_input(event.payload)
        state.start_turn(event.timestamp, user_input)
        return True


class TurnEndHandler(EventHandler):
    """Turn 结束处理器"""
    
    def handle(self, state: SessionState, event: WireEvent) -> bool:
        state.end_turn(event.timestamp)
        return True


class StepBeginHandler(EventHandler):
    """Step 开始处理器"""
    
    def handle(self, state: SessionState, event: WireEvent) -> bool:
        payload = event.payload
        step_n = payload.get('n', 0)
        model = payload.get('model', '')
        
        state.start_step(event.timestamp, step_n, model)
        return True


class ContentPartHandler(EventHandler):
    """内容片段处理器"""
    
    def handle(self, state: SessionState, event: WireEvent) -> bool:
        from ..parsers.wire_parser import WireParser
        
        content_info = WireParser.parse_content_part(event.payload)
        content_type = content_info.get('type', '')
        content = content_info.get('content', '')
        
        state.add_content(event.timestamp, content_type, content)
        return True


class ToolCallHandler(EventHandler):
    """工具调用处理器"""
    
    def handle(self, state: SessionState, event: WireEvent) -> bool:
        from ..parsers.wire_parser import WireParser
        
        tool_call = WireParser.parse_tool_call(event.payload)
        state.start_tool_call(event.timestamp, tool_call)
        return True


class ToolResultHandler(EventHandler):
    """工具结果处理器"""
    
    def handle(self, state: SessionState, event: WireEvent) -> bool:
        from ..parsers.wire_parser import WireParser
        
        tool_result = WireParser.parse_tool_result(event.payload)
        state.end_tool_call(event.timestamp, tool_result)
        return True


class StatusUpdateHandler(EventHandler):
    """状态更新处理器"""
    
    def handle(self, state: SessionState, event: WireEvent) -> bool:
        from ..parsers.wire_parser import WireParser
        
        token_info = WireParser.parse_token_usage(event.payload)
        state.update_token_usage(token_info)
        return True


class ApprovalRequestHandler(EventHandler):
    """用户批准请求处理器"""
    
    def handle(self, state: SessionState, event: WireEvent) -> bool:
        from ..parsers.wire_parser import WireParser
        
        approval_info = WireParser.parse_approval_request(event.payload)
        state.add_approval_request(event.timestamp, approval_info)
        return True


class ApprovalResponseHandler(EventHandler):
    """用户批准响应处理器"""
    
    def handle(self, state: SessionState, event: WireEvent) -> bool:
        from ..parsers.wire_parser import WireParser
        
        response_info = WireParser.parse_approval_response(event.payload)
        state.add_approval_response(event.timestamp, response_info)
        return True
