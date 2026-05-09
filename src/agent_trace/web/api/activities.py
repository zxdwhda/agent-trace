#!/usr/bin/env python3
"""活动日志 API"""

from fastapi import APIRouter
from typing import Dict, Any, List

from ..metrics_store import get_metrics_store

router = APIRouter()


@router.get("/activities/recent")
async def get_recent_activities() -> List[Dict[str, Any]]:
    """获取最近系统活动"""
    store = get_metrics_store()
    return store.get_recent_activities(limit=50)
