"""Isolated SQLite memory for individual Agent Workers."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from .workspace import Workspace, slugify


class AgentMemory:
    def __init__(self, workspace: Workspace, agent_id: str) -> None:
        directory = workspace.root / "memory"
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{slugify(agent_id)}.db"
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    run_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_memories_scope ON memories(scope, created_at)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def remember(
        self,
        scope: str,
        content: Any,
        *,
        kind: str = "interaction",
        run_id: str | None = None,
    ) -> str:
        memory_id = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO memories (id, scope, kind, content, run_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    memory_id,
                    scope,
                    kind,
                    json.dumps(content, ensure_ascii=False),
                    run_id,
                    datetime.now(UTC).isoformat(),
                ),
            )
        return memory_id

    def recall(self, scope: str, *, limit: int = 5) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM memories WHERE scope = ? ORDER BY created_at DESC LIMIT ?",
                (scope, limit),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "scope": row["scope"],
                "kind": row["kind"],
                "content": json.loads(row["content"]),
                "run_id": row["run_id"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def search(
        self, query: str, *, scope: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        statement = "SELECT * FROM memories WHERE content LIKE ?"
        values: list[Any] = [f"%{query}%"]
        if scope:
            statement += " AND scope = ?"
            values.append(scope)
        statement += " ORDER BY created_at DESC LIMIT ?"
        values.append(limit)
        with self._connect() as connection:
            rows = connection.execute(statement, tuple(values)).fetchall()
        return [
            {
                "id": row["id"],
                "scope": row["scope"],
                "kind": row["kind"],
                "content": json.loads(row["content"]),
                "run_id": row["run_id"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0])
