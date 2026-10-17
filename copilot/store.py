"""SQLite store: user accounts and sessions, private conversation history,
per-user episodic memory, and the shared assertion store (corrections, scoped
rules, facts and claims people tell the copilot).

Privacy is enforced here: every conversation/episode read takes the
authenticated user_id and filters on it in SQL.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY, name TEXT, role TEXT, team_id TEXT,
  pw_salt TEXT, pw_hash TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS auth_sessions (
  token TEXT PRIMARY KEY, user_id TEXT, created_at TEXT, expires_at TEXT);
CREATE TABLE IF NOT EXISTS conversations (
  conv_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT, sim_date TEXT,
  created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, conv_id TEXT NOT NULL, user_id TEXT NOT NULL,
  role TEXT, content TEXT, payload TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS episodes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, conv_id TEXT, sim_date TEXT,
  question TEXT, summary TEXT, entities TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS assertions (
  id TEXT PRIMARY KEY, kind TEXT, asset_id TEXT, inspection_id TEXT, well_type TEXT, area_id TEXT,
  equipment_kind TEXT, field TEXT, old_value TEXT, new_value TEXT, rule_key TEXT,
  text TEXT, rationale TEXT, author_user_id TEXT, created_at TEXT, valid_from TEXT, valid_to TEXT,
  status TEXT, conflicts TEXT, visibility TEXT DEFAULT 'shared', conv_id TEXT);
CREATE TABLE IF NOT EXISTS preferences (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, text TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS login_attempts (
  user_id TEXT, ip TEXT, ok INTEGER, at TEXT);
CREATE INDEX IF NOT EXISTS ix_msg_conv ON messages(conv_id);
CREATE INDEX IF NOT EXISTS ix_conv_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS ix_ep_user ON episodes(user_id);
"""


def clean_json(o):
    """Replaces NaN/Infinity (from pandas) with None so payloads are valid JSON."""
    if isinstance(o, float):
        return None if (o != o or o in (float("inf"), float("-inf"))) else o
    if isinstance(o, dict):
        return {k: clean_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean_json(v) for v in o]
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):
        try:
            return clean_json(o.item())
        except Exception:
            return str(o)
    return o


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


