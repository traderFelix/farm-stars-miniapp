from typing import Optional, cast

import aiosqlite

from shared.config import OWNER_TYPE_CLIENT
from shared.db.partners import allocate_partner_views, get_partner_remaining_views

TASK_POST_OPEN_SESSION_TTL_SECONDS = 10 * 60


async def _column_exists(db: aiosqlite.Connection, table_name: str, column_name: str) -> bool:
    async with db.execute(f"PRAGMA table_info({table_name})") as cur:
        rows = await cur.fetchall()

    for row in rows:
        name = row["name"] if isinstance(row, aiosqlite.Row) else row[1]
        if name == column_name:
            return True
    return False


async def ensure_task_channels_client_schema(db: aiosqlite.Connection) -> None:
    if not await _column_exists(db, "task_channels", "client_user_id"):
        await db.execute(
            "ALTER TABLE task_channels ADD COLUMN client_user_id INTEGER"
        )
    if not await _column_exists(db, "task_channels", "owner_type"):
        await db.execute(
            "ALTER TABLE task_channels ADD COLUMN owner_type TEXT NOT NULL DEFAULT 'client'"
        )
    if not await _column_exists(db, "task_channels", "partner_views_per_post"):
        await db.execute(
            "ALTER TABLE task_channels ADD COLUMN partner_views_per_post INTEGER NOT NULL DEFAULT 0"
        )
    if not await _column_exists(db, "task_channels", "partner_view_seconds"):
        await db.execute(
            "ALTER TABLE task_channels ADD COLUMN partner_view_seconds INTEGER NOT NULL DEFAULT 0"
        )
    await db.execute(
        """
        UPDATE task_channels
        SET owner_type = ?
        WHERE owner_type IS NULL
           OR TRIM(owner_type) = ''
           OR owner_type NOT IN ('client', 'partner')
        """,
        (OWNER_TYPE_CLIENT,),
    )
    await db.execute(
        """
        UPDATE task_channels
        SET partner_views_per_post = views_per_post
        WHERE partner_views_per_post IS NULL
           OR partner_views_per_post <= 0
        """
    )
    await db.execute(
        """
        UPDATE task_channels
        SET partner_view_seconds = view_seconds
        WHERE partner_view_seconds IS NULL
           OR partner_view_seconds <= 0
        """
    )


async def ensure_task_posts_manual_schema(db: aiosqlite.Connection) -> None:
    if not await _column_exists(db, "task_posts", "source"):
        await db.execute(
            "ALTER TABLE task_posts ADD COLUMN source TEXT NOT NULL DEFAULT 'auto'"
        )
    if not await _column_exists(db, "task_posts", "added_by_admin_id"):
        await db.execute(
            "ALTER TABLE task_posts ADD COLUMN added_by_admin_id INTEGER"
        )
    if not await _column_exists(db, "task_posts", "hold_seconds"):
        await db.execute(
            "ALTER TABLE task_posts ADD COLUMN hold_seconds INTEGER NOT NULL DEFAULT 0"
        )
    await db.execute(
        """
        UPDATE task_posts
        SET hold_seconds = COALESCE(
            (
                SELECT c.view_seconds
                FROM task_channels c
                WHERE c.id = task_posts.channel_id
            ),
            0
        )
        WHERE hold_seconds IS NULL
           OR hold_seconds <= 0
        """
    )


async def ensure_task_post_open_sessions_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS task_post_open_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            task_post_id INTEGER NOT NULL,
            opened_at REAL NOT NULL,
            can_check_at REAL NOT NULL,
            activity_type TEXT,
            activity_id INTEGER,
            status TEXT NOT NULL DEFAULT 'opened',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT
        )
        """
    )
    if not await _column_exists(db, "task_post_open_sessions", "activity_type"):
        await db.execute("ALTER TABLE task_post_open_sessions ADD COLUMN activity_type TEXT")
    if not await _column_exists(db, "task_post_open_sessions", "activity_id"):
        await db.execute("ALTER TABLE task_post_open_sessions ADD COLUMN activity_id INTEGER")
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_task_post_open_sessions_task_status
        ON task_post_open_sessions(task_post_id, status, opened_at)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_task_post_open_sessions_user_task_status
        ON task_post_open_sessions(user_id, task_post_id, status, opened_at)
        """
    )


