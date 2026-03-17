import sqlite3

DB_PATH = "/Users/vadym/telegram/felix-farm-stars-bot/bot.db"


def fetch_user_by_id(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT user_id, username, balance
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cur.fetchone()
        return row
    finally:
        conn.close()
