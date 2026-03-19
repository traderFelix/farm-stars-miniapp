import aiosqlite


async def count_available_task_posts_for_user(
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


async def add_task_post_view(
        db: aiosqlite.Connection,
        user_id: int,
        task_post_id: int,
        reward: float,
) -> bool:
    cur = await db.execute(
        """
        INSERT OR IGNORE INTO task_post_views (user_id, task_post_id, reward, viewed_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        (int(user_id), int(task_post_id), float(reward)),
    )
    return cur.rowcount == 1


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
        """,
        (int(task_post_id),),
    )
    return cur.rowcount == 1