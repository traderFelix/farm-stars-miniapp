import aiosqlite, uuid

from contextlib import asynccontextmanager


def normalize_daily_cycle_day(cycle_day: int) -> int:
    if cycle_day <= 0:
        return 1
    return ((cycle_day - 1) % 30) + 1


def daily_checkin_reward(cycle_day: int) -> float:
    cycle_day = normalize_daily_cycle_day(cycle_day)
    return round(cycle_day * 0.05, 2)


@asynccontextmanager
async def tx(db: aiosqlite.Connection, immediate: bool = True):
    if getattr(db, "in_transaction", False):
        sp_name = f"sp_{uuid.uuid4().hex}"
        await db.execute(f'SAVEPOINT "{sp_name}"')
        try:
            yield
            await db.execute(f'RELEASE SAVEPOINT "{sp_name}"')
        except Exception:
            await db.execute(f'ROLLBACK TO SAVEPOINT "{sp_name}"')
            await db.execute(f'RELEASE SAVEPOINT "{sp_name}"')
            raise
    else:
        async with db._tx_lock:  # type: ignore[attr-defined]
            await db.execute("BEGIN IMMEDIATE;" if immediate else "BEGIN;")
            try:
                yield
                await db.commit()
            except Exception:
                await db.rollback()
                raise