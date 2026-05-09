#!/usr/bin/env python3
"""实时监控 API — 活跃会话、Token 吞吐、技能热度"""

import time
from typing import Dict, Any, List, Optional
from fastapi import APIRouter

from ...core.monitor import AgentTraceMonitor
from ..metrics_store import get_metrics_store

router = APIRouter()

_monitor: Optional[AgentTraceMonitor] = None


def set_monitor(monitor: AgentTraceMonitor):
    global _monitor
    _monitor = monitor


@router.get("/live/metrics")
async def get_live_metrics() -> Dict[str, Any]:
    """获取实时监控指标"""
    store = get_metrics_store()

    # 1. 活跃会话（从 monitor 获取当前内存中的状态）
    active_sessions: List[Dict[str, Any]] = []
    if _monitor is not None:
        now = time.time()
        for sid, state in _monitor.session_states.items():
            active_sessions.append({
                "session_id": sid,
                "turn_index": state.turn_index,
                "model_name": state.model_name,
                "agent_type": state.agent_type,
                "user_input": state.last_user_message[:60] + "..." if len(state.last_user_message) > 60 else state.last_user_message,
                "total_tokens": state.total_tokens,
                "elapsed_seconds": int(now - state._turn_start_time) if state._turn_start_time > 0 else 0,
                "has_root_span": state.root_span is not None,
                "pending_tools": len(state.active_tools),
            })
        active_sessions.sort(key=lambda x: x["elapsed_seconds"], reverse=True)

    # 2. Token 吞吐（最近 5 分钟，每分钟一个点）
    token_throughput = store.get_token_throughput(minutes=5)

    # 3. 技能热度 Top 5（基于 tool_calls 表）
    skill_heatmap = store.get_skill_heatmap(limit=5)

    # 4. 今日统计快照
    daily = store.get_daily_stats()

    return {
        "active_sessions": active_sessions,
        "active_count": len(active_sessions),
        "token_throughput": token_throughput,
        "skill_heatmap": skill_heatmap,
        "daily": daily,
        "timestamp": time.time(),
    }
