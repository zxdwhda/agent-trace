#!/usr/bin/env python3
"""批量历史导入 API（v0.5.0）"""

import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..metrics_store import get_metrics_store
from ...core.event_bus import event_bus

router = APIRouter()
logger = logging.getLogger("agent_trace.web")

SESSIONS_DIR = Path.home() / ".kimi" / "sessions"
KIMI_CONFIG_PATH = Path.home() / ".kimi" / "config.toml"


def _get_default_model_name() -> str:
    """读取 Kimi CLI 配置文件中的默认模型名称"""
    try:
        if not KIMI_CONFIG_PATH.exists():
            return "unknown"
        config_text = KIMI_CONFIG_PATH.read_text(encoding="utf-8")
        # 尝试用 toml 解析
        try:
            import tomllib
            data = tomllib.loads(config_text)
            model = data.get("default_model", "")
            if model:
                return model
        except ImportError:
            try:
                import tomli
                data = tomli.loads(config_text)
                model = data.get("default_model", "")
                if model:
                    return model
            except ImportError:
                pass
        # 降级：正则提取
        match = re.search(r'^default_model\s*=\s*"([^"]+)"', config_text, re.MULTILINE)
        if match:
            return match.group(1)
    except Exception as e:
        logger.debug(f"Error reading kimi config: {e}")
    return "unknown"


_DEFAULT_MODEL_NAME: Optional[str] = None


def _get_cached_default_model() -> str:
    """缓存的默认模型名称"""
    global _DEFAULT_MODEL_NAME
    if _DEFAULT_MODEL_NAME is None:
        _DEFAULT_MODEL_NAME = _get_default_model_name()
    return _DEFAULT_MODEL_NAME


class ImportRequest(BaseModel):
    date_from: str
    date_to: str


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: List[str]


def _parse_date(date_str: str) -> datetime:
    """解析 YYYY-MM-DD 格式日期"""
    return datetime.strptime(date_str, "%Y-%m-%d")


def _find_wire_files() -> List[Path]:
    """扫描所有 wire.jsonl 文件"""
    files: List[Path] = []
    if not SESSIONS_DIR.exists():
        return files
    try:
        for workdir_dir in SESSIONS_DIR.iterdir():
            if not workdir_dir.is_dir():
                continue
            for session_dir in workdir_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                wire_file = session_dir / "wire.jsonl"
                if wire_file.exists():
                    files.append(wire_file)
    except Exception as e:
        logger.error(f"Error scanning sessions dir: {e}")
    return files


def _get_file_date_range(wire_file: Path) -> Optional[Dict[str, str]]:
    """从文件内容推断日期范围"""
    try:
        with open(wire_file, "r", encoding="utf-8") as f:
            first_ts = None
            last_ts = None
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    ts = record.get("timestamp")
                    if ts:
                        if first_ts is None:
                            first_ts = ts
                        last_ts = ts
                except json.JSONDecodeError:
                    continue
        if first_ts and last_ts:
            return {
                "from": datetime.fromtimestamp(first_ts).strftime("%Y-%m-%d"),
                "to": datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d"),
            }
    except Exception as e:
        logger.debug(f"Error reading date range from {wire_file}: {e}")
    return None


def _get_session_id_from_path(wire_file: Path) -> str:
    """从路径提取 session_id"""
    return wire_file.parent.name


def _extract_text_from_user_input(user_input) -> str:
    """处理 user_input 可能是字符串或消息列表的情况"""
    if isinstance(user_input, str):
        return user_input.strip()
    if isinstance(user_input, list) and user_input:
        # 消息列表格式: [{"type": "text", "text": "..."}]
        parts = []
        for item in user_input:
            if isinstance(item, dict):
                if item.get("type") == "text" and item.get("text"):
                    parts.append(item["text"])
        return " ".join(parts).strip()
    return ""


