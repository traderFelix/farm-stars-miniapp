import aiosqlite, asyncio, logging

from typing import Optional, List, Tuple
from shared.config import DB_PATH

from shared.db.common import tx
from shared.db.ledger import apply_balance_delta
from shared.db.users import (
    register_user, get_balance, ensure_users_role_schema,
)

logger = logging.getLogger(__name__)


# ---------- Connection / TX ----------

async def open_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(
        DB_PATH,
        timeout=30,
        isolation_level=None,  # важно
    )
    db.row_factory = aiosqlite.Row

    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA synchronous=NORMAL;")
    await db.execute("PRAGMA foreign_keys=ON;")
    await db.execute("PRAGMA busy_timeout=30000;")

    db._tx_lock = asyncio.Lock()

    return db

async def close_db(db: aiosqlite.Connection) -> None:
    await db.close()


async def init_db(db: aiosqlite.Connection) -> None:
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          user_id INTEGER PRIMARY KEY,
          username TEXT,
          tg_first_name TEXT,
          tg_last_name TEXT,
          balance NUMERIC DEFAULT 0 CHECK(balance >= 0),
          is_suspicious INTEGER NOT NULL DEFAULT 0,
          suspicious_reason TEXT,
          referred_by INTEGER,
          is_banned INTEGER DEFAULT 0,
          role_level INTEGER NOT NULL DEFAULT 0,
          daily_checkin_cycle_day INTEGER NOT NULL DEFAULT 0,
          last_daily_checkin_at TEXT,
          created_at TEXT DEFAULT (datetime('now')),
          last_seen_at TEXT DEFAULT (datetime('now'))
        );
    
        CREATE TABLE IF NOT EXISTS campaigns (
          campaign_key TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          reward_amount NUMERIC NOT NULL,
          status TEXT DEFAULT 'draft',             -- draft | active | ended
          description TEXT,
          created_at TEXT DEFAULT (datetime('now')),
          starts_at TEXT,
          ends_at TEXT
        );
    
        CREATE TABLE IF NOT EXISTS claims (
          user_id INTEGER NOT NULL,
          campaign_key TEXT NOT NULL,
          amount NUMERIC NOT NULL,
          claimed_at TEXT DEFAULT (datetime('now')),
          status TEXT DEFAULT 'ok',
          PRIMARY KEY (user_id, campaign_key),
          FOREIGN KEY (user_id) REFERENCES users(user_id),
          FOREIGN KEY (campaign_key) REFERENCES campaigns(campaign_key)
        );
    
        CREATE TABLE IF NOT EXISTS campaign_winners (
          campaign_key TEXT NOT NULL,
          username TEXT NOT NULL,                 -- храним БЕЗ @
          user_id INTEGER,                        -- подтянем позже, когда победитель зайдет
          added_at TEXT DEFAULT (datetime('now')),
          added_by INTEGER,
          PRIMARY KEY (campaign_key, username),
          FOREIGN KEY (campaign_key) REFERENCES campaigns(campaign_key)
        );
    
        CREATE TABLE IF NOT EXISTS ledger (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          delta NUMERIC NOT NULL,
          reason TEXT NOT NULL,
          campaign_key TEXT,
          withdrawal_id INTEGER,
          meta TEXT,
          created_at TEXT DEFAULT (datetime('now')),
          FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
    
        CREATE TABLE IF NOT EXISTS withdrawals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          amount NUMERIC NOT NULL,
          method TEXT NOT NULL,                    -- 'ton' | 'stars'
          wallet TEXT,                            -- wallet address for TON
          status TEXT NOT NULL DEFAULT 'pending',  -- pending|paid|rejected
          created_at TEXT DEFAULT (datetime('now')),
          processed_at TEXT,
          processed_by INTEGER,
          fee_xtr INTEGER NOT NULL DEFAULT 0,
          fee_paid INTEGER NOT NULL DEFAULT 0,
          fee_refunded INTEGER NOT NULL DEFAULT 0,
          fee_telegram_charge_id TEXT,
          fee_invoice_payload TEXT,
          FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
    
        CREATE TABLE IF NOT EXISTS abuse_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          action TEXT NOT NULL,                       -- claim_click | claim_fail | withdraw_create
          amount NUMERIC DEFAULT 0,
          created_at TEXT DEFAULT (datetime('now'))
        );
        
        CREATE TABLE IF NOT EXISTS xtr_ledger (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          withdrawal_id INTEGER,
          delta_xtr INTEGER NOT NULL,                  -- + списали комиссию / - вернули комиссию
          reason TEXT NOT NULL,                        -- withdraw_fee_paid | withdraw_fee_refunded | admin_fee_refund
          telegram_payment_charge_id TEXT,
          invoice_payload TEXT,
          meta TEXT,
          created_at TEXT DEFAULT (datetime('now')),
          FOREIGN KEY (user_id) REFERENCES users(user_id),
          FOREIGN KEY (withdrawal_id) REFERENCES withdrawals(id)
        );
        
        CREATE TABLE IF NOT EXISTS task_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL UNIQUE,
            title TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            total_bought_views INTEGER NOT NULL DEFAULT 0,
            views_per_post INTEGER NOT NULL DEFAULT 0,
            view_seconds INTEGER NOT NULL DEFAULT 3,
            allocated_views INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        
        CREATE TABLE IF NOT EXISTS task_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            channel_post_id INTEGER NOT NULL,
            reward REAL NOT NULL DEFAULT 0.01,
            required_views INTEGER NOT NULL DEFAULT 0,
            current_views INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            UNIQUE(channel_id, channel_post_id),
            FOREIGN KEY (channel_id) REFERENCES task_channels(id)
        );
        
        CREATE TABLE IF NOT EXISTS task_post_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_post_id INTEGER NOT NULL,
            reward REAL NOT NULL,
            viewed_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, task_post_id),
            FOREIGN KEY (task_post_id) REFERENCES task_posts(id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);
        CREATE INDEX IF NOT EXISTS idx_users_last_seen_at ON users(last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_campaigns_status_created ON campaigns(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_claims_campaign_key ON claims(campaign_key);
        CREATE INDEX IF NOT EXISTS idx_winners_campaign_key ON campaign_winners(campaign_key);
        CREATE INDEX IF NOT EXISTS idx_ledger_withdrawal ON ledger(withdrawal_id);
        CREATE INDEX IF NOT EXISTS idx_ledger_created_id ON ledger(created_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_ledger_user_created_id ON ledger(user_id, created_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_withdrawals_status_created ON withdrawals(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_withdrawals_user_created ON withdrawals(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_abuse_events_user_action_time ON abuse_events(user_id, action, created_at);
        CREATE INDEX IF NOT EXISTS idx_xtr_ledger_reason_created ON xtr_ledger(reason, created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_xtr_ledger_unique_paid_charge ON xtr_ledger(reason, telegram_payment_charge_id)
          WHERE reason = 'withdraw_fee_paid' AND telegram_payment_charge_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_task_channels_active ON task_channels(is_active, created_at);
        CREATE INDEX IF NOT EXISTS idx_task_posts_queue ON task_posts(is_active, created_at, id);
        CREATE INDEX IF NOT EXISTS idx_task_post_views_user ON task_post_views(user_id, viewed_at);
        CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by);
    """)

    await ensure_users_role_schema(db)
    await db.commit()


async def ensure_user_registered(message_or_callback, db):
    user = message_or_callback.from_user
    async with tx(db, immediate=False):
        await register_user(
            db,
            user.id,
            user.username,
            user.first_name,
            user.last_name,
        )

# ---------- Campaigns ----------

async def upsert_campaign(
        db: aiosqlite.Connection,
        campaign_key: str,
        title: str,
        reward_amount: float,
        status: str = "draft",
        description: Optional[str] = None,
) -> None:
    await db.execute(
        """
        INSERT INTO campaigns (campaign_key, title, reward_amount, status, description)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(campaign_key) DO UPDATE SET
            title=excluded.title,
            reward_amount=excluded.reward_amount,
            status=excluded.status,
            description=excluded.description
        """,
        (campaign_key, title, float(reward_amount), status, description),
    )

async def set_campaign_status(db: aiosqlite.Connection, campaign_key: str, status: str) -> None:
    await db.execute(
        "UPDATE campaigns SET status = ? WHERE campaign_key = ?",
        (status, campaign_key),
    )

async def delete_campaign(db: aiosqlite.Connection, campaign_key: str) -> None:
    await db.execute("DELETE FROM claims WHERE campaign_key = ?", (campaign_key,))
    await db.execute("DELETE FROM campaign_winners WHERE campaign_key = ?", (campaign_key,))
    await db.execute("DELETE FROM campaigns WHERE campaign_key = ?", (campaign_key,))

async def get_campaign(db: aiosqlite.Connection, campaign_key: str):
    async with db.execute(
            "SELECT campaign_key, title, reward_amount, status FROM campaigns WHERE campaign_key = ?",
            (campaign_key,),
    ) as cur:
        return await cur.fetchone()

async def list_campaigns(db: aiosqlite.Connection):
    async with db.execute(
            """
        SELECT campaign_key, reward_amount, status, created_at
        FROM campaigns
        ORDER BY datetime(created_at) DESC
        """
    ) as cur:
        return await cur.fetchall()

async def list_campaigns_latest(db: aiosqlite.Connection, limit: int = 5):
    async with db.execute(
            """
        SELECT campaign_key, reward_amount, status, created_at
        FROM campaigns
        ORDER BY datetime(created_at) DESC
        LIMIT ?
        """,
            (int(limit),),
    ) as cur:
        return await cur.fetchall()

async def list_active_campaigns(db: aiosqlite.Connection):
    async with db.execute(
            """
        SELECT campaign_key, title, reward_amount
        FROM campaigns
        WHERE status = 'active'
        ORDER BY datetime(created_at) DESC
        """
    ) as cur:
        return await cur.fetchall()

async def campaigns_status_counts(db: aiosqlite.Connection) -> Tuple[int, int, int]:
    async with db.execute("SELECT status, COUNT(*) AS cnt FROM campaigns GROUP BY status") as cur:
        rows = await cur.fetchall()

    counts = {"active": 0, "ended": 0, "draft": 0}
    for r in rows:
        counts[str(r["status"])] = int(r["cnt"])

    return counts["active"], counts["ended"], counts["draft"]


# ---------- Winners ----------

async def add_winners(db: aiosqlite.Connection, campaign_key: str, usernames: List[str]) -> int:
    count = 0
    for u in usernames:
        u = (u or "").strip().lstrip("@")
        if not u:
            continue
        await db.execute(
            "INSERT OR IGNORE INTO campaign_winners (campaign_key, username) VALUES (?, ?)",
            (campaign_key, u),
        )
        count += 1
    return count

async def list_winners(db: aiosqlite.Connection, campaign_key: str) -> List[str]:
    async with db.execute(
            "SELECT username FROM campaign_winners WHERE campaign_key = ? ORDER BY added_at ASC",
            (campaign_key,),
    ) as cur:
        rows = await cur.fetchall()
    return [r["username"] for r in rows]

async def winners_count(db: aiosqlite.Connection, campaign_key: str) -> int:
    async with db.execute("SELECT COUNT(*) AS c FROM campaign_winners WHERE campaign_key = ?", (campaign_key,)) as cur:
        row = await cur.fetchone()
    return int(row["c"])

async def attach_winner_user_id(db: aiosqlite.Connection, campaign_key: str, username: str, user_id: int) -> None:
    u = (username or "").strip().lstrip("@")
    if not u:
        return
    await db.execute(
        """
        UPDATE campaign_winners
        SET user_id = ?
        WHERE campaign_key = ?
          AND username = ?
          AND user_id IS NULL
        """,
        (int(user_id), campaign_key, u),
    )

async def is_winner(db: aiosqlite.Connection, campaign_key: str, user_id: int, username: Optional[str]) -> bool:
    async with db.execute(
            "SELECT 1 FROM campaign_winners WHERE campaign_key = ? AND user_id = ? LIMIT 1",
            (campaign_key, int(user_id)),
    ) as cur:
        if await cur.fetchone() is not None:
            return True

    u = (username or "").strip().lstrip("@")
    if not u:
        return False

    async with db.execute(
            "SELECT 1 FROM campaign_winners WHERE campaign_key = ? AND username = ? LIMIT 1",
            (campaign_key, u),
    ) as cur:
        return await cur.fetchone() is not None

async def delete_winner_if_not_claimed(db: aiosqlite.Connection, campaign_key: str, username: str):
    u = (username or "").strip().lstrip("@")
    if not u:
        return False, "Пустой username"

    async with db.execute(
            "SELECT user_id FROM campaign_winners WHERE campaign_key = ? AND username = ?",
            (campaign_key, u),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return False, "Этого username нет в списке победителей"

    winner_user_id = row["user_id"]

    user_id_by_username = None
    if winner_user_id is None:
        async with db.execute("SELECT user_id FROM users WHERE username = ? LIMIT 1", (u,)) as cur:
            r2 = await cur.fetchone()
        if r2:
            user_id_by_username = r2["user_id"]

    async with db.execute(
            """
        SELECT 1
        FROM claims cl
        WHERE cl.campaign_key = ?
          AND (
            (? IS NOT NULL AND cl.user_id = ?)
            OR (? IS NOT NULL AND cl.user_id = ?)
          )
        LIMIT 1
        """,
            (campaign_key, winner_user_id, winner_user_id, user_id_by_username, user_id_by_username),
    ) as cur:
        if await cur.fetchone() is not None:
            return False, "Нельзя удалить: этот победитель уже заклеймил"

    await db.execute(
        "DELETE FROM campaign_winners WHERE campaign_key = ? AND username = ?",
        (campaign_key, u),
    )
    return True, "Удалено"


# ---------- Claims ----------

async def has_claim(db: aiosqlite.Connection, user_id: int, campaign_key: str) -> bool:
    async with db.execute(
            "SELECT 1 FROM claims WHERE user_id = ? AND campaign_key = ?",
            (int(user_id), campaign_key),
    ) as cur:
        return await cur.fetchone() is not None

async def add_claim(db: aiosqlite.Connection, user_id: int, campaign_key: str, amount: float) -> None:
    await db.execute(
        "INSERT INTO claims (user_id, campaign_key, amount) VALUES (?, ?, ?)",
        (int(user_id), campaign_key, float(amount)),
    )

async def claimed_usernames(db: aiosqlite.Connection, campaign_key: str) -> List[str]:
    async with db.execute(
            """
        SELECT u.username
        FROM claims c
        JOIN users u ON u.user_id = c.user_id
        WHERE c.campaign_key = ?
          AND u.username IS NOT NULL
          AND u.username != ''
        ORDER BY datetime(c.claimed_at) ASC
        """,
            (campaign_key,),
    ) as cur:
        rows = await cur.fetchall()
    return [r["username"] for r in rows]

async def campaign_stats(db: aiosqlite.Connection, campaign_key: str):
    async with db.execute(
            "SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total FROM claims WHERE campaign_key = ?",
            (campaign_key,),
    ) as cur:
        row = await cur.fetchone()
    claims_count = int(row["cnt"] or 0)
    total_paid = float(row["total"] or 0.0)

    async with db.execute("SELECT COUNT(*) AS c FROM campaign_winners WHERE campaign_key = ?", (campaign_key,)) as cur:
        r2 = await cur.fetchone()
    winners_cnt = int(r2["c"])

    return claims_count, winners_cnt, total_paid

async def global_claims_stats(db: aiosqlite.Connection):
    async with db.execute("SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total FROM claims") as cur:
        row = await cur.fetchone()
    return int(row["cnt"] or 0), float(row["total"] or 0.0)

async def claim_reward(
        db: aiosqlite.Connection,
        user_id: int,
        username: Optional[str],
        campaign_key: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
) -> tuple[bool, str, float]:

    uid = int(user_id)
    ck = (campaign_key or "").strip()

    async with tx(db, immediate=True):
        await register_user(db, uid, username, first_name, last_name)

        row = await get_campaign(db, ck)
        if not row:
            return False, "❌ Конкурс не найден", 0.0

        _k, title, reward_amount, status = row[0], row[1], float(row[2]), row[3]
        if status != "active":
            return False, "❌ Этот конкурс сейчас неактивен", 0.0

        if username:
            await attach_winner_user_id(db, ck, username, uid)

        ok_winner = await is_winner(db, ck, uid, username)
        if not ok_winner:
            return False, "❌ Ты не в списке победителей этого конкурса", 0.0

        try:
            await add_claim(db, uid, ck, reward_amount)
        except Exception:
            return False, "⚠️ Ты уже забрал награду в этом конкурсе", 0.0

        await apply_balance_delta(
            db,
            user_id=uid,
            delta=reward_amount,
            reason="contest_bonus",
            campaign_key=ck,
            meta=title,
        )

        new_balance = await get_balance(db, uid)
        return True, f"✅ Ты получил {reward_amount:g}⭐️ ({title})", float(new_balance)

# ---------- Totals for admin dashboard ----------

async def total_assigned_amount(db: aiosqlite.Connection) -> float:
    async with db.execute(
            """
        SELECT COALESCE(SUM(c.reward_amount), 0) AS total
        FROM campaign_winners w
        JOIN campaigns c ON c.campaign_key = w.campaign_key
        """
    ) as cur:
        row = await cur.fetchone()
    return float(row["total"] or 0.0)

async def unclaimed_total_amount(db: aiosqlite.Connection) -> float:
    async with db.execute(
            """
        SELECT COALESCE(SUM(c.reward_amount), 0) AS total
        FROM campaign_winners w
        JOIN campaigns c ON c.campaign_key = w.campaign_key
        LEFT JOIN users u ON u.username = w.username
        WHERE NOT EXISTS (
            SELECT 1
            FROM claims cl
            WHERE cl.campaign_key = w.campaign_key
              AND (
                (w.user_id IS NOT NULL AND cl.user_id = w.user_id)
                OR (w.user_id IS NULL AND u.user_id IS NOT NULL AND cl.user_id = u.user_id)
              )
        )
        """
    ) as cur:
        row = await cur.fetchone()
    return float(row["total"] or 0.0)


async def cleanup_abuse_events(db: aiosqlite.Connection) -> None:
    await db.execute("""
        DELETE FROM abuse_events
        WHERE datetime(created_at) < datetime('now', '-1 day')
    """)


async def log_abuse_event(db, user_id: int, action: str, amount: float = 0):
    await cleanup_abuse_events(db)

    await db.execute(
        """
        INSERT INTO abuse_events (user_id, action, amount)
        VALUES (?, ?, ?)
        """,
        (int(user_id), action, float(amount)),
    )


async def count_recent_abuse_events(
        db: aiosqlite.Connection,
        user_id: int,
        action: str,
        minutes: int,
) -> int:
    async with db.execute(
            """
        SELECT COUNT(*)
        FROM abuse_events
        WHERE user_id = ?
          AND action = ?
          AND datetime(created_at) >= datetime('now', ?)
        """,
            (int(user_id), action, f"-{int(minutes)} minutes"),
    ) as cur:
        row = await cur.fetchone()
        return int(row[0] or 0)


async def sum_recent_abuse_amount(
        db: aiosqlite.Connection,
        user_id: int,
        action: str,
        hours: int,
) -> float:
    async with db.execute(
            """
        SELECT COALESCE(SUM(amount), 0)
        FROM abuse_events
        WHERE user_id = ?
          AND action = ?
          AND datetime(created_at) >= datetime('now', ?)
        """,
            (int(user_id), action, f"-{int(hours)} hours"),
    ) as cur:
        row = await cur.fetchone()
        return float(row[0] or 0.0)


async def xtr_ledger_add(
        db: aiosqlite.Connection,
        user_id: int,
        delta_xtr: int,
        reason: str,
        withdrawal_id: Optional[int] = None,
        telegram_payment_charge_id: Optional[str] = None,
        invoice_payload: Optional[str] = None,
        meta: Optional[str] = None,
) -> None:
    await db.execute(
        """
        INSERT INTO xtr_ledger (
            user_id,
            withdrawal_id,
            delta_xtr,
            reason,
            telegram_payment_charge_id,
            invoice_payload,
            meta,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            int(user_id),
            int(withdrawal_id) if withdrawal_id is not None else None,
            int(delta_xtr),
            reason,
            telegram_payment_charge_id,
            invoice_payload,
            meta,
        ),
    )


async def xtr_ledger_sum(db: aiosqlite.Connection) -> int:
    async with db.execute(
            "SELECT COALESCE(SUM(delta_xtr), 0) AS s FROM xtr_ledger"
    ) as cur:
        row = await cur.fetchone()
        return int(row["s"] or 0)


async def xtr_ledger_sum_by_reason(db: aiosqlite.Connection, reason: str) -> int:
    async with db.execute(
            """
        SELECT COALESCE(SUM(delta_xtr), 0) AS s
        FROM xtr_ledger
        WHERE reason = ?
        """,
            (reason,),
    ) as cur:
        row = await cur.fetchone()
        return int(row["s"] or 0)
