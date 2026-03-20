from typing import Optional

import aiosqlite


async def count_available_view_post_tasks_for_user(
        db: aiosqlite.Connection,
        user_id: int,
) -> int:
    async with db.execute(
            """
        SELECT COUNT(*)
        FROM task_posts p
        WHERE p.is_active = 1
          AND p.current_views < p.required_views
          AND NOT EXISTS (
              SELECT 1
              FROM task_post_views v
              WHERE v.user_id = ?
                AND v.task_post_id = p.id
          )
        """,
            (int(user_id),),
    ) as cur:
        row = await cur.fetchone()
        return int(row[0] or 0)


async def get_next_view_post_task_for_user(
        db: aiosqlite.Connection,
        user_id: int,
):
    async with db.execute(
            """
        SELECT
            p.id,
            p.channel_id,
            c.chat_id,
            c.title AS channel_title,
            c.view_seconds,
            p.channel_post_id,
            p.reward,
            p.required_views,
            p.current_views,
            p.created_at
        FROM task_posts p
        JOIN task_channels c ON c.id = p.channel_id
        WHERE p.is_active = 1
          AND p.current_views < p.required_views
          AND NOT EXISTS (
              SELECT 1
              FROM task_post_views v
              WHERE v.user_id = ?
                AND v.task_post_id = p.id
          )
        ORDER BY datetime(p.created_at) ASC, p.id ASC
        LIMIT 1
        """,
            (int(user_id),),
    ) as cur:
        return await cur.fetchone()


async def get_view_post_task_for_user(
        db: aiosqlite.Connection,
        user_id: int,
        task_post_id: int,
):
    async with db.execute(
            """
        SELECT
            p.id,
            p.channel_id,
            c.chat_id,
            c.title AS channel_title,
            c.view_seconds,
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


async def add_task_post_view(db, user_id: int, task_post_id: int, reward: float) -> bool:
    cursor = await db.execute(
        """
        INSERT OR IGNORE INTO task_post_views (user_id, task_post_id, reward)
        VALUES (?, ?, ?)
        """,
        (int(user_id), int(task_post_id), float(reward)),
    )
    return cursor.rowcount == 1


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


async def list_task_channels(db: aiosqlite.Connection):
    async with db.execute(
            """
        SELECT
            id,
            chat_id,
            COALESCE(title, '') AS title,
            is_active,
            total_bought_views,
            views_per_post,
            view_seconds,
            allocated_views,
            (total_bought_views - allocated_views) AS remaining_views,
            created_at
        FROM task_channels
        ORDER BY id DESC
        """
    ) as cur:
        return await cur.fetchall()


async def get_task_channel(db: aiosqlite.Connection, channel_id: int):
    async with db.execute(
            """
        SELECT
            id,
            chat_id,
            COALESCE(title, '') AS title,
            is_active,
            total_bought_views,
            views_per_post,
            view_seconds,
            allocated_views,
            (total_bought_views - allocated_views) AS remaining_views,
            created_at
        FROM task_channels
        WHERE id = ?
        LIMIT 1
        """,
            (int(channel_id),),
    ) as cur:
        return await cur.fetchone()


async def get_task_channel_by_chat_id(db: aiosqlite.Connection, chat_id: str):
    async with db.execute(
            """
        SELECT
            id,
            chat_id,
            COALESCE(title, '') AS title,
            is_active,
            total_bought_views,
            views_per_post,
            view_seconds,
            allocated_views,
            (total_bought_views - allocated_views) AS remaining_views,
            created_at
        FROM task_channels
        WHERE chat_id = ?
        LIMIT 1
        """,
            (str(chat_id),),
    ) as cur:
        return await cur.fetchone()


async def create_task_channel(
        db: aiosqlite.Connection,
        chat_id: str,
        title: Optional[str],
        total_bought_views: int,
        views_per_post: int,
        view_seconds: int,
) -> int:
    cur = await db.execute(
        """
        INSERT INTO task_channels (
            chat_id, title, is_active, total_bought_views, views_per_post, view_seconds, allocated_views, created_at
        )
        VALUES (?, ?, 1, ?, ?, ?, 0, datetime('now'))
        """,
        (
            str(chat_id),
            title,
            int(total_bought_views),
            int(views_per_post),
            int(view_seconds),
        ),
    )
    return int(cur.lastrowid)


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


async def list_task_posts_by_channel(db: aiosqlite.Connection, channel_id: int, limit: int = 20):
    async with db.execute(
            """
        SELECT
            id,
            channel_post_id,
            required_views,
            current_views,
            is_active,
            created_at,
            completed_at
        FROM task_posts
        WHERE channel_id = ?
        ORDER BY channel_post_id DESC, id DESC
        LIMIT ?
        """,
            (int(channel_id), int(limit)),
    ) as cur:
        return await cur.fetchall()


async def auto_disable_task_channel_if_exhausted(
        db: aiosqlite.Connection,
        channel_id: int,
) -> bool:
    cur = await db.execute(
        """
        UPDATE task_channels
        SET is_active = 0
        WHERE id = ?
          AND is_active = 1
          AND allocated_views >= total_bought_views
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
) -> bool:
    channel = await get_task_channel_by_chat_id(db, chat_id)
    if not channel:
        return False

    if int(channel["is_active"] or 0) != 1:
        return False

    remaining = int(channel["remaining_views"] or 0)
    views_per_post = int(channel["views_per_post"] or 0)

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
            channel_id, channel_post_id, reward, required_views, current_views, is_active, created_at
        )
        VALUES (?, ?, ?, ?, 0, 1, datetime('now'))
        """,
        (
            int(channel["id"]),
            int(channel_post_id),
            float(reward),
            int(alloc),
        ),
    )

    if cur.rowcount != 1:
        return False

    await db.execute(
        """
        UPDATE task_channels
        SET
            allocated_views = allocated_views + ?,
            title = COALESCE(?, title)
        WHERE id = ?
        """,
        (int(alloc), title, int(channel["id"])),
    )

    await auto_disable_task_channel_if_exhausted(db, int(channel["id"]))
    return True