async def cleanup_expired_task_post_open_sessions(db: aiosqlite.Connection) -> None:
    await ensure_task_post_open_sessions_schema(db)
    await db.execute(
        """
        UPDATE task_post_open_sessions
        SET status = 'expired'
        WHERE status = 'opened'
          AND opened_at < CAST(strftime('%s', 'now') AS REAL) - ?
        """,
        (TASK_POST_OPEN_SESSION_TTL_SECONDS,),
    )


def _active_open_sessions_count_sql() -> str:
    return """
        SELECT COUNT(*)
        FROM task_post_open_sessions s
        WHERE s.task_post_id = p.id
          AND s.status = 'opened'
          AND s.opened_at >= CAST(strftime('%s', 'now') AS REAL) - ?
    """


async def count_available_view_post_tasks_for_user(
        db: aiosqlite.Connection,
        user_id: int,
) -> int:
    await cleanup_expired_task_post_open_sessions(db)
    async with db.execute(
            f"""
        SELECT COUNT(*)
        FROM task_posts p
        WHERE p.is_active = 1
          AND p.current_views < p.required_views
          AND p.current_views + ({_active_open_sessions_count_sql()}) < p.required_views
          AND NOT EXISTS (
              SELECT 1
              FROM task_post_views v
              WHERE v.user_id = ?
                AND v.task_post_id = p.id
          )
        """,
            (TASK_POST_OPEN_SESSION_TTL_SECONDS, int(user_id)),
    ) as cur:
        row = await cur.fetchone()
        return int(row[0] or 0)


async def get_next_view_post_task_for_user(
        db: aiosqlite.Connection,
        user_id: int,
):
    await ensure_task_posts_manual_schema(db)
    await cleanup_expired_task_post_open_sessions(db)
    async with db.execute(
            f"""
        SELECT
            p.id,
            p.channel_id,
            c.chat_id,
            c.title AS channel_title,
            COALESCE(NULLIF(p.hold_seconds, 0), c.view_seconds) AS view_seconds,
            p.channel_post_id,
            p.reward,
            p.required_views,
            p.current_views,
            p.created_at
        FROM task_posts p
        JOIN task_channels c ON c.id = p.channel_id
        WHERE p.is_active = 1
          AND p.current_views < p.required_views
          AND p.current_views + ({_active_open_sessions_count_sql()}) < p.required_views
          AND NOT EXISTS (
              SELECT 1
              FROM task_post_views v
              WHERE v.user_id = ?
                AND v.task_post_id = p.id
          )
        ORDER BY datetime(p.created_at) ASC, p.id ASC
        LIMIT 1
        """,
            (TASK_POST_OPEN_SESSION_TTL_SECONDS, int(user_id)),
    ) as cur:
        return await cur.fetchone()


async def get_openable_view_post_task_for_user(
        db: aiosqlite.Connection,
        user_id: int,
        task_post_id: int,
):
    await ensure_task_posts_manual_schema(db)
    await cleanup_expired_task_post_open_sessions(db)
    async with db.execute(
            f"""
        SELECT
            p.id,
            p.channel_id,
            c.chat_id,
            c.title AS channel_title,
            COALESCE(NULLIF(p.hold_seconds, 0), c.view_seconds) AS view_seconds,
            p.channel_post_id,
            p.reward,
            p.required_views,
            p.current_views,
            p.created_at
        FROM task_posts p
        JOIN task_channels c ON c.id = p.channel_id
        WHERE p.id = ?
          AND p.is_active = 1
          AND p.current_views < p.required_views
          AND p.current_views + ({_active_open_sessions_count_sql()}) < p.required_views
          AND NOT EXISTS (
              SELECT 1
              FROM task_post_views v
              WHERE v.user_id = ?
                AND v.task_post_id = p.id
          )
        LIMIT 1
        """,
            (int(task_post_id), TASK_POST_OPEN_SESSION_TTL_SECONDS, int(user_id)),
    ) as cur:
        return await cur.fetchone()


