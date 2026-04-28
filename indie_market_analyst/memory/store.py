"""SQLite-backed persistence for sessions, messages, observations, and run blobs.

Schema is deliberately narrow so the file stays portable. JSON payloads ride in
text columns; structured queries go through dedicated columns.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_DEFAULT_DB = Path(os.environ.get("DB_PATH", "sessions/memory.db"))
_LOCK = threading.Lock()

_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    payload_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    session_id TEXT,
    tag TEXT,
    text TEXT NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_observations_tag ON observations(tag);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    blob_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id, created_at);
"""


def _ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


class MemoryStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB
        _ensure_parent(self.db_path)
        with self._conn() as c:
            c.executescript(_DDL)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with _LOCK:
            conn = sqlite3.connect(self.db_path, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            try:
                yield conn
            finally:
                conn.close()

    # ---- sessions ----
    def create_session(self, meta: dict[str, Any] | None = None) -> str:
        sid = str(uuid.uuid4())
        with self._conn() as c:
            c.execute(
                "INSERT INTO sessions(id, created_at, meta_json) VALUES (?,?,?)",
                (sid, time.time(), json.dumps(meta or {})),
            )
        return sid

    def session_exists(self, session_id: str) -> bool:
        with self._conn() as c:
            row = c.execute("SELECT 1 FROM sessions WHERE id=?", (session_id,)).fetchone()
        return row is not None

    # ---- messages ----
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        payload: dict[str, Any] | None = None,
    ) -> str:
        mid = str(uuid.uuid4())
        with self._conn() as c:
            c.execute(
                "INSERT INTO messages(id, session_id, created_at, role, content, payload_json)"
                " VALUES (?,?,?,?,?,?)",
                (mid, session_id, time.time(), role, content, json.dumps(payload or {})),
            )
        return mid

    def get_messages(self, session_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, role, content, payload_json, created_at FROM messages"
                " WHERE session_id=? ORDER BY created_at ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [
            {"id": r[0], "role": r[1], "content": r[2], "payload": json.loads(r[3] or "{}"),
             "created_at": r[4]}
            for r in rows
        ]

    def get_messages_for_llm(
        self,
        session_id: str,
        limit: int = 20,
        max_chars: int = 32_000,
    ) -> list[dict[str, str]]:
        """Return recent chat history in Responses API message-list shape.

        The database keeps the persistence format unchanged. This helper only
        projects the most recent persisted rows into the message format accepted
        by ``Runner.run_streamed``.
        """
        limit = max(0, int(limit))
        max_chars = max(0, int(max_chars))
        if limit == 0 or max_chars == 0:
            return []

        with self._conn() as c:
            rows = c.execute(
                """
                SELECT role, content FROM messages
                WHERE session_id=? AND role IN ('user', 'assistant', 'system', 'developer')
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        messages = [
            {"role": role, "content": content}
            for role, content in reversed(rows)
            if isinstance(content, str) and content.strip()
        ]

        kept_reversed: list[dict[str, str]] = []
        used_chars = 0
        for msg in reversed(messages):
            content_len = len(msg["content"])
            if used_chars + content_len > max_chars:
                if not kept_reversed:
                    kept_reversed.append({
                        "role": msg["role"],
                        "content": msg["content"][-max_chars:],
                    })
                break
            kept_reversed.append(msg)
            used_chars += content_len
        return list(reversed(kept_reversed))

    # ---- session listing / search / delete ----
    def list_sessions(self, limit: int = 200) -> list[dict[str, Any]]:
        """Return sessions newest-first with a preview of the first user message."""
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT s.id, s.created_at, s.meta_json,
                       (SELECT content FROM messages m
                         WHERE m.session_id = s.id AND m.role = 'user'
                         ORDER BY m.created_at ASC LIMIT 1) AS first_user,
                       (SELECT MAX(created_at) FROM messages m2
                         WHERE m2.session_id = s.id) AS last_activity,
                       (SELECT COUNT(*) FROM messages m3
                         WHERE m3.session_id = s.id) AS msg_count
                FROM sessions s
                ORDER BY COALESCE(
                    (SELECT MAX(created_at) FROM messages m4 WHERE m4.session_id = s.id),
                    s.created_at
                ) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            meta = json.loads(r[2] or "{}")
            preview = (r[3] or "").strip().replace("\n", " ")
            if len(preview) > 80:
                preview = preview[:77] + "…"
            out.append({
                "id": r[0],
                "created_at": r[1],
                "last_activity": r[4] or r[1],
                "message_count": r[5] or 0,
                "preview": preview or "(empty)",
                "title": meta.get("title") or preview or "New chat",
            })
        return out

    def delete_session(self, session_id: str) -> bool:
        with self._conn() as c:
            cur = c.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            # messages/observations cascade via FK; also nuke runs (no FK).
            c.execute("DELETE FROM runs WHERE session_id=?", (session_id,))
            c.execute("DELETE FROM observations WHERE session_id=?", (session_id,))
            return cur.rowcount > 0

    def search_messages(
        self, query: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Simple substring search over message content; returns session rows
        with matching snippets.
        """
        q = f"%{query.strip()}%" if query.strip() else "%"
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT m.session_id, m.content, m.created_at, m.role
                FROM messages m
                WHERE m.content LIKE ?
                ORDER BY m.created_at DESC
                LIMIT ?
                """,
                (q, limit),
            ).fetchall()
        seen: dict[str, dict[str, Any]] = {}
        for sid, content, at, role in rows:
            if sid in seen:
                continue
            snippet = (content or "").strip().replace("\n", " ")
            idx = snippet.lower().find(query.lower()) if query else -1
            if idx > 40:
                snippet = "…" + snippet[idx - 30: idx + 70]
            elif len(snippet) > 120:
                snippet = snippet[:117] + "…"
            seen[sid] = {
                "session_id": sid,
                "snippet": snippet,
                "at": at,
                "role": role,
            }
        return list(seen.values())

    # ---- observations (long-term memory) ----
    def add_observation(
        self, text: str, tag: str | None = None, session_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> str:
        oid = str(uuid.uuid4())
        with self._conn() as c:
            c.execute(
                "INSERT INTO observations(id, created_at, session_id, tag, text, meta_json)"
                " VALUES (?,?,?,?,?,?)",
                (oid, time.time(), session_id, tag, text, json.dumps(meta or {})),
            )
        return oid

    def recent_observations(self, tag: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as c:
            if tag:
                rows = c.execute(
                    "SELECT id, tag, text, created_at FROM observations WHERE tag=?"
                    " ORDER BY created_at DESC LIMIT ?",
                    (tag, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT id, tag, text, created_at FROM observations"
                    " ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [{"id": r[0], "tag": r[1], "text": r[2], "created_at": r[3]} for r in rows]

    # ---- runs ----
    def save_run(
        self,
        session_id: str,
        kind: str,
        status: str,
        blob: dict[str, Any],
        run_id: str | None = None,
    ) -> str:
        rid = run_id or str(uuid.uuid4())
        with self._conn() as c:
            c.execute(
                "INSERT INTO runs(id, session_id, created_at, kind, status, blob_json)"
                " VALUES (?,?,?,?,?,?)",
                (rid, session_id, time.time(), kind, status, json.dumps(blob)),
            )
        return rid

    def list_runs(self, session_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as c:
            if session_id:
                rows = c.execute(
                    "SELECT id, session_id, kind, status, created_at FROM runs"
                    " WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT id, session_id, kind, status, created_at FROM runs"
                    " ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            {"id": r[0], "session_id": r[1], "kind": r[2], "status": r[3], "created_at": r[4]}
            for r in rows
        ]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT id, session_id, kind, status, created_at, blob_json FROM runs WHERE id=?",
                (run_id,),
            ).fetchone()
            if not row:
                rows = c.execute(
                    "SELECT id, session_id, kind, status, created_at, blob_json FROM runs"
                ).fetchall()
                for candidate in rows:
                    try:
                        blob = json.loads(candidate[5])
                    except json.JSONDecodeError:
                        continue
                    if blob.get("run_id") == run_id:
                        return {
                            "id": candidate[0],
                            "session_id": candidate[1],
                            "kind": candidate[2],
                            "status": candidate[3],
                            "created_at": candidate[4],
                            "blob": blob,
                        }
        if not row:
            return None
        return {
            "id": row[0], "session_id": row[1], "kind": row[2], "status": row[3],
            "created_at": row[4], "blob": json.loads(row[5]),
        }


_singleton: MemoryStore | None = None


def get_store() -> MemoryStore:
    global _singleton
    if _singleton is None:
        _singleton = MemoryStore()
    return _singleton
