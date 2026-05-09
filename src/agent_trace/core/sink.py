#!/usr/bin/env python3
"""双平台 CozeLoop Sink 适配器"""

import json
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import urllib.request
import urllib.error

logger = logging.getLogger("agent_trace.sink")


class Sink(ABC):
    """抽象 Sink 接口"""

    @abstractmethod
    def report_turn_end(self, session_state: Any) -> None:
        """在 Turn 结束时上报数据

        Args:
            session_state: SessionState 实例
        """
        pass


class CozeLoopOfficialSink(Sink):
    """官方 CozeLoop SDK 上报（已集成 SDK，此处仅负责 Flush）"""

    def report_turn_end(self, session_state: Any) -> None:
        try:
            import cozeloop
            cozeloop.flush()
            logger.debug("[Sink:Official] Flushed CozeLoop SDK queue")
        except Exception as e:
            logger.warning(f"[Sink:Official] Flush failed: {e}")


class CozeLoopOpenSourceSink(Sink):
    """开源版 CozeLoop HTTP 上报

    参考 thrift: IngestTracesRequest { spans: list<InputSpan> }
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        workspace_id: Optional[str] = None,
        api_token: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("COZELOOP_OPENSOURCE_BASE", "http://localhost:8080")).rstrip("/")
        self.workspace_id = workspace_id or os.getenv("COZELOOP_WORKSPACE_ID", "")
        self.api_token = api_token or os.getenv("COZELOOP_API_TOKEN", "")

    def report_turn_end(self, session_state: Any) -> None:
        try:
            trace_id = ""
            if session_state.trace_context:
                trace_id = session_state.trace_context.trace_id

            span_id = uuid.uuid4().hex[:16]
            now_ms = int(time.time() * 1000)
            duration_ms = max(1, int((time.time() - getattr(session_state, "_turn_start_time", time.time())) * 1000))

            # 构造最小化 InputSpan
            span: Dict[str, Any] = {
                "started_at_micros": now_ms * 1000,
                "span_id": span_id,
                "parent_id": "0",
                "trace_id": trace_id or f"trace_{span_id}",
                "duration": duration_ms,
                "workspace_id": self.workspace_id,
                "span_name": "agent_turn",
                "span_type": "agent",
                "method": "POST",
                "status_code": 0,
                "input": json.dumps({"user_input": session_state.last_user_message}, ensure_ascii=False),
                "output": json.dumps(
                    {
                        "total_tokens": session_state.total_tokens,
                        "input_tokens": session_state.total_input_tokens,
                        "output_tokens": session_state.total_output_tokens,
                        "cache_read_tokens": session_state.total_cache_read_tokens,
                        "cache_write_tokens": session_state.total_cache_write_tokens,
                    },
                    ensure_ascii=False,
                ),
                "tags_string": {
                    "session_id": session_state.session_id,
                    "agent_type": session_state.agent_type,
                    "model_name": session_state.model_name,
                    "turn_index": str(session_state.turn_index),
                },
            }

            payload = json.dumps({"spans": [span]}, ensure_ascii=False).encode("utf-8")
            url = f"{self.base_url}/v1/loop/traces/ingest"
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "cozeloop-workspace-id": self.workspace_id,
                    "Authorization": f"Bearer {self.api_token}" if self.api_token else "",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                logger.debug(
                    f"[Sink:OpenSource] IngestTraces status={resp.status}, "
                    f"session={session_state.session_id[:8]}..."
                )
        except urllib.error.HTTPError as e:
            logger.warning(f"[Sink:OpenSource] HTTP {e.code}: {e.reason}")
        except Exception as e:
            logger.warning(f"[Sink:OpenSource] Report failed: {e}")


class MultiSink(Sink):
    """同时向多个 Sink 上报"""

    def __init__(self, sinks: List[Sink]):
        self.sinks = sinks

    def report_turn_end(self, session_state: Any) -> None:
        for sink in self.sinks:
            try:
                sink.report_turn_end(session_state)
            except Exception as e:
                logger.warning(f"[Sink:Multi] Sub-sink error: {e}")


def create_sink(
    mode: str,
    base_url: Optional[str] = None,
    workspace_id: Optional[str] = None,
    api_token: Optional[str] = None,
) -> Optional[Sink]:
    """根据模式创建对应的 Sink

    Args:
        mode: official / opensource / both
    """
    mode = mode.lower()
    if mode == "official":
        return CozeLoopOfficialSink()
    elif mode == "opensource":
        return CozeLoopOpenSourceSink(base_url, workspace_id, api_token)
    elif mode == "both":
        return MultiSink(
            [
                CozeLoopOfficialSink(),
                CozeLoopOpenSourceSink(base_url, workspace_id, api_token),
            ]
        )
    else:
        logger.warning(f"[Sink] Unknown mode '{mode}', no sink created")
        return None