async def get_view_post_task_for_user(
        db: aiosqlite.Connection,
        user_id: int,
        task_post_id: int,
):
    await ensure_task_posts_manual_schema(db)
    async with db.execute(
            """
        SELECT
            p.id,
            p.channel_id,
            c.chat_id,
            c.title AS channel_title,
            COALESCE(NULLIF(p.hold_seconds, 0), c.view_seconds) AS view_seconds,
            p.channel_post_id,
            p.reward,
            p.required_views,
            p.current_views,
            p.created_at
        FROM task_posts p
        JOIN task_channels c ON c.id = p.channel_id
        WHERE p.id = ?
          AND p.is_active = 1
          AND p.current_views < p.required_views
          AND NOT EXISTS (
              SELECT 1
              FROM task_post_views v
              WHERE v.user_id = ?
                AND v.task_post_id = p.id
          )
        LIMIT 1
        """,
            (int(task_post_id), int(user_id)),
    ) as cur:
        return await cur.fetchone()


async def create_task_post_open_session(
        db: aiosqlite.Connection,
        *,
        session_id: str,
        user_id: int,
        task_post_id: int,
        opened_at: float,
        can_check_at: float,
        activity_type: Optional[str] = None,
        activity_id: Optional[int] = None,
) -> None:
    await ensure_task_post_open_sessions_schema(db)
    await db.execute(
        """
        INSERT INTO task_post_open_sessions (
            session_id,
            user_id,
            task_post_id,
            opened_at,
            can_check_at,
            activity_type,
            activity_id,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'opened')
        """,
        (
            str(session_id),
            int(user_id),
            int(task_post_id),
            float(opened_at),
            float(can_check_at),
            activity_type,
            int(activity_id) if activity_id is not None else None,
        ),
    )


async def get_view_post_task_for_open_session(
        db: aiosqlite.Connection,
        *,
        user_id: int,
        task_post_id: int,
        session_id: str,
):
    await ensure_task_posts_manual_schema(db)
    await cleanup_expired_task_post_open_sessions(db)
    async with db.execute(
            """
        SELECT
            p.id,
            p.channel_id,
            c.chat_id,
            c.title AS channel_title,
            COALESCE(NULLIF(p.hold_seconds, 0), c.view_seconds) AS view_seconds,
            p.channel_post_id,
            p.reward,
            p.required_views,
            p.current_views,
            p.created_at,
            s.session_id,
            s.opened_at,
            s.can_check_at,
            s.activity_type,
            s.activity_id
        FROM task_post_open_sessions s
        JOIN task_posts p ON p.id = s.task_post_id
        JOIN task_channels c ON c.id = p.channel_id
        WHERE s.session_id = ?
          AND s.user_id = ?
          AND s.task_post_id = ?
          AND s.status = 'opened'
          AND NOT EXISTS (
              SELECT 1
              FROM task_post_views v
              WHERE v.user_id = s.user_id
                AND v.task_post_id = s.task_post_id
          )
        LIMIT 1
        """,
            (str(session_id), int(user_id), int(task_post_id)),
    ) as cur:
        return await cur.fetchone()


async def complete_task_post_open_session(
        db: aiosqlite.Connection,
        *,
        session_id: str,
        status: str = "completed",
) -> None:
    await ensure_task_post_open_sessions_schema(db)
    await db.execute(
        """
        UPDATE task_post_open_sessions
        SET status = ?,
            completed_at = datetime('now')
        WHERE session_id = ?
        """,
        (str(status), str(session_id)),
    )


async def add_task_post_view(db, user_id: int, task_post_id: int, reward: float) -> bool:
    cursor = await db.execute(
        """
        INSERT OR IGNORE INTO task_post_views (user_id, task_post_id, reward)
        VALUES (?, ?, ?)
        """,
        (int(user_id), int(task_post_id), float(reward)),
    )
    return cursor.rowcount == 1


