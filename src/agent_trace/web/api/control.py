#!/usr/bin/env python3
"""控制 API"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any

router = APIRouter()


class ControlRequest(BaseModel):
    action: str


@router.post("/control")
async def control(req: ControlRequest) -> Dict[str, Any]:
    """控制指令（预留）"""
    return {"action": req.action, "status": "ok"}
