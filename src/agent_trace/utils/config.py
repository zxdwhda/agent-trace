#!/usr/bin/env python3
"""
配置管理模块
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """应用配置"""
    
    # CozeLoop 配置
    workspace_id: str = ""
    api_token: str = ""
    api_base: str = "https://api.coze.cn"
    
    # 监控配置
    sessions_dir: str = "~/.kimi/sessions/"
    poll_interval: float = 2.0
    active_session_timeout_minutes: int = 30
    
    # 日志配置
    log_level: str = "INFO"
    log_file: str = "/tmp/kimi-cozeloop.log"
    
    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量加载配置"""
        return cls(
            workspace_id=os.getenv("COZELOOP_WORKSPACE_ID", ""),
            api_token=os.getenv("COZELOOP_API_TOKEN", ""),
            api_base=os.getenv("COZELOOP_API_BASE", "https://api.coze.cn"),
            sessions_dir=os.getenv("KIMI_SESSIONS_DIR", "~/.kimi/sessions/"),
            poll_interval=float(os.getenv("KIMI_POLL_INTERVAL", "2.0")),
            active_session_timeout_minutes=int(os.getenv("KIMI_ACTIVE_TIMEOUT", "30")),
            log_level=os.getenv("KIMI_LOG_LEVEL", "INFO"),
            log_file=os.getenv("KIMI_LOG_FILE", "/tmp/kimi-cozeloop.log"),
        )
    
    @classmethod
    def with_defaults(cls, workspace_id: str, api_token: str) -> "Config":
        """使用默认值创建配置（用于快速启动）"""
        return cls(
            workspace_id=workspace_id,
            api_token=api_token,
        )
    
    def setup_env(self):
        """设置环境变量供 SDK 使用"""
        os.environ["COZELOOP_WORKSPACE_ID"] = self.workspace_id
        os.environ["COZELOOP_API_TOKEN"] = self.api_token
        os.environ["COZELOOP_API_BASE"] = self.api_base
