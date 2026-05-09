#!/usr/bin/env python3
"""智能提示词优化建议 API（v0.6.0）"""

import logging
import time
from typing import Dict, Any, List, Optional

from fastapi import APIRouter

from ..metrics_store import get_metrics_store

router = APIRouter()
logger = logging.getLogger("agent_trace.web")


def _make_suggestion(
    category: str,
    severity: str,
    title: str,
    description: str,
    suggestion: str,
    metric_value: Optional[float] = None,
) -> Dict[str, Any]:
    return {
        "category": category,
        "severity": severity,
        "title": title,
        "description": description,
        "suggestion": suggestion,
        "metric_value": metric_value,
    }


@router.get("/prompt-suggestions")
async def prompt_suggestions() -> List[Dict[str, Any]]:
    """GET /api/prompt-suggestions — 启发式提示词优化建议"""
    suggestions: List[Dict[str, Any]] = []
    try:
        store = get_metrics_store()
        conn = store._connect()
        now = time.time()
        day_ago = now - 86400

        # ========== 1. Token 暴增检测 ==========
        try:
            # 最近 24 小时的平均单 turn token
            avg_row = conn.execute(
                """
                SELECT AVG(CAST(total_tokens AS FLOAT)) as avg_tokens
                FROM turn_metrics
                WHERE timestamp >= ?
                """,
                (day_ago,),
            ).fetchone()
            avg_tokens = (avg_row["avg_tokens"] or 0)

            if avg_tokens > 0:
                rows = conn.execute(
                    """
                    SELECT session_id, turn_index, total_tokens
                    FROM turn_metrics
                    WHERE timestamp >= ? AND total_tokens > ?
                    """,
                    (day_ago, avg_tokens * 3),
                ).fetchall()
                for row in rows:
                    suggestions.append(
                        _make_suggestion(
                            category="token_efficiency",
                            severity="warning",
                            title="单轮 Token 消耗异常",
                            description=(
                                f"检测到 session {row['session_id'][:16]}... "
                                f"第 {row['turn_index']} 轮消耗 {row['total_tokens']} tokens，"
                                f"是平均值 {avg_tokens:.0f} 的 {row['total_tokens'] / avg_tokens:.1f} 倍"
                            ),
                            suggestion="建议检查提示词是否包含过多上下文，尝试使用更精确的指令",
                            metric_value=row["total_tokens"],
                        )
                    )
        except Exception as e:
            logger.debug(f"Token surge check error: {e}")

        # ========== 2. 空会话检测 ==========
        try:
            rows = conn.execute(
                """
                SELECT session_id, total_turns, total_tokens
                FROM session_summary
                WHERE total_turns = 0 OR total_tokens = 0
                LIMIT 20
                """
            ).fetchall()
            for row in rows:
                suggestions.append(
                    _make_suggestion(
                        category="session_health",
                        severity="info",
                        title="空会话或零 Token 会话",
                        description=(
                            f"Session {row['session_id'][:16]}... "
                            f"总轮数 {row['total_turns']}，总 tokens {row['total_tokens']}"
                        ),
                        suggestion="建议检查会话是否正常结束，或是否存在未捕获的错误",
                        metric_value=row["total_tokens"],
                    )
                )
        except Exception as e:
            logger.debug(f"Empty session check error: {e}")

        # ========== 3. 高频率 Skill 检测 ==========
        try:
            rows = conn.execute(
                """
                SELECT
                    agent_type,
                    COUNT(*) as total_sessions,
                    SUM(total_turns) as total_turns,
                    SUM(total_tokens) as total_tokens,
                    AVG(CAST(total_tokens AS FLOAT) / NULLIF(total_turns, 0)) as avg_tokens_per_turn
                FROM session_summary
                WHERE total_tokens > 0
                GROUP BY agent_type
                ORDER BY total_sessions DESC
                LIMIT 1
                """
            ).fetchall()
            if rows:
                top = rows[0]
                avg_tpt = top["avg_tokens_per_turn"] or 0
                if avg_tpt > 5000:
                    suggestions.append(
                        _make_suggestion(
                            category="skill_usage",
                            severity="warning",
                            title="高频 Skill Token 消耗过高",
                            description=(
                                f"使用最多的 skill '{top['agent_type']}' "
                                f"平均每轮消耗 {avg_tpt:.0f} tokens，超过 5000 阈值"
                            ),
                            suggestion="建议优化该 skill 的提示词模板，减少不必要的上下文传递",
                            metric_value=avg_tpt,
                        )
                    )
        except Exception as e:
            logger.debug(f"High frequency skill check error: {e}")

        # ========== 4. 长时间无响应检测 ==========
        try:
            rows = conn.execute(
                """
                SELECT session_id, total_turns, first_seen, last_active
                FROM session_summary
                WHERE last_active < ? AND total_turns > 0
                LIMIT 20
                """,
                (day_ago,),
            ).fetchall()
            for row in rows:
                idle_hours = (now - row["last_active"]) / 3600
                suggestions.append(
                    _make_suggestion(
                        category="session_health",
                        severity="critical",
                        title="长时间无响应的活跃会话",
                        description=(
                            f"Session {row['session_id'][:16]}... "
                            f"最后活跃 {idle_hours:.1f} 小时前，仍有 {row['total_turns']} 轮记录"
                        ),
                        suggestion="建议检查该会话对应的应用是否崩溃或卡死",
                        metric_value=idle_hours,
                    )
                )
        except Exception as e:
            logger.debug(f"Idle session check error: {e}")

        # ========== 5. Cache 效率低检测 ==========
        try:
            rows = conn.execute(
                """
                SELECT
                    session_id,
                    SUM(total_tokens) as sum_total,
                    SUM(cache_read_tokens) as sum_cache
                FROM turn_metrics
                GROUP BY session_id
                HAVING sum_total > 0
                LIMIT 100
                """
            ).fetchall()
            for row in rows:
                total = row["sum_total"] or 0
                cache = row["sum_cache"] or 0
                if total > 1000:
                    ratio = cache / total
                    if ratio < 0.05:
                        suggestions.append(
                            _make_suggestion(
                                category="cache_efficiency",
                                severity="info",
                                title="Cache 读取效率低",
                                description=(
                                    f"Session {row['session_id'][:16]}... "
                                    f"cache_read_tokens / total_tokens 比例仅为 {ratio:.1%}"
                                ),
                                suggestion="建议增加提示词中的重复上下文复用，或检查缓存策略配置",
                                metric_value=ratio,
                            )
                        )
        except Exception as e:
            logger.debug(f"Cache efficiency check error: {e}")

    except Exception as e:
        logger.error(f"Error generating prompt suggestions: {e}")

    return suggestions
