"""Shared organization knowledge base for products, services, pricing, and procedures."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from .workspace import Workspace, slugify


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_]{2,}", value.casefold())}


class SharedKnowledge:
    def __init__(self, workspace: Workspace) -> None:
        self.path = workspace.root / "knowledge.db"
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS collections (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    collection_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (collection_id) REFERENCES collections(id)
                );
                CREATE INDEX IF NOT EXISTS ix_documents_collection
                ON documents(collection_id, created_at);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def create_collection(self, name: str, description: str = "") -> str:
        collection_id = slugify(name)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO collections (id, name, description, created_at) "
                "VALUES (?, ?, ?, ?)",
                (collection_id, name, description, datetime.now(UTC).isoformat()),
            )
        return collection_id

    def collections(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT c.*, COUNT(d.id) AS documents FROM collections c "
                "LEFT JOIN documents d ON d.collection_id = c.id GROUP BY c.id ORDER BY c.name"
            ).fetchall()
        return [dict(row) for row in rows]

    def add(
        self,
        collection: str,
        title: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        collection_id = slugify(collection)
        document_id = uuid.uuid4().hex
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM collections WHERE id = ?", (collection_id,)
            ).fetchone()
            if not exists:
                raise KeyError(f"Unknown knowledge collection: {collection}")
            connection.execute(
                "INSERT INTO documents (id, collection_id, title, content, metadata, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    document_id,
                    collection_id,
                    title,
                    content,
                    json.dumps(metadata or {}),
                    datetime.now(UTC).isoformat(),
                ),
            )
        return document_id

    def search(
        self,
        query: str,
        *,
        collections: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        statement = "SELECT * FROM documents"
        values: list[Any] = []
        if collections:
            ids = [slugify(value) for value in collections]
            placeholders = ",".join("?" for _ in ids)
            statement += f" WHERE collection_id IN ({placeholders})"
            values.extend(ids)
        with self._connect() as connection:
            rows = connection.execute(statement, tuple(values)).fetchall()
        query_tokens = _tokens(query)
        ranked: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            document_tokens = _tokens(f"{row['title']} {row['content']}")
            overlap = len(query_tokens & document_tokens)
            score = overlap / max(1, len(query_tokens))
            if score > 0 or not query_tokens:
                ranked.append((score, row))
        ranked.sort(key=lambda item: (item[0], item[1]["created_at"]), reverse=True)
        return [
            {
                "id": row["id"],
                "collection": row["collection_id"],
                "title": row["title"],
                "content": row["content"],
                "metadata": json.loads(row["metadata"]),
                "score": round(score, 4),
            }
            for score, row in ranked[:limit]
        ]
