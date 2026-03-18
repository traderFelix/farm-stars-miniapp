import sqlite3
import time
from typing import Optional

DB_PATH = "/Users/vadym/telegram/felix-farm-stars-bot/bot.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_miniapp_tables():
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS miniapp_tasks (
                id INTEGER PRIMARY KEY,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                reward REAL NOT NULL,
                hold_seconds INTEGER NOT NULL,
                telegram_url TEXT NOT NULL,
                channel_name TEXT,
                message_id INTEGER,
                is_active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS miniapp_task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                opened_at INTEGER,
                completed_at INTEGER,
                reward REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                UNIQUE(user_id, task_id)
            )
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_miniapp_task_events_user_status
            ON miniapp_task_events(user_id, status)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_miniapp_tasks_active_sort
            ON miniapp_tasks(is_active, sort_order, id)
            """
        )

        conn.commit()
    finally:
        conn.close()


def seed_demo_tasks_if_empty():
    conn = get_connection()
    try:
        cur = conn.execute("SELECT COUNT(*) AS cnt FROM miniapp_tasks")
        row = cur.fetchone()
        if int(row["cnt"]) > 0:
            return

        now_ts = int(time.time())
        demo_rows = [
            (
                101,
                "view_post",
                "Просмотреть пост #1",
                0.03,
                3,
                "https://t.me/telegram/1",
                "@telegram",
                1,
                1,
                1,
                now_ts,
            ),
            (
                102,
                "view_post",
                "Просмотреть пост #2",
                0.04,
                4,
                "https://t.me/telegram/2",
                "@telegram",
                2,
                1,
                2,
                now_ts,
            ),
            (
                103,
                "view_post",
                "Просмотреть пост #3",
                0.05,
                5,
                "https://t.me/telegram/3",
                "@telegram",
                3,
                1,
                3,
                now_ts,
            ),
        ]

        conn.executemany(
            """
            INSERT INTO miniapp_tasks (
                id, type, title, reward, hold_seconds, telegram_url,
                channel_name, message_id, is_active, sort_order, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            demo_rows,
        )
        conn.commit()
    finally:
        conn.close()


def fetch_user_by_id(user_id: int):
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT
                user_id,
                username,
                balance
            FROM users
            WHERE user_id = ?
            """,
            (int(user_id),),
        )
        return cur.fetchone()
    finally:
        conn.close()


def add_balance_to_user(user_id: int, delta: float):
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE users
            SET balance = COALESCE(balance, 0) + ?
            WHERE user_id = ?
            """,
            (float(delta), int(user_id)),
        )
        conn.commit()

        cur = conn.execute(
            """
            SELECT balance
            FROM users
            WHERE user_id = ?
            """,
            (int(user_id),),
        )
        row = cur.fetchone()
        return float(row["balance"] or 0) if row else 0.0
    finally:
        conn.close()


def fetch_next_task_for_user(user_id: int):
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT
                t.id,
                t.type,
                t.title,
                t.reward,
                t.hold_seconds,
                t.telegram_url,
                t.channel_name,
                t.message_id
            FROM miniapp_tasks t
            LEFT JOIN miniapp_task_events e
                ON e.task_id = t.id
               AND e.user_id = ?
            WHERE t.is_active = 1
              AND (e.id IS NULL OR e.status != 'completed')
            ORDER BY t.sort_order ASC, t.id ASC
            LIMIT 1
            """,
            (int(user_id),),
        )
        return cur.fetchone()
    finally:
        conn.close()


def fetch_task_by_id(task_id: int):
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT
                id,
                type,
                title,
                reward,
                hold_seconds,
                telegram_url,
                channel_name,
                message_id,
                is_active
            FROM miniapp_tasks
            WHERE id = ?
            LIMIT 1
            """,
            (int(task_id),),
        )
        return cur.fetchone()
    finally:
        conn.close()


def fetch_task_event(user_id: int, task_id: int):
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT
                id,
                user_id,
                task_id,
                opened_at,
                completed_at,
                reward,
                status
            FROM miniapp_task_events
            WHERE user_id = ?
              AND task_id = ?
            LIMIT 1
            """,
            (int(user_id), int(task_id)),
        )
        return cur.fetchone()
    finally:
        conn.close()


def open_task_for_user(user_id: int, task_id: int, reward: float):
    now_ts = int(time.time())
    conn = get_connection()
    try:
        existing = conn.execute(
            """
            SELECT status
            FROM miniapp_task_events
            WHERE user_id = ?
              AND task_id = ?
            LIMIT 1
            """,
            (int(user_id), int(task_id)),
        ).fetchone()

        if existing and existing["status"] == "completed":
            return {"error": "Task already completed"}

        if existing:
            conn.execute(
                """
                UPDATE miniapp_task_events
                SET opened_at = ?, status = 'opened', reward = ?
                WHERE user_id = ?
                  AND task_id = ?
                """,
                (now_ts, float(reward), int(user_id), int(task_id)),
            )
        else:
            conn.execute(
                """
                INSERT INTO miniapp_task_events (
                    user_id, task_id, opened_at, completed_at, reward, status
                )
                VALUES (?, ?, ?, NULL, ?, 'opened')
                """,
                (int(user_id), int(task_id), now_ts, float(reward)),
            )

        conn.commit()
        return {"opened_at": now_ts}
    finally:
        conn.close()


def complete_task_for_user(user_id: int, task_id: int, reward: float):
    now_ts = int(time.time())
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE miniapp_task_events
            SET completed_at = ?, status = 'completed', reward = ?
            WHERE user_id = ?
              AND task_id = ?
            """,
            (now_ts, float(reward), int(user_id), int(task_id)),
        )
        conn.commit()
        return now_ts
    finally:
        conn.close()


def list_completed_tasks_for_user(user_id: int, limit: int = 20):
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT
                e.task_id,
                t.title,
                e.reward,
                e.completed_at
            FROM miniapp_task_events e
            JOIN miniapp_tasks t
              ON t.id = e.task_id
            WHERE e.user_id = ?
              AND e.status = 'completed'
            ORDER BY e.completed_at DESC, e.id DESC
            LIMIT ?
            """,
            (int(user_id), int(limit)),
        )
        return cur.fetchall()
    finally:
        conn.close()