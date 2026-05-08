from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    repo            TEXT    NOT NULL,
    pr_number       INTEGER NOT NULL DEFAULT 0,
    pr_title        TEXT    NOT NULL DEFAULT '',
    timestamp       TEXT    NOT NULL,
    overall_score   REAL    NOT NULL,
    security_score  REAL    NOT NULL,
    performance_score REAL  NOT NULL,
    architecture_score REAL NOT NULL,
    test_score      REAL    NOT NULL,
    docs_score      REAL    NOT NULL,
    critical_issues INTEGER NOT NULL DEFAULT 0,
    total_issues    INTEGER NOT NULL DEFAULT 0,
    language        TEXT    NOT NULL DEFAULT 'unknown',
    analysis_time   REAL    NOT NULL DEFAULT 0
)
"""


def _db_path() -> str:
    path = os.getenv("EVOLUTION_DB_PATH", "data/evolution.db")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


async def _ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(_CREATE_TABLE)
    await db.commit()


async def save_review(
    *,
    repo: str,
    pr_number: int = 0,
    pr_title: str = "",
    overall_score: float,
    security_score: float,
    performance_score: float,
    architecture_score: float,
    test_score: float,
    docs_score: float,
    critical_issues: int = 0,
    total_issues: int = 0,
    language: str = "unknown",
    analysis_time: float = 0.0,
) -> None:
    async with aiosqlite.connect(_db_path()) as db:
        await _ensure_schema(db)
        await db.execute(
            """INSERT INTO reviews
               (repo, pr_number, pr_title, timestamp, overall_score,
                security_score, performance_score, architecture_score,
                test_score, docs_score, critical_issues, total_issues,
                language, analysis_time)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                repo, pr_number, pr_title,
                datetime.now(UTC).isoformat(),
                overall_score, security_score, performance_score,
                architecture_score, test_score, docs_score,
                critical_issues, total_issues, language, analysis_time,
            ),
        )
        await db.commit()
    logger.info("Evolution record saved | repo=%s pr=%d score=%.1f", repo, pr_number, overall_score)


async def get_evolution(repo: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_schema(db)
        if repo:
            cursor = await db.execute(
                "SELECT * FROM reviews WHERE repo = ? ORDER BY timestamp DESC LIMIT ?",
                (repo, limit),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM reviews ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def list_repos() -> list[str]:
    async with aiosqlite.connect(_db_path()) as db:
        await _ensure_schema(db)
        cursor = await db.execute(
            "SELECT DISTINCT repo FROM reviews ORDER BY repo"
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


def count_critical(findings: list[Any]) -> int:
    return sum(1 for f in findings if getattr(f, "severity", "").upper() == "CRITICAL")


def count_total(findings: list[Any]) -> int:
    return len(findings)
