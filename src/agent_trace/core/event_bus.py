#!/usr/bin/env python3
"""事件总线 — 解耦 Monitor 与 Web 推送（线程安全版）"""

import asyncio
import json
import logging
import queue
import threading
import time
from typing import Dict, Any

logger = logging.getLogger("agent_trace.event_bus")


class EventBus:
    """线程安全事件总线，基于 threading.Queue + asyncio 桥接"""

    def __init__(self, maxsize: int = 10000):
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        self._lock = threading.Lock()

    def put(self, event_type: str, session_id: str, payload: Dict[str, Any]):
        """投递事件（线程安全，支持 sync/async 调用）"""
        event = {
            "type": event_type,
            "session_id": session_id,
            "timestamp": time.time(),
            "payload": payload,
        }
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            logger.warning("Event bus queue full, dropping event")

    def put_sync(self, event_type: str, session_id: str, payload: Dict[str, Any]):
        """同步接口（与 put 相同，保留兼容）"""
        self.put(event_type, session_id, payload)

    async def get(self) -> Dict[str, Any]:
        """消费事件（async 接口，内部桥接 threading.Queue）"""
        loop = asyncio.get_running_loop()
        # 在线程池中阻塞获取，避免 event loop 冲突
        return await loop.run_in_executor(None, self._queue.get)

    def get_stats(self) -> Dict[str, int]:
        return {
            "queue_size": self._queue.qsize(),
            "maxsize": self._queue.maxsize,
        }


# 全局事件总线实例（线程安全）
event_bus = EventBus()