class Store:
    def __init__(self, path: str | None = None):
        self.path = path or config.DB_PATH
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.version = 0  # bumps whenever assertions change, so the engine can refresh

    def _q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def _x(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    # ------------------------------------------------------------------ auth
    def seed_users(self, users: dict, default_password: str):
        for u in users.values():
            if self._q("SELECT 1 FROM users WHERE user_id=?", (u["user_id"],)):
                self._x("UPDATE users SET name=?, role=?, team_id=? WHERE user_id=?",
                        (u["name"], u.get("role"), u.get("team_id"), u["user_id"]))
                continue
            salt = secrets.token_hex(16)
            self._x("INSERT INTO users VALUES (?,?,?,?,?,?,?)",
                    (u["user_id"], u["name"], u.get("role"), u.get("team_id"), salt,
                     _hash(default_password, salt), _now()))

    def list_users(self):
        return self._q("SELECT user_id, name, role, team_id FROM users ORDER BY user_id")

    def get_user(self, user_id):
        r = self._q("SELECT user_id, name, role, team_id FROM users WHERE user_id=?", (user_id,))
        return r[0] if r else None

    def login(self, user_id: str, password: str) -> str | None:
        r = self._q("SELECT pw_salt, pw_hash FROM users WHERE user_id=?", (user_id,))
        if not r or not hmac.compare_digest(_hash(password, r[0]["pw_salt"]), r[0]["pw_hash"]):
            return None
        token = secrets.token_urlsafe(32)
        exp = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="seconds")
        self._x("INSERT INTO auth_sessions VALUES (?,?,?,?)", (token, user_id, _now(), exp))
        return token

    def user_for_token(self, token: str | None):
        if not token:
            return None
        r = self._q("SELECT user_id, expires_at FROM auth_sessions WHERE token=?", (token,))
        if not r or r[0]["expires_at"] < _now():
            return None
        return self.get_user(r[0]["user_id"])

    def logout(self, token: str):
        self._x("DELETE FROM auth_sessions WHERE token=?", (token,))

    def change_password(self, user_id: str, old: str, new: str) -> bool:
        r = self._q("SELECT pw_salt, pw_hash FROM users WHERE user_id=?", (user_id,))
        if not r or not hmac.compare_digest(_hash(old, r[0]["pw_salt"]), r[0]["pw_hash"]) or len(new) < 6:
            return False
        salt = secrets.token_hex(16)
        self._x("UPDATE users SET pw_salt=?, pw_hash=? WHERE user_id=?", (salt, _hash(new, salt), user_id))
        return True

    # ------------------------------------------------------------------ private conversations
    def new_conversation(self, user_id: str, sim_date: str, title: str = "New chat") -> str:
        cid = "C-" + uuid.uuid4().hex[:10]
        self._x("INSERT INTO conversations VALUES (?,?,?,?,?,?)", (cid, user_id, title, sim_date, _now(), _now()))
        return cid

    def conversations(self, user_id: str):
        return self._q("SELECT * FROM conversations WHERE user_id=? ORDER BY updated_at DESC", (user_id,))

    def conversation(self, user_id: str, conv_id: str):
        r = self._q("SELECT * FROM conversations WHERE user_id=? AND conv_id=?", (user_id, conv_id))
        return r[0] if r else None

    def rename_conversation(self, user_id, conv_id, title):
        self._x("UPDATE conversations SET title=? WHERE user_id=? AND conv_id=?", (title[:80], user_id, conv_id))

    def add_message(self, user_id: str, conv_id: str, role: str, content: str, payload: dict | None = None):
        if not self.conversation(user_id, conv_id):
            raise PermissionError("conversation does not belong to this user")
        self._x("INSERT INTO messages (conv_id,user_id,role,content,payload,created_at) VALUES (?,?,?,?,?,?)",
                (conv_id, user_id, role, content, json.dumps(clean_json(payload or {}), default=str), _now()))
        self._x("UPDATE conversations SET updated_at=? WHERE conv_id=?", (_now(), conv_id))

    def messages(self, user_id: str, conv_id: str):
        rows = self._q("SELECT role, content, payload, created_at FROM messages WHERE user_id=? AND conv_id=? "
                       "ORDER BY id", (user_id, conv_id))
        for r in rows:
            r["payload"] = clean_json(json.loads(r["payload"] or "{}"))
        return rows

    # ------------------------------------------------------------------ episodic memory (private)
    def add_episode(self, user_id, conv_id, sim_date, question, summary, entities):
        self._x("INSERT INTO episodes (user_id,conv_id,sim_date,question,summary,entities,created_at) "
                "VALUES (?,?,?,?,?,?,?)", (user_id, conv_id, sim_date, question, summary,
                                           json.dumps(entities), _now()))

    def episodes(self, user_id: str, exclude_conv: str | None = None):
        rows = self._q("SELECT * FROM episodes WHERE user_id=? AND (? IS NULL OR conv_id != ?) ORDER BY id",
                       (user_id, exclude_conv, exclude_conv))
        for r in rows:
            r["entities"] = json.loads(r["entities"] or "[]")
        return rows

    # ------------------------------------------------------------------ private preferences
    def add_preference(self, user_id: str, text: str):
        self._x("INSERT INTO preferences (user_id,text,created_at) VALUES (?,?,?)", (user_id, text, _now()))

    def preferences(self, user_id: str):
        return [r["text"] for r in self._q("SELECT text FROM preferences WHERE user_id=? ORDER BY id", (user_id,))]

    # ------------------------------------------------------------------ shared assertions
    def add_assertion(self, **kw) -> dict:
        n = len(self._q("SELECT id FROM assertions")) + 1
        a = {"id": f"FB-{n:04d}", "created_at": _now(), "visibility": "shared", **kw}
        a["conflicts"] = json.dumps(a.get("conflicts") or [], default=str)
        cols = ",".join(a.keys())
        self._x(f"INSERT INTO assertions ({cols}) VALUES ({','.join('?' * len(a))})",
                tuple(None if v is None else (v if isinstance(v, str) else json.dumps(v) if isinstance(v, (dict, list)) else str(v)) for v in a.values()))
        # a newer applied correction of the same field supersedes the older one
        if a.get("status") == "applied" and a.get("inspection_id") and a.get("field"):
            self._x("UPDATE assertions SET status='superseded' WHERE inspection_id=? AND field=? AND id!=? "
                    "AND status='applied'", (a["inspection_id"], a["field"], a["id"]))
        self.version += 1
        return self.assertions(ids=[a["id"]])[0]

    def assertions(self, ids=None, asset_id=None):
        sql, args = "SELECT * FROM assertions WHERE 1=1", []
        if ids:
            sql += f" AND id IN ({','.join('?' * len(ids))})"
            args += ids
        if asset_id:
            sql += " AND asset_id=?"
            args.append(asset_id)
        rows = self._q(sql + " ORDER BY created_at, id", args)
        for r in rows:
            r["conflicts"] = json.loads(r["conflicts"] or "[]")
        return rows

    def reset_memory(self):
        """Clears runtime feedback and conversations (for re-running scenarios). Keeps accounts."""
        for t in ("assertions", "episodes", "messages", "conversations", "preferences"):
            self._x(f"DELETE FROM {t}")
        self.version += 1
