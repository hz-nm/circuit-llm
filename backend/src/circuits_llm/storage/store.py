"""SQLite persistence for projects, chat messages, circuit versions and model endpoints.

A new connection is opened per operation: the app is single-user and local, so
this keeps the store thread-safe (FastAPI runs sync handlers in a thread pool)
without connection pooling. Schema changes are applied as numbered migrations
tracked with ``PRAGMA user_version``.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from pydantic import SecretStr

from circuits_llm.domain import Circuit
from circuits_llm.llm.contracts import ModelEndpoint
from circuits_llm.simulation.results import SimulationResult

from .records import (
    MessageMeta,
    MessageRecord,
    ProjectRecord,
    VersionRecord,
    VersionSource,
    VersionSummary,
)

MAX_PROJECTS_LISTED: Final = 500
MAX_MESSAGES_LISTED: Final = 2000
MAX_ENDPOINTS: Final = 32
_BUSY_TIMEOUT_S: Final = 10.0

_MIGRATIONS: Final[tuple[str, ...]] = (
    """
    CREATE TABLE model_endpoints (
        id TEXT PRIMARY KEY,
        position INTEGER NOT NULL,
        config TEXT NOT NULL
    );
    CREATE TABLE projects (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE versions (
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        number INTEGER NOT NULL,
        source TEXT NOT NULL,
        circuit TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (project_id, number)
    );
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        version_number INTEGER,
        meta TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    );
    CREATE INDEX messages_by_project ON messages (project_id, id);
    CREATE TABLE simulations (
        project_id TEXT NOT NULL,
        version_number INTEGER NOT NULL,
        result TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (project_id, version_number),
        FOREIGN KEY (project_id, version_number)
            REFERENCES versions (project_id, number) ON DELETE CASCADE
    );
    """,
)


class NotFoundError(LookupError):
    """Raised when a referenced row does not exist."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


