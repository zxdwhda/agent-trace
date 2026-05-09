#!/usr/bin/env python3
"""FastAPI Web 服务器 — 为 AgentTrace Desktop 提供 API 和 WebSocket"""

import os
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from ..core.monitor import AgentTraceMonitor
from ..core.event_bus import event_bus
from .api import status, sessions, control
from .api import config as config_api
from .api import import_batch as import_api
from .api import skills as skills_api
from .api import prompt_optimizer as prompt_api
from .api import activities as activities_api
from .api import live as live_api

logger = logging.getLogger("agent_trace.web")

# WebSocket 连接管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        disconnected = set()
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.add(conn)
        self.active_connections -= disconnected

manager = ConnectionManager()


async def event_forwarder():
    """从 EventBus 消费事件并广播给所有 WebSocket 客户端"""
    while True:
        try:
            event = await event_bus.get()
            await manager.broadcast(event)
        except Exception as e:
            logger.error(f"Event forwarder error: {e}")


async def auto_archive_task():
    """后台定时任务：每24小时自动归档超过15天未活跃的会话"""
    from .metrics_store import get_metrics_store
    while True:
        try:
            await asyncio.sleep(86400)
            store = get_metrics_store()
            count = await asyncio.to_thread(store.auto_archive_old_sessions, 15)
            if count > 0:
                event_bus.put_sync("session.auto_archived", "system", {"count": count})
                logger.info(f"Auto-archived {count} old sessions")
        except Exception as e:
            logger.error(f"Auto-archive task error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动事件转发器
    forwarder_task = asyncio.create_task(event_forwarder())
    # 启动自动归档定时任务
    archive_task = asyncio.create_task(auto_archive_task())
    # 启动监控引擎（独立 Web 模式也自动扫描）
    monitor_task = None
    try:
        sessions_dir = str(Path.home() / ".kimi" / "sessions")
        if os.path.exists(sessions_dir):
            monitor = AgentTraceMonitor(
                sessions_dir=sessions_dir,
                poll_interval=2.0,
            )
            status.set_monitor(monitor)
            sessions.set_monitor(monitor)
            live_api.set_monitor(monitor)
            import threading
            monitor_thread = threading.Thread(target=monitor.start, daemon=True)
            monitor_thread.start()
            logger.info(f"AgentTrace Monitor started (sessions_dir={sessions_dir})")
    except Exception as e:
        logger.warning(f"Failed to start monitor in web server: {e}")

    logger.info("AgentTrace Web Server started")
    yield
    forwarder_task.cancel()
    archive_task.cancel()
    logger.info("AgentTrace Web Server stopped")


app = FastAPI(
    title="AgentTrace API",
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由
app.include_router(status.router, prefix="/api", tags=["status"])
app.include_router(sessions.router, prefix="/api", tags=["sessions"])
app.include_router(control.router, prefix="/api", tags=["control"])
app.include_router(config_api.router, prefix="/api", tags=["config"])
app.include_router(import_api.router, prefix="/api", tags=["import"])
app.include_router(skills_api.router, prefix="/api", tags=["skills"])
app.include_router(prompt_api.router, prefix="/api", tags=["prompt"])
app.include_router(activities_api.router, prefix="/api", tags=["activities"])
app.include_router(live_api.router, prefix="/api", tags=["live"])


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # 接收客户端消息（如控制指令）
            data = await websocket.receive_text()
            # 暂不处理客户端消息
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# 静态文件（生产环境）
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir) and os.listdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


def main():
    import uvicorn
    port = int(os.getenv("AGENTTRACE_WEB_PORT", "18765"))
    uvicorn.run(
        "agent_trace.web.server:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
