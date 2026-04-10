from typing import Union

import aiosqlite, uuid

from contextlib import asynccontextmanager

DAILY_CHECKIN_REWARDS = (
    0.20, 0.20, 0.20, 0.30, 0.30, 0.30, 1.00,
    0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 2.00,
    0.50, 0.50, 0.50, 0.50, 0.50, 0.50, 3.00,
    0.70, 0.70, 0.70, 0.80, 0.80, 0.80, 0.80, 0.80, 5.00,
)
DAILY_CHECKIN_BOOST_DAYS = {7, 14, 21}
DAILY_CHECKIN_JACKPOT_DAY = 30


def normalize_daily_cycle_day(cycle_day: int) -> int:
    if cycle_day <= 0:
        return 1
    return ((cycle_day - 1) % len(DAILY_CHECKIN_REWARDS)) + 1


def daily_checkin_season_length() -> int:
    return len(DAILY_CHECKIN_REWARDS)


def daily_checkin_reward(cycle_day: int) -> float:
    cycle_day = normalize_daily_cycle_day(cycle_day)
    return float(DAILY_CHECKIN_REWARDS[cycle_day - 1])


def daily_checkin_tier(cycle_day: int) -> str:
    cycle_day = normalize_daily_cycle_day(cycle_day)
    if cycle_day == DAILY_CHECKIN_JACKPOT_DAY:
        return "jackpot"
    if cycle_day in DAILY_CHECKIN_BOOST_DAYS:
        return "boost"
    return "standard"


def daily_checkin_schedule() -> list[dict[str, Union[float, int, str]]]:
    return [
        {
            "day": index,
            "reward": float(reward),
            "tier": daily_checkin_tier(index),
        }
        for index, reward in enumerate(DAILY_CHECKIN_REWARDS, start=1)
    ]


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
        await db.execute("BEGIN IMMEDIATE;" if immediate else "BEGIN;")
        try:
            yield
            await db.commit()
        except Exception:
            await db.rollback()
            raise