class Store:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path, timeout=_BUSY_TIMEOUT_S)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:  # commits on success, rolls back on exception
                yield conn
        finally:
            conn.close()

    def _migrate(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            current: int = conn.execute("PRAGMA user_version").fetchone()[0]
            if current > len(_MIGRATIONS):
                raise RuntimeError(
                    f"database {self._path} has schema version {current}, newer than this "
                    f"build supports ({len(_MIGRATIONS)}); please upgrade circuits-llm"
                )
            for version, script in enumerate(_MIGRATIONS[current:], start=current + 1):
                conn.executescript(f"BEGIN; {script} PRAGMA user_version = {version}; COMMIT;")

    # ----------------------------------------------------------------- endpoints

    def list_endpoints(self) -> list[ModelEndpoint]:
        with self._connect() as conn:
            rows = conn.execute("SELECT config FROM model_endpoints ORDER BY position").fetchall()
        return [_endpoint_from_json(row["config"]) for row in rows]

    def get_endpoint(self, endpoint_id: str) -> ModelEndpoint:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT config FROM model_endpoints WHERE id = ?", (endpoint_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"model endpoint {endpoint_id!r} not found")
        return _endpoint_from_json(row["config"])

    def save_endpoint(self, endpoint: ModelEndpoint) -> ModelEndpoint:
        """Insert or update ``endpoint``; new endpoints go to the end of the fallback chain."""
        config = _endpoint_to_json(endpoint)
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM model_endpoints WHERE id = ?", (endpoint.id,)
            ).fetchone()
            if exists:
                conn.execute(
                    "UPDATE model_endpoints SET config = ? WHERE id = ?", (config, endpoint.id)
                )
                return endpoint
            count: int = conn.execute("SELECT COUNT(*) FROM model_endpoints").fetchone()[0]
            if count >= MAX_ENDPOINTS:
                raise ValueError(f"at most {MAX_ENDPOINTS} model endpoints can be configured")
            conn.execute(
                "INSERT INTO model_endpoints (id, position, config) VALUES (?, ?, ?)",
                (endpoint.id, count, config),
            )
        return endpoint

    def delete_endpoint(self, endpoint_id: str) -> None:
        with self._connect() as conn:
            deleted = conn.execute("DELETE FROM model_endpoints WHERE id = ?", (endpoint_id,))
            if deleted.rowcount == 0:
                raise NotFoundError(f"model endpoint {endpoint_id!r} not found")

    def reorder_endpoints(self, ordered_ids: Sequence[str]) -> None:
        with self._connect() as conn:
            existing = {row["id"] for row in conn.execute("SELECT id FROM model_endpoints")}
            if set(ordered_ids) != existing or len(ordered_ids) != len(existing):
                raise ValueError("the new order must list every configured endpoint exactly once")
            conn.executemany(
                "UPDATE model_endpoints SET position = ? WHERE id = ?",
                [(position, eid) for position, eid in enumerate(ordered_ids)],
            )

    # ----------------------------------------------------------------- projects

    _PROJECT_SELECT: Final = """
        SELECT p.id, p.title, p.created_at, p.updated_at,
               (SELECT MAX(number) FROM versions v WHERE v.project_id = p.id) AS latest_version
        FROM projects p
    """

    def create_project(self, title: str) -> ProjectRecord:
        project_id, now = _new_id(), _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (project_id, title, now, now),
            )
        return self.get_project(project_id)

    def list_projects(self) -> list[ProjectRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                f"{self._PROJECT_SELECT} ORDER BY p.updated_at DESC LIMIT ?",
                (MAX_PROJECTS_LISTED,),
            ).fetchall()
        return [ProjectRecord.model_validate(dict(row)) for row in rows]

    def get_project(self, project_id: str) -> ProjectRecord:
        with self._connect() as conn:
            row = conn.execute(
                f"{self._PROJECT_SELECT} WHERE p.id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"project {project_id!r} not found")
        return ProjectRecord.model_validate(dict(row))

    def rename_project(self, project_id: str, title: str) -> ProjectRecord:
        with self._connect() as conn:
            updated = conn.execute(
                "UPDATE projects SET title = ?, updated_at = ? WHERE id = ?",
                (title, _now(), project_id),
            )
            if updated.rowcount == 0:
                raise NotFoundError(f"project {project_id!r} not found")
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> None:
        with self._connect() as conn:
            deleted = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            if deleted.rowcount == 0:
                raise NotFoundError(f"project {project_id!r} not found")

    # ----------------------------------------------------------------- messages

    def add_message(
        self,
        project_id: str,
        role: str,
        content: str,
        *,
        version_number: int | None = None,
        meta: MessageMeta | None = None,
    ) -> MessageRecord:
        now = _now()
        meta_json = (meta or MessageMeta()).model_dump_json()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO messages (project_id, role, content, version_number, meta, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, role, content, version_number, meta_json, now),
            )
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
            row = conn.execute(
                "SELECT * FROM messages WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return _message_from_row(row)

    def list_messages(self, project_id: str) -> list[MessageRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM (SELECT * FROM messages WHERE project_id = ? ORDER BY id DESC"
                " LIMIT ?) ORDER BY id",
                (project_id, MAX_MESSAGES_LISTED),
            ).fetchall()
        return [_message_from_row(row) for row in rows]

    # ----------------------------------------------------------------- versions

    def add_version(
        self, project_id: str, circuit: Circuit, source: VersionSource
    ) -> VersionRecord:
        now = _now()
        with self._connect() as conn:
            number: int = conn.execute(
                "SELECT COALESCE(MAX(number), 0) + 1 FROM versions WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO versions (project_id, number, source, circuit, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (project_id, number, source, circuit.model_dump_json(), now),
            )
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
        return VersionRecord(
            project_id=project_id,
            number=number,
            source=source,
            circuit=circuit,
            created_at=datetime.fromisoformat(now),
        )

    def get_version(self, project_id: str, number: int) -> VersionRecord:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM versions WHERE project_id = ? AND number = ?",
                (project_id, number),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"version {number} of project {project_id!r} not found")
        return _version_from_row(row)

    def latest_version(self, project_id: str) -> VersionRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM versions WHERE project_id = ? ORDER BY number DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        return None if row is None else _version_from_row(row)

    def list_versions(self, project_id: str) -> list[VersionSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT number, source, json_extract(circuit, '$.title') AS title, created_at"
                " FROM versions WHERE project_id = ? ORDER BY number",
                (project_id,),
            ).fetchall()
        return [VersionSummary.model_validate(dict(row)) for row in rows]

    # ----------------------------------------------------------------- simulations

    def save_simulation(self, project_id: str, number: int, result: SimulationResult) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO simulations"
                " (project_id, version_number, result, created_at)"
                " VALUES (?, ?, ?, ?)",
                (project_id, number, result.model_dump_json(), _now()),
            )

    def get_simulation(self, project_id: str, number: int) -> SimulationResult | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT result FROM simulations WHERE project_id = ? AND version_number = ?",
                (project_id, number),
            ).fetchone()
        return None if row is None else SimulationResult.model_validate_json(row["result"])


# --------------------------------------------------------------------------- row mapping


def _endpoint_to_json(endpoint: ModelEndpoint) -> str:
    data: dict[str, Any] = endpoint.model_dump(mode="json")
    data["api_key"] = endpoint.api_key.get_secret_value() if endpoint.api_key else None
    return json.dumps(data)


def _endpoint_from_json(raw: str) -> ModelEndpoint:
    data: dict[str, Any] = json.loads(raw)
    key = data.get("api_key")
    data["api_key"] = SecretStr(key) if key else None
    return ModelEndpoint.model_validate(data)


def _message_from_row(row: sqlite3.Row) -> MessageRecord:
    return MessageRecord(
        id=row["id"],
        role=row["role"],
        content=row["content"],
        version_number=row["version_number"],
        meta=MessageMeta.model_validate_json(row["meta"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _version_from_row(row: sqlite3.Row) -> VersionRecord:
    return VersionRecord(
        project_id=row["project_id"],
        number=row["number"],
        source=row["source"],
        circuit=Circuit.model_validate_json(row["circuit"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )
