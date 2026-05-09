#!/usr/bin/env python3
"""会话 API"""

from fastapi import APIRouter, Query
from typing import Dict, Any, List, Optional

from ...core.monitor import AgentTraceMonitor
from ..metrics_store import get_metrics_store

router = APIRouter()

_monitor: Optional[AgentTraceMonitor] = None


def set_monitor(monitor: AgentTraceMonitor):
    global _monitor
    _monitor = monitor


@router.get("/sessions")
async def list_sessions(
    archived: bool = Query(False, description="是否只返回归档会话"),
) -> List[Dict[str, Any]]:
    """列出会话（活跃 + 历史）"""
    # 活跃会话（归档模式下不显示活跃会话）
    active_ids = set()
    result = []
    if _monitor is not None and not archived:
        for session_id, state in _monitor.session_states.items():
            active_ids.add(session_id)
            result.append({
                "session_id": session_id,
                "agent_type": state.agent_type,
                "model_name": state.model_name,
                "title": state.session_id[:8],
                "turn_index": state.turn_index,
                "total_input_tokens": state.total_input_tokens,
                "total_output_tokens": state.total_output_tokens,
                "total_tokens": state.total_tokens,
                "status": "active" if state.root_span else "ended",
                "trace_id": state.trace_context.trace_id if state.trace_context else None,
                "source": "active",
                "archived": False,
            })

    # 历史会话
    try:
        historical = get_metrics_store().list_sessions(limit=500, archived=archived)
        for row in historical:
            if row["session_id"] in active_ids:
                continue
            status = row.get("status", "historical")
            result.append({
                "session_id": row["session_id"],
                "agent_type": row["agent_type"],
                "model_name": row["model_name"],
                "title": row.get("title", row["session_id"][:8]),
                "turn_index": row["total_turns"],
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": row["total_tokens"],
                "status": status,
                "trace_id": None,
                "source": "db",
                "archived": row.get("archived", False),
                "first_seen": row["first_seen"],
                "last_active": row["last_active"],
            })
    except Exception:
        pass

    return result


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> Dict[str, Any]:
    """删除会话（物理删除）"""
    store = get_metrics_store()
    deleted = store.delete_session(session_id)
    if deleted:
        store.log_activity(
            activity_type="session_deleted",
            description=f"删除会话 {session_id[:8]}...",
            metadata={"session_id": session_id},
        )
    return {"deleted": deleted, "session_id": session_id}


@router.patch("/sessions/{session_id}")
async def patch_session(session_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """更新会话（归档/取消归档）"""
    store = get_metrics_store()
    archived = body.get("archived")
    if archived is not None:
        ok = store.archive_session(session_id, archived=bool(archived))
        if ok:
            activity_type = "session_archived" if archived else "session_restored"
            description = f"{'归档' if archived else '恢复'}会话 {session_id[:8]}..."
            store.log_activity(
                activity_type=activity_type,
                description=description,
                metadata={"session_id": session_id, "archived": bool(archived)},
            )
        return {"updated": ok, "session_id": session_id, "archived": bool(archived)}
    return {"updated": False, "session_id": session_id}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> Dict[str, Any]:
    """获取会话详情"""
    if _monitor is not None:
        state = _monitor.session_states.get(session_id)
        if state is not None:
            return {
                "session_id": state.session_id,
                "agent_type": state.agent_type,
                "model_name": state.model_name,
                "turn_index": state.turn_index,
                "total_input_tokens": state.total_input_tokens,
                "total_output_tokens": state.total_output_tokens,
                "total_tokens": state.total_tokens,
                "trace_context": state.trace_context.to_dict() if state.trace_context else None,
                "source": "active",
            }
    # 从历史记录查找
    db_session = get_metrics_store().get_session(session_id)
    if db_session is not None:
        return {
            "session_id": db_session["session_id"],
            "agent_type": db_session["agent_type"],
            "model_name": db_session["model_name"],
            "turn_index": db_session["total_turns"],
            "total_input_tokens": sum(t["input_tokens"] for t in db_session["turns"]),
            "total_output_tokens": sum(t["output_tokens"] for t in db_session["turns"]),
            "total_tokens": db_session["total_tokens"],
            "trace_context": None,
            "source": "db",
            "turns": db_session["turns"],
        }
    return {}


@router.get("/stats/tokens")
async def get_token_stats() -> Dict[str, Any]:
    """获取 Token 统计"""
    store = get_metrics_store()
    trend = store.get_token_trend(hours=24)
    models = store.get_model_distribution()

    timestamps = []
    input_tokens = []
    output_tokens = []
    for row in trend:
        timestamps.append(row["hour_offset"])
        input_tokens.append(row["input_tokens"])
        output_tokens.append(row["output_tokens"])

    return {
        "timestamps": timestamps,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "models": models,
    }
