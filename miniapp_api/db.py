import sqlite3

DB_PATH = "/Users/vadym/telegram/felix-farm-stars-bot/bot.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_user_by_id(user_id: int):
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT user_id, username, balance
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
