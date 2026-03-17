#!/usr/bin/env python3
"""
AgentTrace - AI IDE 会话监控与 Trace 上报工具

支持 Kimi Code CLI、Claude Code 等多款 AI IDE 的会话监控，
将 Trace 数据自动上报到 Coze 罗盘进行观测和分析。
"""

try:
    from ._version import __version__
except ImportError:
    __version__ = "0.3.2"

__author__ = "AgentTrace Contributors"
__license__ = "MIT"

from .core.monitor import AgentTraceMonitor
from .core.session_state import SessionState
from .utils.config import Config

__all__ = ["AgentTraceMonitor", "SessionState", "Config", "__version__"]