async def count_completed_task_views_for_user(
        db: aiosqlite.Connection,
        user_id: int,
) -> int:
    async with db.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM task_post_views
            WHERE user_id = ?
            """,
            (int(user_id),),
    ) as cur:
        row = await cur.fetchone()
    return int(row["cnt"] or 0)


async def increment_task_post_views(
        db: aiosqlite.Connection,
        task_post_id: int,
) -> bool:
    cur = await db.execute(
        """
        UPDATE task_posts
        SET
            current_views = current_views + 1,
            is_active = CASE
                WHEN current_views + 1 >= required_views THEN 0
                ELSE is_active
            END,
            completed_at = CASE
                WHEN current_views + 1 >= required_views THEN datetime('now')
                ELSE completed_at
            END
        WHERE id = ?
          AND is_active = 1
          AND current_views < required_views
        """,
        (int(task_post_id),),
    )
    return cur.rowcount == 1


async def mark_task_post_unavailable(
        db: aiosqlite.Connection,
        task_post_id: int,
) -> bool:
    await ensure_task_post_open_sessions_schema(db)
    await db.execute(
        """
        UPDATE task_post_open_sessions
        SET status = 'expired'
        WHERE task_post_id = ?
          AND status = 'opened'
        """,
        (int(task_post_id),),
    )
    cur = await db.execute(
        """
        UPDATE task_posts
        SET is_active = 0
        WHERE id = ?
          AND is_active = 1
        """,
        (int(task_post_id),),
    )
    return cur.rowcount == 1


async def list_task_channels(db: aiosqlite.Connection):
    await ensure_task_channels_client_schema(db)
    async with db.execute(
            """
        SELECT
            c.id,
            c.chat_id,
            COALESCE(title, '') AS title,
            c.owner_type,
            c.is_active,
            c.total_bought_views,
            c.views_per_post,
            c.view_seconds,
            c.partner_views_per_post,
            c.partner_view_seconds,
            c.allocated_views,
            (c.total_bought_views - c.allocated_views) AS remaining_views,
            c.created_at,
            c.client_user_id,
            u.username AS client_username,
            u.tg_first_name AS client_first_name
        FROM task_channels c
        LEFT JOIN users u ON u.user_id = c.client_user_id
        ORDER BY c.id DESC
        """
    ) as cur:
        return await cur.fetchall()


async def get_task_channel(db: aiosqlite.Connection, channel_id: int):
    await ensure_task_channels_client_schema(db)
    async with db.execute(
            """
        SELECT
            c.id,
            c.chat_id,
            COALESCE(c.title, '') AS title,
            c.owner_type,
            c.is_active,
            c.total_bought_views,
            c.views_per_post,
            c.view_seconds,
            c.partner_views_per_post,
            c.partner_view_seconds,
            c.allocated_views,
            (c.total_bought_views - c.allocated_views) AS remaining_views,
            c.created_at,
            c.client_user_id,
            u.username AS client_username,
            u.tg_first_name AS client_first_name
        FROM task_channels c
        LEFT JOIN users u ON u.user_id = c.client_user_id
        WHERE c.id = ?
        LIMIT 1
        """,
            (int(channel_id),),
    ) as cur:
        return await cur.fetchone()


async def get_task_channel_by_chat_id(db: aiosqlite.Connection, chat_id: str):
    await ensure_task_channels_client_schema(db)
    async with db.execute(
            """
        SELECT
            c.id,
            c.chat_id,
            COALESCE(c.title, '') AS title,
            c.owner_type,
            c.is_active,
            c.total_bought_views,
            c.views_per_post,
            c.view_seconds,
            c.partner_views_per_post,
            c.partner_view_seconds,
            c.allocated_views,
            (c.total_bought_views - c.allocated_views) AS remaining_views,
            c.created_at,
            c.client_user_id,
            u.username AS client_username,
            u.tg_first_name AS client_first_name
        FROM task_channels c
        LEFT JOIN users u ON u.user_id = c.client_user_id
        WHERE c.chat_id = ?
        LIMIT 1
        """,
            (str(chat_id),),
    ) as cur:
        return await cur.fetchone()


async def create_task_channel(
        db: aiosqlite.Connection,
        chat_id: str,
        title: Optional[str],
        client_user_id: Optional[int],
        owner_type: str,
        total_bought_views: int,
        views_per_post: int,
        view_seconds: int,
) -> int:
    await ensure_task_channels_client_schema(db)
    cur = await db.execute(
        """
        INSERT INTO task_channels (
            chat_id, title, client_user_id, owner_type, is_active, total_bought_views,
            views_per_post, view_seconds, partner_views_per_post, partner_view_seconds,
            allocated_views, created_at
        )
        VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, 0, datetime('now'))
        """,
        (
            str(chat_id),
            title,
            int(client_user_id) if client_user_id is not None else None,
            str(owner_type or OWNER_TYPE_CLIENT),
            int(total_bought_views),
            int(views_per_post),
            int(view_seconds),
            int(views_per_post),
            int(view_seconds),
        ),
    )
    return int(cur.lastrowid)


async def set_task_channel_client(
        db: aiosqlite.Connection,
        channel_id: int,
        client_user_id: Optional[int],
        owner_type: str,
) -> None:
    await ensure_task_channels_client_schema(db)
    await db.execute(
        """
        UPDATE task_channels
        SET client_user_id = ?,
            owner_type = ?
        WHERE id = ?
        """,
        (
            int(client_user_id) if client_user_id is not None else None,
            str(owner_type or OWNER_TYPE_CLIENT),
            int(channel_id),
        ),
    )


async def set_task_channel_title(
        db: aiosqlite.Connection,
        channel_id: int,
        title: Optional[str],
) -> None:
    await db.execute(
        """
        UPDATE task_channels
        SET title = ?
        WHERE id = ?
        """,
        (title, int(channel_id)),
    )


async def set_task_channel_active(db: aiosqlite.Connection, channel_id: int, is_active: int) -> None:
    await db.execute(
        """
        UPDATE task_channels
        SET is_active = ?
        WHERE id = ?
        """,
        (int(is_active), int(channel_id)),
    )


async def task_channel_stats(db: aiosqlite.Connection, channel_id: int):
    async with db.execute(
            """
        SELECT
            COUNT(*) AS total_posts,
            COALESCE(SUM(required_views), 0) AS total_required,
            COALESCE(SUM(current_views), 0) AS total_current,
            SUM(CASE WHEN is_active = 1 AND current_views < required_views THEN 1 ELSE 0 END) AS active_posts
        FROM task_posts
        WHERE channel_id = ?
        """,
            (int(channel_id),),
    ) as cur:
        return await cur.fetchone()


async def update_task_channel_params(
        db: aiosqlite.Connection,
        channel_id: int,
        total_bought_views: int,
        views_per_post: int,
        view_seconds: int,
) -> None:
    await db.execute(
        """
        UPDATE task_channels
        SET
            total_bought_views = ?,
            views_per_post = ?,
            view_seconds = ?
        WHERE id = ?
        """,
        (
            int(total_bought_views),
            int(views_per_post),
            int(view_seconds),
            int(channel_id),
        ),
    )


async def update_task_channel_partner_params(
        db: aiosqlite.Connection,
        channel_id: int,
        partner_views_per_post: int,
        partner_view_seconds: int,
) -> None:
    await db.execute(
        """
        UPDATE task_channels
        SET
            partner_views_per_post = ?,
            partner_view_seconds = ?
        WHERE id = ?
        """,
        (
            int(partner_views_per_post),
            int(partner_view_seconds),
            int(channel_id),
        ),
    )


async def get_task_channel_allocated_views(db: aiosqlite.Connection, channel_id: int) -> int:
    async with db.execute(
            """
        SELECT allocated_views
        FROM task_channels
        WHERE id = ?
        LIMIT 1
        """,
            (int(channel_id),),
    ) as cur:
        row = await cur.fetchone()
        return int(row["allocated_views"] or 0) if row else 0


async def get_task_channel_partner_remaining_views(db: aiosqlite.Connection, channel_row) -> int:
    partner_user_id = channel_row["client_user_id"] if channel_row is not None else None
    if partner_user_id is None:
        return 0
    partner_user_id_value = cast(int, partner_user_id)
    channel_chat_id = str(channel_row["chat_id"])
    return await get_partner_remaining_views(
        db,
        partner_user_id_value,
        channel_chat_id,
    )


async def list_task_posts_by_channel(
        db: aiosqlite.Connection,
        channel_id: int,
        limit: int = 20,
        offset: int = 0,
):
    await ensure_task_posts_manual_schema(db)
    async with db.execute(
            """
        SELECT
            id,
            channel_post_id,
            required_views,
            current_views,
            is_active,
            source,
            added_by_admin_id,
            created_at,
            completed_at
        FROM task_posts
        WHERE channel_id = ?
        ORDER BY channel_post_id DESC, id DESC
        LIMIT ?
        OFFSET ?
        """,
            (int(channel_id), int(limit), int(offset)),
    ) as cur:
        return await cur.fetchall()


async def get_task_post_by_channel_post(
        db: aiosqlite.Connection,
        *,
        channel_id: int,
        channel_post_id: int,
):
    await ensure_task_posts_manual_schema(db)
    async with db.execute(
            """
        SELECT
            id,
            channel_id,
            channel_post_id,
            reward,
            required_views,
            current_views,
            is_active,
            source,
            added_by_admin_id,
            created_at,
            completed_at
        FROM task_posts
        WHERE channel_id = ?
          AND channel_post_id = ?
        LIMIT 1
        """,
            (int(channel_id), int(channel_post_id)),
    ) as cur:
        return await cur.fetchone()


async def auto_disable_task_channel_if_exhausted(
        db: aiosqlite.Connection,
        channel_id: int,
) -> bool:
    channel = await get_task_channel(db, int(channel_id))
    if not channel or int(channel["is_active"] or 0) != 1:
        return False

    client_remaining = int(channel["remaining_views"] or 0)
    partner_remaining = await get_task_channel_partner_remaining_views(db, channel)
    if client_remaining + partner_remaining > 0:
        return False

    cur = await db.execute(
        """
        UPDATE task_channels
        SET is_active = 0
        WHERE id = ?
          AND is_active = 1
        """,
        (int(channel_id),),
    )
    return cur.rowcount == 1


async def allocate_task_post_from_channel_post(
        db: aiosqlite.Connection,
        chat_id: str,
        channel_post_id: int,
        title: Optional[str] = None,
        reward: float = 0.01,
        source: str = "auto",
        added_by_admin_id: Optional[int] = None,
) -> bool:
    await ensure_task_posts_manual_schema(db)
    channel = await get_task_channel_by_chat_id(db, chat_id)
    if not channel:
        return False

    if int(channel["is_active"] or 0) != 1:
        return False

    client_remaining = int(channel["remaining_views"] or 0)
    partner_remaining = await get_task_channel_partner_remaining_views(db, channel)
    remaining = client_remaining + partner_remaining
    client_views_per_post = int(channel["views_per_post"] or 0)
    client_view_seconds = int(channel["view_seconds"] or 0)
    partner_views_per_post = int(channel["partner_views_per_post"] or 0) or client_views_per_post
    partner_view_seconds = int(channel["partner_view_seconds"] or 0) or client_view_seconds
    use_partner_pool = partner_remaining > 0
    views_per_post = partner_views_per_post if use_partner_pool else client_views_per_post
    hold_seconds = partner_view_seconds if use_partner_pool else client_view_seconds

    if remaining <= 0 or views_per_post <= 0:
        await auto_disable_task_channel_if_exhausted(db, int(channel["id"]))
        return False

    alloc = min(remaining, views_per_post)
    if alloc <= 0:
        await auto_disable_task_channel_if_exhausted(db, int(channel["id"]))
        return False

    cur = await db.execute(
        """
        INSERT OR IGNORE INTO task_posts (
            channel_id, channel_post_id, reward, required_views, current_views, is_active,
            source, added_by_admin_id, hold_seconds, created_at
        )
        VALUES (?, ?, ?, ?, 0, 1, ?, ?, ?, datetime('now'))
        """,
        (
            int(channel["id"]),
            int(channel_post_id),
            float(reward),
            int(alloc),
            source,
            int(added_by_admin_id) if added_by_admin_id is not None else None,
            int(hold_seconds),
        ),
    )

    if cur.rowcount != 1:
        return False

    partner_alloc = min(partner_remaining, int(alloc))
    client_alloc = max(int(alloc) - int(partner_alloc), 0)
    if partner_alloc > 0 and channel["client_user_id"] is not None:
        await allocate_partner_views(
            db,
            partner_user_id=int(channel["client_user_id"]),
            channel_chat_id=str(channel["chat_id"]),
            amount=int(partner_alloc),
        )

    if client_alloc > 0:
        await db.execute(
            """
            UPDATE task_channels
            SET
                allocated_views = allocated_views + ?,
                title = COALESCE(?, title)
            WHERE id = ?
            """,
            (int(client_alloc), title, int(channel["id"])),
        )
    else:
        await db.execute(
            """
            UPDATE task_channels
            SET title = COALESCE(?, title)
            WHERE id = ?
            """,
            (title, int(channel["id"])),
        )

    await auto_disable_task_channel_if_exhausted(db, int(channel["id"]))
    return True
