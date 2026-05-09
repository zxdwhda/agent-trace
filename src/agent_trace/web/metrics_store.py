#!/usr/bin/env python3
"""Metrics Store — SQLite 存储 Token 统计和会话历史"""

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

DEFAULT_DB_PATH = Path.home() / ".agent_trace" / "metrics.db"


class MetricsStore:
    """SQLite 指标存储（线程安全）"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """获取线程本地连接"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        """初始化表结构"""
        conn = self._connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS turn_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                model_name TEXT DEFAULT 'unknown',
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read_tokens INTEGER DEFAULT 0,
                cache_write_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                timestamp REAL NOT NULL,
                UNIQUE(session_id, turn_index)
            );

            CREATE TABLE IF NOT EXISTS session_summary (
                session_id TEXT PRIMARY KEY,
                agent_type TEXT DEFAULT 'unknown',
                model_name TEXT DEFAULT 'unknown',
                title TEXT DEFAULT '',
                total_turns INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                archived INTEGER DEFAULT 0,
                first_seen REAL NOT NULL,
                last_active REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_turn_ts ON turn_metrics(timestamp);
            CREATE INDEX IF NOT EXISTS idx_turn_session ON turn_metrics(session_id);
            CREATE INDEX IF NOT EXISTS idx_summary_active ON session_summary(last_active);

            CREATE TABLE IF NOT EXISTS tool_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                skill_name TEXT NOT NULL,
                call_count INTEGER DEFAULT 1,
                timestamp REAL NOT NULL,
                UNIQUE(session_id, skill_name)
            );
            CREATE INDEX IF NOT EXISTS idx_tool_skill ON tool_calls(skill_name);
            CREATE INDEX IF NOT EXISTS idx_tool_session ON tool_calls(session_id);

            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_type TEXT NOT NULL,
                description TEXT,
                metadata TEXT,
                timestamp REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_activity_type ON activity_log(activity_type);
            """
        )
        conn.commit()

    def record_turn(
        self,
        session_id: str,
        turn_index: int,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        total_tokens: int = 0,
        agent_type: str = "unknown",
        title: str = "",
        timestamp: Optional[float] = None,
    ):
        """记录一次 Turn 的指标并更新会话汇总"""
        # 跳过空 turn（但保留有标题的未完成会话）
        is_empty = total_tokens == 0 and input_tokens == 0 and output_tokens == 0
        if is_empty and not title:
            return
        ts = timestamp if timestamp is not None else time.time()
        conn = self._connect()

        # 写入 turn_metrics
        conn.execute(
            """
            INSERT INTO turn_metrics
            (session_id, turn_index, model_name, input_tokens, output_tokens,
             cache_read_tokens, cache_write_tokens, total_tokens, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, turn_index) DO UPDATE SET
                model_name = excluded.model_name,
                input_tokens = excluded.input_tokens,
                output_tokens = excluded.output_tokens,
                cache_read_tokens = excluded.cache_read_tokens,
                cache_write_tokens = excluded.cache_write_tokens,
                total_tokens = excluded.total_tokens,
                timestamp = excluded.timestamp
            """,
            (
                session_id,
                turn_index,
                model_name,
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_write_tokens,
                total_tokens,
                ts,
            ),
        )

        # 更新 session_summary
        conn.execute(
            """
            INSERT INTO session_summary
            (session_id, agent_type, model_name, title, total_turns, total_tokens, first_seen, last_active)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                agent_type = excluded.agent_type,
                model_name = COALESCE(NULLIF(excluded.model_name, 'unknown'), session_summary.model_name),
                title = COALESCE(NULLIF(excluded.title, ''), session_summary.title),
                total_turns = session_summary.total_turns + 1,
                total_tokens = session_summary.total_tokens + excluded.total_tokens,
                last_active = excluded.last_active
            """,
            (session_id, agent_type, model_name, title, total_tokens, ts, ts),
        )
        conn.commit()

    def get_daily_stats(self) -> Dict[str, int]:
        """获取今日统计"""
        now = time.time()
        start_of_day = now - (now % 86400)
        conn = self._connect()
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COUNT(*) as total_turns
            FROM turn_metrics
            WHERE timestamp >= ?
            """,
            (start_of_day,),
        ).fetchone()
        return {
            "total_tokens_today": row["total_tokens"] or 0,
            "total_turns_today": row["total_turns"] or 0,
        }

    def get_token_throughput(self, minutes: int = 5) -> List[Dict[str, Any]]:
        """获取最近 N 分钟的 Token 吞吐（每分钟一个点）"""
        now = time.time()
        cutoff = now - minutes * 60
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT
                CAST((timestamp - ?) / 60 AS INTEGER) as minute_bucket,
                SUM(input_tokens) as input_tokens,
                SUM(output_tokens) as output_tokens,
                SUM(total_tokens) as total_tokens,
                COUNT(*) as turns
            FROM turn_metrics
            WHERE timestamp >= ?
            GROUP BY minute_bucket
            ORDER BY minute_bucket
            """,
            (cutoff, cutoff),
        ).fetchall()
        # 填充缺失的分钟（补零）
        data = {row["minute_bucket"]: row for row in rows}
        result = []
        for i in range(minutes):
            bucket = i
            row = data.get(bucket)
            result.append({
                "minute_offset": bucket,
                "input_tokens": row["input_tokens"] if row else 0,
                "output_tokens": row["output_tokens"] if row else 0,
                "total_tokens": row["total_tokens"] if row else 0,
                "turns": row["turns"] if row else 0,
            })
        return result

    def get_skill_heatmap(self, limit: int = 5) -> List[Dict[str, Any]]:
        """获取技能热度 Top N"""
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT skill_name, SUM(call_count) as total_calls
            FROM tool_calls
            GROUP BY skill_name
            ORDER BY total_calls DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {"skill_name": row["skill_name"], "calls": row["total_calls"] or 0}
            for row in rows
        ]

    def get_model_distribution(self) -> Dict[str, int]:
        """获取模型使用分布"""
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT model_name, SUM(total_tokens) as tokens
            FROM turn_metrics
            GROUP BY model_name
            ORDER BY tokens DESC
            """
        ).fetchall()
        return {row["model_name"]: row["tokens"] or 0 for row in rows}

    def get_token_trend(self, hours: int = 24) -> List[Dict[str, Any]]:
        """获取 Token 趋势（按小时聚合）"""
        cutoff = time.time() - hours * 3600
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT
                CAST((timestamp - ?) / 3600 AS INTEGER) as hour_bucket,
                SUM(input_tokens) as input_tokens,
                SUM(output_tokens) as output_tokens,
                SUM(total_tokens) as total_tokens,
                COUNT(*) as turns
            FROM turn_metrics
            WHERE timestamp >= ?
            GROUP BY hour_bucket
            ORDER BY hour_bucket
            """,
            (cutoff, cutoff),
        ).fetchall()

        result = []
        for row in rows:
            result.append(
                {
                    "hour_offset": row["hour_bucket"],
                    "input_tokens": row["input_tokens"] or 0,
                    "output_tokens": row["output_tokens"] or 0,
                    "total_tokens": row["total_tokens"] or 0,
                    "turns": row["turns"] or 0,
                }
            )
        return result

    def list_sessions(self, limit: int = 500, archived: bool = False) -> List[Dict[str, Any]]:
        """列出历史会话摘要"""
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT
                session_id,
                agent_type,
                model_name,
                title,
                total_turns,
                total_tokens,
                archived,
                first_seen,
                last_active
            FROM session_summary
            WHERE archived = ? AND (total_tokens > 0 OR archived = 0)
            ORDER BY last_active DESC
            LIMIT ?
            """,
            (1 if archived else 0, limit),
        ).fetchall()
        return [
            {
                "session_id": row["session_id"],
                "agent_type": row["agent_type"],
                "model_name": row["model_name"],
                "title": row["title"] or row["session_id"][:8],
                "total_turns": row["total_turns"],
                "total_tokens": row["total_tokens"],
                "archived": bool(row["archived"]),
                "first_seen": row["first_seen"],
                "last_active": row["last_active"],
                "status": "in_progress" if row["total_tokens"] == 0 else "historical",
            }
            for row in rows
        ]

    def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有相关数据"""
        conn = self._connect()
        # 删除 turn_metrics
        conn.execute("DELETE FROM turn_metrics WHERE session_id = ?", (session_id,))
        # 删除 tool_calls
        conn.execute("DELETE FROM tool_calls WHERE session_id = ?", (session_id,))
        # 删除 session_summary
        cursor = conn.execute("DELETE FROM session_summary WHERE session_id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount > 0

    def archive_session(self, session_id: str, archived: bool = True) -> bool:
        """归档或取消归档会话"""
        conn = self._connect()
        cursor = conn.execute(
            "UPDATE session_summary SET archived = ? WHERE session_id = ?",
            (1 if archived else 0, session_id),
        )
        conn.commit()
        return cursor.rowcount > 0

    def auto_archive_old_sessions(self, days: int = 15) -> int:
        """自动归档超过指定天数未活跃的会话"""
        cutoff = time.time() - days * 86400
        conn = self._connect()
        cursor = conn.execute(
            """
            UPDATE session_summary
            SET archived = 1
            WHERE archived = 0 AND last_active < ?
            """,
            (cutoff,),
        )
        conn.commit()
        return cursor.rowcount

    def record_tool_calls(self, session_id: str, skill_counts: Dict[str, int]):
        """记录会话中的工具调用统计"""
        if not skill_counts:
            return
        ts = time.time()
        conn = self._connect()
        for skill_name, count in skill_counts.items():
            conn.execute(
                """
                INSERT INTO tool_calls (session_id, skill_name, call_count, timestamp)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, skill_name) DO UPDATE SET
                    call_count = tool_calls.call_count + excluded.call_count,
                    timestamp = excluded.timestamp
                """,
                (session_id, skill_name, count, ts),
            )
        conn.commit()

    def get_skill_analysis(self) -> List[Dict[str, Any]]:
        """按 skill_name 聚合工具调用分析"""
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT
                skill_name,
                COUNT(DISTINCT session_id) as total_sessions,
                SUM(call_count) as total_calls,
                AVG(CAST(call_count AS FLOAT)) as avg_calls_per_session
            FROM tool_calls
            GROUP BY skill_name
            ORDER BY total_calls DESC
            """
        ).fetchall()
        return [
            {
                "skill_name": row["skill_name"],
                "total_sessions": row["total_sessions"],
                "total_calls": row["total_calls"],
                "avg_calls_per_session": round(row["avg_calls_per_session"] or 0, 2),
            }
            for row in rows
        ]

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取单个会话历史详情"""
        conn = self._connect()
        summary = conn.execute(
            "SELECT * FROM session_summary WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not summary:
            return None

        turns = conn.execute(
            """
            SELECT turn_index, model_name, input_tokens, output_tokens,
                   cache_read_tokens, total_tokens, timestamp
            FROM turn_metrics
            WHERE session_id = ?
            ORDER BY turn_index
            """,
            (session_id,),
        ).fetchall()

        skills = conn.execute(
            """
            SELECT skill_name, call_count
            FROM tool_calls
            WHERE session_id = ?
            ORDER BY call_count DESC
            """,
            (session_id,),
        ).fetchall()

        return {
            "session_id": summary["session_id"],
            "agent_type": summary["agent_type"],
            "model_name": summary["model_name"],
            "total_turns": summary["total_turns"],
            "total_tokens": summary["total_tokens"],
            "first_seen": summary["first_seen"],
            "last_active": summary["last_active"],
            "skills": [
                {"skill_name": s["skill_name"], "call_count": s["call_count"]}
                for s in skills
            ],
            "turns": [
                {
                    "turn_index": t["turn_index"],
                    "model_name": t["model_name"],
                    "input_tokens": t["input_tokens"],
                    "output_tokens": t["output_tokens"],
                    "cache_read_tokens": t["cache_read_tokens"],
                    "total_tokens": t["total_tokens"],
                    "timestamp": t["timestamp"],
                }
                for t in turns
            ],
        }

    def log_activity(
        self,
        activity_type: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """记录系统活动"""
        conn = self._connect()
        conn.execute(
            """
            INSERT INTO activity_log (activity_type, description, metadata, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (
                activity_type,
                description,
                json.dumps(metadata, ensure_ascii=False) if metadata else None,
                time.time(),
            ),
        )
        conn.commit()

    def get_recent_activities(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近活动记录"""
        conn = self._connect()
        rows = conn.execute(
            """
            SELECT id, activity_type, description, metadata, timestamp
            FROM activity_log
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        result = []
        for row in rows:
            meta = None
            if row["metadata"]:
                try:
                    meta = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    meta = {}
            result.append(
                {
                    "id": row["id"],
                    "activity_type": row["activity_type"],
                    "description": row["description"] or "",
                    "metadata": meta or {},
                    "timestamp": row["timestamp"],
                }
            )
        return result


# 全局实例（惰性初始化）
_metrics_store: Optional[MetricsStore] = None
_lock = threading.Lock()


def get_metrics_store(db_path: Optional[str] = None) -> MetricsStore:
    """获取全局 MetricsStore 实例"""
    global _metrics_store
    if _metrics_store is None:
        with _lock:
            if _metrics_store is None:
                _metrics_store = MetricsStore(db_path)
    return _metrics_store
