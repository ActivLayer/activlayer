"""Small durable store for runs, approvals, and tamper-evident events."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .spec import Run, RunStatus


class SQLiteStore:
    def __init__(self, path: str | Path = "activlayer.db") -> None:
        self.path = str(path)
        self._initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    worker TEXT NOT NULL,
                    worker_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_step INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL,
                    permissions TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    run_id TEXT NOT NULL,
                    step_name TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, step_name),
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                );
                """
            )

    def create_run(self, run: Run) -> None:
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO runs
                (id, worker, worker_version, status, current_step, state, permissions,
                 error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run.id,
                    run.worker,
                    run.worker_version,
                    run.status.value,
                    run.current_step,
                    json.dumps(run.state),
                    json.dumps(sorted(run.permissions)),
                    run.error,
                    now,
                    now,
                ),
            )

    def get_run(self, run_id: str) -> Run:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown run: {run_id}")
        return Run(
            id=row["id"],
            worker=row["worker"],
            worker_version=row["worker_version"],
            status=RunStatus(row["status"]),
            current_step=row["current_step"],
            state=json.loads(row["state"]),
            permissions=frozenset(json.loads(row["permissions"])),
            error=row["error"],
        )

    def list_runs(self, *, limit: int = 50, worker: str | None = None) -> list[Run]:
        query = "SELECT id FROM runs"
        values: tuple[Any, ...] = ()
        if worker:
            query += " WHERE worker = ?"
            values = (worker,)
        query += " ORDER BY created_at DESC LIMIT ?"
        values = (*values, limit)
        with self.connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return [self.get_run(row["id"]) for row in rows]

    def save_run(self, run: Run) -> None:
        with self.connect() as connection:
            connection.execute(
                """UPDATE runs SET status = ?, current_step = ?, state = ?, permissions = ?,
                error = ?, updated_at = ? WHERE id = ?""",
                (
                    run.status.value,
                    run.current_step,
                    json.dumps(run.state),
                    json.dumps(sorted(run.permissions)),
                    run.error,
                    datetime.now(UTC).isoformat(),
                    run.id,
                ),
            )

    def approve(self, run_id: str, step_name: str, actor: str, reason: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO approvals
                (run_id, step_name, actor, reason, created_at) VALUES (?, ?, ?, ?, ?)""",
                (run_id, step_name, actor, reason, datetime.now(UTC).isoformat()),
            )

    def is_approved(self, run_id: str, step_name: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM approvals WHERE run_id = ? AND step_name = ?",
                (run_id, step_name),
            ).fetchone()
        return row is not None

    def append_event(self, run_id: str, kind: str, payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        created_at = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            previous = connection.execute(
                "SELECT hash FROM events WHERE run_id = ? ORDER BY id DESC LIMIT 1", (run_id,)
            ).fetchone()
            previous_hash = previous["hash"] if previous else "0" * 64
            digest = hashlib.sha256(
                f"{run_id}|{kind}|{encoded}|{created_at}|{previous_hash}".encode()
            ).hexdigest()
            connection.execute(
                """INSERT INTO events
                (run_id, kind, payload, created_at, previous_hash, hash)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (run_id, kind, encoded, created_at, previous_hash, digest),
            )
        return digest

    def events(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        return [
            {
                "kind": row["kind"],
                "payload": json.loads(row["payload"]),
                "created_at": row["created_at"],
                "previous_hash": row["previous_hash"],
                "hash": row["hash"],
            }
            for row in rows
        ]

    def verify_events(self, run_id: str) -> bool:
        previous_hash = "0" * 64
        for event in self.events(run_id):
            encoded = json.dumps(event["payload"], sort_keys=True, separators=(",", ":"))
            expected = hashlib.sha256(
                f"{run_id}|{event['kind']}|{encoded}|{event['created_at']}|{previous_hash}".encode()
            ).hexdigest()
            if event["previous_hash"] != previous_hash or event["hash"] != expected:
                return False
            previous_hash = event["hash"]
        return True
