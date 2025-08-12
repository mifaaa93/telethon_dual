# services/db.py
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional, Iterable
from telethon.tl.types import User

import aiosqlite
from telethon.tl import types
from config import settings  # путь к базе берём из настроек

# Путь к БД и подготовка директории
DB_PATH = Path(settings.db_path)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_lock = asyncio.Lock()
_conn: Optional[aiosqlite.Connection] = None


# --------------------------- Core ---------------------------

async def connect() -> aiosqlite.Connection:
    """
    Открыть соединение с базой (singleton).
    """
    global _conn
    if _conn is None:
        _conn = await aiosqlite.connect(DB_PATH)
        _conn.row_factory = aiosqlite.Row   # удобное преобразование в dict
        await _conn.execute("PRAGMA journal_mode=WAL;")
        await _conn.execute("PRAGMA synchronous=NORMAL;")
    return _conn


async def close_db() -> None:
    """Закрыть соединение (опционально вызывать при завершении приложения)."""
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


async def init_db() -> None:
    conn = await connect()
    async with _lock:
        # включим внешние ключи на всякий случай
        await conn.execute("PRAGMA foreign_keys=ON;")

        # users
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                tg_id      INTEGER PRIMARY KEY,
                username   TEXT,
                first_name TEXT
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")

        # invites (как у тебя)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS invites (
                link TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                owner_tg_id INTEGER,
                title TEXT,
                date_created INTEGER,
                expire_date INTEGER,
                usage_limit INTEGER,
                request_needed INTEGER,
                usage INTEGER DEFAULT 0,
                approved_request_count INTEGER DEFAULT 0,
                revoked INTEGER DEFAULT 0,
                last_synced_at INTEGER
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_invites_owner    ON invites(owner_tg_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_invites_chat     ON invites(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_invites_created  ON invites(date_created)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_invites_synced   ON invites(last_synced_at)")
        await conn.commit()



# --------------------------- Helpers ---------------------------

def _ts(dt_obj) -> Optional[int]:
    """Безопасно конвертировать datetime -> int (unix)."""
    if not dt_obj:
        return None
    try:
        return int(dt_obj.timestamp())
    except Exception:
        return None


def _rows_to_dicts(rows: list[aiosqlite.Row]) -> list[dict]:
    return [dict(r) for r in rows]


# --------------------------- Insert / Upsert ---------------------------

async def insert_invite_from_exported(
    exported: types.ChatInviteExported,   # или types.ExportedChatInvite в другой версии
    chat_id: int | str,
    owner_tg_id: int,
) -> None:
    """
    Сохранить ссылку напрямую из ChatInviteExported.
    last_synced_at обновляется КАЖДЫЙ раз.
    ON CONFLICT(link) — обновляем ключевые поля и счётчики.
    """
    link = getattr(exported, "link", None)
    if not link:
        return

    now = int(time.time())

    title = getattr(exported, "title", None)
    date_created = _ts(getattr(exported, "date", None)) or now
    expire_date = _ts(getattr(exported, "expire_date", None))
    usage_limit = getattr(exported, "usage_limit", None)
    request_needed = 1 if getattr(exported, "request_needed", False) else 0
    revoked = 1 if getattr(exported, "revoked", False) else 0
    usage = getattr(exported, "usage", 0) or 0
    approved = getattr(exported, "approved_request_count", 0) or 0

    conn = await connect()
    async with _lock:
        await conn.execute(
            """
            INSERT INTO invites (
              link, chat_id, owner_tg_id, title, date_created, expire_date,
              usage_limit, request_needed, usage, approved_request_count, revoked, last_synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(link) DO UPDATE SET
              title                   = COALESCE(excluded.title, title),
              expire_date             = COALESCE(excluded.expire_date, expire_date),
              usage_limit             = COALESCE(excluded.usage_limit, usage_limit),
              request_needed          = excluded.request_needed,
              usage                   = MAX(usage, excluded.usage),
              approved_request_count  = MAX(approved_request_count, excluded.approved_request_count),
              revoked                 = excluded.revoked,
              last_synced_at          = excluded.last_synced_at   -- всегда обновляем штамп синхронизации
            """,
            (
                link,
                str(chat_id),
                owner_tg_id,
                title,
                date_created,
                expire_date,
                usage_limit,
                request_needed,
                usage,
                approved,
                revoked,
                now,
            ),
        )
        await conn.commit()


async def insert_many_from_exported(
    exported_list: Iterable[types.ChatInviteExported],
    chat_id: int | str,
    owner_tg_id: int,
) -> None:
    """
    Пакетная вставка ссылок (одной транзакцией) для одного пользователя.
    last_synced_at обновляется у каждой строки.
    """
    now = int(time.time())
    params: list[tuple] = []

    for e in exported_list:
        link = getattr(e, "link", None)
        if not link:
            continue

        title = getattr(e, "title", None)
        date_created = _ts(getattr(e, "date", None)) or now
        expire_date = _ts(getattr(e, "expire_date", None))
        usage_limit = getattr(e, "usage_limit", None)
        request_needed = 1 if getattr(e, "request_needed", False) else 0
        revoked = 1 if getattr(e, "revoked", False) else 0
        usage = getattr(e, "usage", 0) or 0
        approved = getattr(e, "approved_request_count", 0) or 0

        params.append((
            link,
            str(chat_id),
            owner_tg_id,
            title,
            date_created,
            expire_date,
            usage_limit,
            request_needed,
            usage,
            approved,
            revoked,
            now,   # last_synced_at
        ))

    if not params:
        return

    conn = await connect()
    async with _lock:
        await conn.executemany(
            """
            INSERT INTO invites (
              link, chat_id, owner_tg_id, title, date_created, expire_date,
              usage_limit, request_needed, usage, approved_request_count, revoked, last_synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(link) DO UPDATE SET
              title                   = COALESCE(excluded.title, title),
              expire_date             = COALESCE(excluded.expire_date, expire_date),
              usage_limit             = COALESCE(excluded.usage_limit, usage_limit),
              request_needed          = excluded.request_needed,
              usage                   = MAX(usage, excluded.usage),
              approved_request_count  = MAX(approved_request_count, excluded.approved_request_count),
              revoked                 = excluded.revoked,
              last_synced_at          = excluded.last_synced_at
            """,
            params,
        )
        await conn.commit()


# --------------------------- Update counters ---------------------------

async def update_invite_counters(
    link: str,
    usage: int,
    approved_request_count: int,
    revoked: bool,
) -> None:
    """
    Обновить счётчики по одной ссылке.
    last_synced_at обновляется всегда.
    """
    now = int(time.time())
    conn = await connect()
    async with _lock:
        await conn.execute(
            """
            UPDATE invites
            SET usage                  = MAX(usage, ?),
                approved_request_count = MAX(approved_request_count, ?),
                revoked                = ?,
                last_synced_at         = ?
            WHERE link = ?
            """,
            (usage, approved_request_count, int(revoked), now, link),
        )
        await conn.commit()


# --------------------------- Queries ---------------------------

async def get_invites_by_owner(owner_tg_id: int) -> list[dict]:
    """
    Получить ссылки, созданные конкретным пользователем + его username и имя.
    link
    chat_id
    owner_tg_id
    title
    date_created
    expire_date
    usage_limit
    request_needed
    usage
    approved_request_count
    revoked
    last_synced_at
    owner_username
    owner_first_name

    """
    conn = await connect()
    async with _lock:
        cur = await conn.execute(
            """
            SELECT
                i.*,
                u.username    AS owner_username,
                u.first_name  AS owner_first_name
            FROM invites i
            LEFT JOIN users u
                ON u.tg_id = i.owner_tg_id
            WHERE i.owner_tg_id = ?
            ORDER BY i.date_created DESC
            """,
            (owner_tg_id, )
        )
        rows = await cur.fetchall()
    return _rows_to_dicts(rows)



async def get_all_invites() -> list[dict]:
    """
    Получить все ссылки + данные владельца (username, first_name).
    link
    chat_id
    owner_tg_id
    title
    date_created
    expire_date
    usage_limit
    request_needed
    usage
    approved_request_count
    revoked
    last_synced_at
    owner_username
    owner_first_name
    """
    conn = await connect()
    async with _lock:
        cur = await conn.execute(
            """
            SELECT
                i.*,
                u.username    AS owner_username,
                u.first_name  AS owner_first_name
            FROM invites i
            LEFT JOIN users u
                ON u.tg_id = i.owner_tg_id
            ORDER BY i.date_created DESC
            """
        )
        rows = await cur.fetchall()
    return _rows_to_dicts(rows)


async def get_link(link: str) -> Optional[dict]:
    conn = await connect()
    async with _lock:
        cur = await conn.execute("SELECT * FROM invites WHERE link = ?", (link,))
        row = await cur.fetchone()
    return dict(row) if row else None


async def delete_invite(link: str) -> None:
    conn = await connect()
    async with _lock:
        await conn.execute("DELETE FROM invites WHERE link = ?", (link,))
        await conn.commit()


# --------------------------- Users ---------------------------

async def upsert_user_basic(user: User) -> None:
    """
    Создаёт пользователя или обновляет username/first_name по tg_id.
    """
    conn = await connect()
    async with _lock:
        await conn.execute("""
            INSERT INTO users (tg_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(tg_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name
        """, (user.id, user.username, user.first_name))
        await conn.commit()


async def get_user(tg_id: int) -> Optional[dict]:
    conn = await connect()
    async with _lock:
        cur = await conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
        row = await cur.fetchone()
    return dict(row) if row else None


async def list_users(limit: int = 100, offset: int = 0) -> list[dict]:
    conn = await connect()
    async with _lock:
        cur = await conn.execute(
            "SELECT * FROM users ORDER BY tg_id LIMIT ? OFFSET ?",
            (limit, offset)
        )
        rows = await cur.fetchall()
    return _rows_to_dicts(rows)


async def delete_user(tg_id: int) -> None:
    conn = await connect()
    async with _lock:
        await conn.execute("DELETE FROM users WHERE tg_id = ?", (tg_id,))
        await conn.commit()
