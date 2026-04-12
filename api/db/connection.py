import asyncio

import aiosqlite

from shared.config import DB_PATH


async def get_db():
    db = await aiosqlite.connect(
        DB_PATH,
        timeout=30,
        isolation_level=None,
    )
    db.row_factory = aiosqlite.Row

    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA synchronous=NORMAL;")
    await db.execute("PRAGMA foreign_keys=ON;")
    await db.execute("PRAGMA busy_timeout=30000;")

    db._tx_lock = asyncio.Lock()
    return db
