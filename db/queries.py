import psycopg2
from config import DATABASE_URL


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """001_init.sql을 실행해 테이블을 생성한다."""
    import os
    migration_path = os.path.join(os.path.dirname(__file__), "migrations", "001_init.sql")
    with open(migration_path, "r") as f:
        sql = f.read()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print("DB initialized.")
    finally:
        conn.close()


def get_sent_today(conn, sender_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(unit_count), 0)
            FROM recognition
            WHERE sender_id = %s
              AND (created_at AT TIME ZONE 'Asia/Seoul')::date =
                  (now() AT TIME ZONE 'Asia/Seoul')::date
            """,
            (sender_id,),
        )
        return cur.fetchone()[0]


def insert_recognition(conn, sender_id, receiver_id, message, unit_count, source_channel_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO recognition (
                sender_id,
                receiver_id,
                message,
                unit_count,
                source_channel_id
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (sender_id, receiver_id, message, unit_count, source_channel_id),
        )
        return cur.fetchone()[0]


def get_total_received(conn, receiver_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(unit_count), 0)
            FROM recognition
            WHERE receiver_id = %s
            """,
            (receiver_id,),
        )
        return cur.fetchone()[0]


def update_feed_ts(conn, recognition_id, feed_channel_id, feed_message_ts):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE recognition
            SET feed_channel_id = %s,
                feed_message_ts = %s
            WHERE id = %s
            """,
            (feed_channel_id, feed_message_ts, recognition_id),
        )
