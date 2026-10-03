"""Single-organization ActivLayer workspace and configuration management."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WORKSPACE_VERSION = 1
MAX_USERS = 3
DEFAULT_DIR = ".activlayer"


class WorkspaceError(RuntimeError):
    pass


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    if not value:
        raise ValueError("A non-empty name is required")
    return value


def _write_json(path: Path, value: Any, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    if private:
        temporary.chmod(0o600)
    temporary.replace(path)


@dataclass(slots=True)
class Workspace:
    root: Path

    @classmethod
    def discover(cls, start: Path | None = None) -> Workspace:
        override = os.getenv("ACTIVLAYER_HOME")
        if override:
            root = Path(override).expanduser().resolve()
            if not (root / "config.json").exists():
                raise WorkspaceError(f"No ActivLayer environment at {root}")
            return cls(root)
        current = (start or Path.cwd()).resolve()
        for directory in (current, *current.parents):
            candidate = directory / DEFAULT_DIR
            if (candidate / "config.json").exists():
                return cls(candidate)
        raise WorkspaceError("No ActivLayer environment found. Run `activlayer init` first.")

    @classmethod
    def initialize(
        cls,
        directory: Path,
        organization: str,
        *,
        owner_email: str | None = None,
    ) -> Workspace:
        root = directory.expanduser().resolve()
        if (root / "config.json").exists():
            raise WorkspaceError(f"An ActivLayer environment already exists at {root}")
        root.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC).isoformat()
        config = {
            "workspace_version": WORKSPACE_VERSION,
            "organization": {
                "id": slugify(organization),
                "name": organization.strip(),
                "max_users": MAX_USERS,
            },
            "active_provider": None,
            "providers": {},
            "connectors": {},
            "extensions": [],
            "runtime": {
                "database": "state.db",
                "log_level": "INFO",
                "default_timeout_seconds": 120,
            },
            "created_at": now,
        }
        users: list[dict[str, Any]] = []
        if owner_email:
            users.append(
                {
                    "id": secrets.token_hex(8),
                    "email": owner_email.strip().lower(),
                    "name": "Owner",
                    "role": "owner",
                    "active": True,
                    "created_at": now,
                }
            )
        _write_json(root / "config.json", config)
        _write_json(root / "users.json", users, private=True)
        _write_json(root / "secrets.json", {}, private=True)
        (root / "agents" / "drafts").mkdir(parents=True)
        (root / "agents" / "published").mkdir(parents=True)
        (root / "logs").mkdir(parents=True)
        return cls(root)

    @property
    def config_path(self) -> Path:
        return self.root / "config.json"

    @property
    def state_path(self) -> Path:
        return self.root / self.config["runtime"]["database"]

    @property
    def config(self) -> dict[str, Any]:
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def save_config(self, config: dict[str, Any]) -> None:
        _write_json(self.config_path, config)

    @property
    def users(self) -> list[dict[str, Any]]:
        return json.loads((self.root / "users.json").read_text(encoding="utf-8"))

    def save_users(self, users: list[dict[str, Any]]) -> None:
        if len(users) > MAX_USERS:
            raise WorkspaceError(f"Community Edition supports at most {MAX_USERS} users")
        _write_json(self.root / "users.json", users, private=True)

    def issue_token(self, email: str) -> str:
        users = self.users
        user = next((item for item in users if item["email"] == email.strip().lower()), None)
        if user is None:
            raise WorkspaceError(f"Unknown user: {email}")
        token = f"alce_{secrets.token_urlsafe(32)}"
        user["token_hash"] = hashlib.sha256(token.encode()).hexdigest()
        user["token_issued_at"] = datetime.now(UTC).isoformat()
        self.save_users(users)
        return token

    def authenticate(self, token: str) -> dict[str, Any] | None:
        digest = hashlib.sha256(token.encode()).hexdigest()
        for user in self.users:
            if user.get("active") and secrets.compare_digest(user.get("token_hash", ""), digest):
                return user
        return None

    @property
    def secrets(self) -> dict[str, str]:
        return json.loads((self.root / "secrets.json").read_text(encoding="utf-8"))

    def set_secret(self, key: str, value: str) -> None:
        values = self.secrets
        values[key] = value
        _write_json(self.root / "secrets.json", values, private=True)

    def delete_secret(self, key: str) -> None:
        values = self.secrets
        values.pop(key, None)
        _write_json(self.root / "secrets.json", values, private=True)

    def resolve_secret(self, key: str | None) -> str | None:
        if not key:
            return None
        return os.getenv(key) or self.secrets.get(key)

    def draft_path(self, agent_id: str) -> Path:
        return self.root / "agents" / "drafts" / f"{slugify(agent_id)}.json"

    def published_path(self, agent_id: str) -> Path:
        return self.root / "agents" / "published" / f"{slugify(agent_id)}.json"