def _derive_title(wire_file: Path) -> str:
    """从 wire.jsonl 提取会话标题（第一条 TurnBegin 的 user_input）"""
    try:
        with open(wire_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    msg = record.get("message") or {}
                    if msg.get("type") == "TurnBegin":
                        payload = msg.get("payload") or {}
                        user_input = payload.get("user_input", "")
                        text = _extract_text_from_user_input(user_input)
                        if text:
                            text = text.replace("\n", " ")
                            if len(text) > 100:
                                text = text[:97] + "..."
                            return text
                except (json.JSONDecodeError, AttributeError):
                    continue
    except Exception:
        pass
    return ""


def _parse_wire_file(wire_file: Path) -> Tuple[List[Dict[str, Any]], Dict[str, int], str, float]:
    """解析 wire.jsonl 文件中的 turn 数据，返回 (turns, skill_counts, title, file_mtime)"""
    turns: List[Dict[str, Any]] = []
    session_id = _get_session_id_from_path(wire_file)
    current_turn: Optional[Dict[str, Any]] = None
    skill_counts: Dict[str, int] = {}
    title = _derive_title(wire_file)
    default_model = _get_cached_default_model()
    
    # 使用文件 mtime 作为默认时间戳（当 record 中没有 timestamp 时）
    try:
        file_mtime = wire_file.stat().st_mtime
    except Exception:
        file_mtime = time.time()

    try:
        with open(wire_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg = record.get("message") or {}
                event_type = msg.get("type", "")
                payload = msg.get("payload") or {}
                ts = record.get("timestamp", file_mtime)

                if event_type == "TurnBegin":
                    current_turn = {
                        "session_id": payload.get("session_id", session_id),
                        "timestamp": ts,
                        "turn_index": len(turns),
                        "model_name": "unknown",
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cache_read_tokens": 0,
                        "cache_write_tokens": 0,
                        "total_tokens": 0,
                    }
                elif event_type == "StatusUpdate" and current_turn is not None:
                    token_usage = payload.get("token_usage", {})
                    current_turn["input_tokens"] = token_usage.get("input_other", 0) + token_usage.get("input_cache_read", 0)
                    current_turn["output_tokens"] = token_usage.get("output", 0)
                    current_turn["cache_read_tokens"] = token_usage.get("input_cache_read", 0)
                    current_turn["cache_write_tokens"] = token_usage.get("input_cache_creation", 0)
                    current_turn["total_tokens"] = (
                        current_turn["input_tokens"]
                        + current_turn["output_tokens"]
                        + current_turn["cache_write_tokens"]
                    )
                    # 尝试从 StatusUpdate 提取 model_name
                    model = payload.get("model")
                    if model and current_turn["model_name"] == "unknown":
                        current_turn["model_name"] = model
                elif event_type == "ToolCall":
                    fn = payload.get("function", {})
                    skill_name = fn.get("name", "unknown")
                    skill_counts[skill_name] = skill_counts.get(skill_name, 0) + 1
                elif event_type == "TurnEnd" and current_turn is not None:
                    # 优先使用 TurnEnd payload 中的数据（如果存在）
                    current_turn["session_id"] = payload.get("session_id", current_turn["session_id"])
                    current_turn["model_name"] = payload.get("model_name", current_turn["model_name"])
                    current_turn["total_tokens"] = payload.get("total_tokens", current_turn["total_tokens"])
                    current_turn["input_tokens"] = payload.get("input_tokens", current_turn["input_tokens"])
                    current_turn["output_tokens"] = payload.get("output_tokens", current_turn["output_tokens"])
                    current_turn["timestamp"] = payload.get("timestamp", current_turn["timestamp"])
                    turns.append(current_turn)
                    current_turn = None
    except Exception as e:
        logger.warning(f"Error parsing {wire_file}: {e}")

    # 文件结束时，如果还有未完成的 turn，也加入（未完成的会话）
    if current_turn is not None:
        current_turn["timestamp"] = current_turn.get("timestamp", file_mtime)
        turns.append(current_turn)

    # 如果 model_name 仍是 unknown，用配置中的默认模型替换
    if default_model and default_model != "unknown":
        for turn in turns:
            if turn.get("model_name") == "unknown":
                turn["model_name"] = default_model

    return turns, skill_counts, title, file_mtime


def _filter_files_by_date(files: List[Path], date_from: datetime, date_to: datetime) -> List[Path]:
    """按文件修改时间筛选 wire.jsonl 文件"""
    result: List[Path] = []
    date_to_end = date_to + timedelta(days=1)
    for wf in files:
        try:
            mtime = datetime.fromtimestamp(wf.stat().st_mtime)
            if date_from <= mtime < date_to_end:
                result.append(wf)
        except Exception as e:
            logger.debug(f"Error checking mtime for {wf}: {e}")
    return result


@router.get("/import/preview")
async def import_preview(
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
) -> Dict[str, Any]:
    """GET /api/import/preview — 预览可导入的历史会话（dry run）"""
    try:
        d_from = _parse_date(date_from)
        d_to = _parse_date(date_to)
    except ValueError:
        return {"error": "Invalid date format, expected YYYY-MM-DD"}

    try:
        all_files = _find_wire_files()
        filtered = _filter_files_by_date(all_files, d_from, d_to)

        session_ids: set = set()
        existing_ids: set = set()
        date_ranges: List[Dict[str, str]] = []

        store = get_metrics_store()
        for wf in filtered:
            sid = _get_session_id_from_path(wf)
            session_ids.add(sid)
            dr = _get_file_date_range(wf)
            if dr:
                date_ranges.append(dr)

        # 检查哪些 session 已存在
        for sid in session_ids:
            if store.get_session(sid) is not None:
                existing_ids.add(sid)

        # 计算 date_range
        range_from = None
        range_to = None
        for dr in date_ranges:
            d = datetime.strptime(dr["from"], "%Y-%m-%d")
            if range_from is None or d < range_from:
                range_from = d
            d = datetime.strptime(dr["to"], "%Y-%m-%d")
            if range_to is None or d > range_to:
                range_to = d

        return {
            "total_files": len(filtered),
            "total_sessions": len(session_ids),
            "existing_sessions": len(existing_ids),
            "new_sessions": len(session_ids) - len(existing_ids),
            "date_range": {
                "from": range_from.strftime("%Y-%m-%d") if range_from else date_from,
                "to": range_to.strftime("%Y-%m-%d") if range_to else date_to,
            },
        }
    except Exception as e:
        logger.error(f"Error in import preview: {e}")
        return {"error": str(e)}


@router.post("/import/batch")
async def import_batch(req: ImportRequest) -> Dict[str, Any]:
    """POST /api/import/batch — 批量导入历史会话"""
    try:
        d_from = _parse_date(req.date_from)
        d_to = _parse_date(req.date_to)
    except ValueError:
        return {"imported": 0, "skipped": 0, "errors": ["Invalid date format, expected YYYY-MM-DD"]}

    imported = 0
    skipped = 0
    errors: List[str] = []
    store = get_metrics_store()

    try:
        all_files = _find_wire_files()
        filtered = _filter_files_by_date(all_files, d_from, d_to)
        total = len(filtered)

        event_bus.put_sync("import.started", "system", {"total_files": total, "date_from": req.date_from, "date_to": req.date_to})

        for idx, wf in enumerate(filtered):
            sid = _get_session_id_from_path(wf)
            try:
                # 去重：如果 session 已存在则跳过
                if store.get_session(sid) is not None:
                    skipped += 1
                    continue

                turns, skill_counts, title, file_mtime = _parse_wire_file(wf)
                for turn in turns:
                    store.record_turn(
                        session_id=turn["session_id"],
                        turn_index=turn["turn_index"],
                        model_name=turn["model_name"],
                        input_tokens=turn["input_tokens"],
                        output_tokens=turn["output_tokens"],
                        cache_read_tokens=turn["cache_read_tokens"],
                        cache_write_tokens=turn["cache_write_tokens"],
                        total_tokens=turn["total_tokens"],
                        agent_type="kimi_cli",
                        title=title,
                        timestamp=turn.get("timestamp", file_mtime),
                    )
                if skill_counts:
                    store.record_tool_calls(sid, skill_counts)
                if turns:
                    imported += 1

                # 推送进度事件
                if (idx + 1) % 5 == 0 or idx == total - 1:
                    event_bus.put_sync("import.progress", "system", {
                        "current": idx + 1,
                        "total": total,
                        "imported": imported,
                        "skipped": skipped,
                    })
            except Exception as e:
                logger.warning(f"Error importing {wf}: {e}")
                errors.append(f"{sid}: {str(e)}")

        event_bus.put_sync("import.completed", "system", {
            "imported": imported,
            "skipped": skipped,
            "errors": len(errors),
        })

        store.log_activity(
            activity_type="import_completed",
            description=f"批量导入完成：成功 {imported} 个，跳过 {skipped} 个",
            metadata={"imported": imported, "skipped": skipped, "errors": len(errors)},
        )

        return {"imported": imported, "skipped": skipped, "errors": errors}
    except Exception as e:
        logger.error(f"Error in import batch: {e}")
        return {"imported": imported, "skipped": skipped, "errors": errors + [str(e)]}
