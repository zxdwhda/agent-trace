#!/usr/bin/env python3
"""配置 API — Settings 配置持久化（v0.4.1）"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger("agent_trace.web")

CONFIG_DIR = Path.home() / ".agent_trace"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "coze_loop_mode": "official",
    "workspace_id": "",
    "api_token": "",
    "opensource_url": "http://localhost:8082",
    "poll_interval_seconds": 5,
    "log_level": "INFO",
}


class AppConfig(BaseModel):
    coze_loop_mode: str
    workspace_id: str
    api_token: str
    opensource_url: str
    poll_interval_seconds: int
    log_level: str


class ConfigResponse(BaseModel):
    status: str


def _load_config() -> Dict[str, Any]:
    """从文件加载配置，不存在则返回默认值"""
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 合并默认值，确保所有键都存在
        config = dict(DEFAULT_CONFIG)
        config.update(data)
        return config
    except Exception as e:
        logger.warning(f"Failed to load config from {CONFIG_PATH}: {e}")
        return dict(DEFAULT_CONFIG)


def _save_config(config: Dict[str, Any]) -> None:
    """保存配置到文件"""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save config to {CONFIG_PATH}: {e}")
        raise


@router.get("/config")
async def get_config() -> Dict[str, Any]:
    """GET /api/config — 读取配置"""
    try:
        return _load_config()
    except Exception as e:
        logger.error(f"Error reading config: {e}")
        return dict(DEFAULT_CONFIG)


@router.post("/config")
async def post_config(body: AppConfig) -> Dict[str, str]:
    """POST /api/config — 写入配置"""
    try:
        config = body.dict()
        _save_config(config)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return {"status": "error", "message": str(e)}
