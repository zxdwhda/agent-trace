#!/usr/bin/env python3
"""状态 API"""

import time
import glob
from typing import Dict, Any, Optional
from fastapi import APIRouter

from ...core.monitor import AgentTraceMonitor
from ...core.event_bus import event_bus
from ..metrics_store import get_metrics_store

router = APIRouter()

# 全局 monitor 引用（由 cli 注入）
_monitor: Optional[AgentTraceMonitor] = None
_server_start_time = time.time()


def set_monitor(monitor: AgentTraceMonitor):
    global _monitor
    _monitor = monitor


def _count_monitored_files() -> int:
    """扫描监控的 wire.jsonl 文件数"""
    return len(glob.glob("/Users/zionxaviardamienang/.kimi/sessions/*/*/wire.jsonl"))


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """获取监控状态"""
    daily = get_metrics_store().get_daily_stats()
    store = get_metrics_store()
    conn = store._connect()
    
    # 活跃会话数（最近24小时有活动的会话）
    active_cutoff = time.time() - 86400
    active_count = conn.execute(
        "SELECT COUNT(*) FROM session_summary WHERE last_active > ? AND archived = 0",
        (active_cutoff,)
    ).fetchone()[0]
    
    if _monitor is None:
        return {
            "active_sessions": active_count,
            "monitored_files": _count_monitored_files(),
            "total_turns_today": daily["total_turns_today"],
            "total_tokens_today": daily["total_tokens_today"],
            "uptime_seconds": time.time() - _server_start_time,
            "event_bus": event_bus.get_stats(),
        }
    stats = _monitor.get_stats()
    stats["total_turns_today"] = daily["total_turns_today"]
    stats["total_tokens_today"] = daily["total_tokens_today"]
    stats["uptime_seconds"] = _monitor._start_time and (time.time() - _monitor._start_time) or 0
    stats["event_bus"] = event_bus.get_stats()
    return stats
