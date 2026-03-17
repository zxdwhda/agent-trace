#!/usr/bin/env python3
"""
日志配置模块
"""

import logging
import sys
from pathlib import Path


def setup_logging(log_level: str = "INFO", log_file: str = "/tmp/kimi-cozeloop.log") -> logging.Logger:
    """
    配置日志系统
    
    Args:
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        log_file: 日志文件路径
        
    Returns:
        配置好的 logger 实例
    """
    logger = logging.getLogger("agent_trace")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # 清除已有 handler
    logger.handlers = []
    
    # 格式化
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 获取日志级别数值
    log_level_value = getattr(logging, log_level.upper())
    
    # 控制台输出 - 使用与文件相同的日志级别
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level_value)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件输出
    if log_file:
        log_path = Path(log_file).expanduser()
        # 只在目录不存在且不是系统标准目录时创建
        if not log_path.parent.exists() and log_path.parent != Path('/tmp'):
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                # 权限不足时使用 /tmp 作为回退
                fallback_path = Path('/tmp') / log_path.name
                logger.warning(f"Cannot create log directory {log_path.parent}, using {fallback_path}")
                log_path = fallback_path
        
        try:
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setLevel(log_level_value)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except PermissionError as e:
            logger.error(f"Cannot write to log file {log_path}: {e}")
            # 尝试使用 /tmp 作为回退
            try:
                fallback_path = Path('/tmp') / log_path.name
                file_handler = logging.FileHandler(fallback_path, encoding="utf-8")
                file_handler.setLevel(log_level_value)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
                logger.warning(f"Using fallback log path: {fallback_path}")
            except Exception as e2:
                logger.error(f"Failed to create fallback log: {e2}")
    
    return logger
