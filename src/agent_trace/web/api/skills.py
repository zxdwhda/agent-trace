#!/usr/bin/env python3
"""技能分析 API（v0.6.5）— 按 ToolCall function name 聚合"""

import logging
from typing import Dict, Any, List, Optional

from fastapi import APIRouter

from ..metrics_store import get_metrics_store

router = APIRouter()
logger = logging.getLogger("agent_trace.web")


@router.get("/skills/analysis")
async def skills_analysis() -> List[Dict[str, Any]]:
    """GET /api/skills/analysis — 按 skill_name（ToolCall function name）聚合分析"""
    try:
        store = get_metrics_store()
        return store.get_skill_analysis()
    except Exception as e:
        logger.error(f"Error in skills analysis: {e}")
        return []
