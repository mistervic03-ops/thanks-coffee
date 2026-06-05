import psycopg2
from datetime import date, timedelta
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


def get_weekly_stats(conn, start_date, end_date):
    return _get_stats_for_dates(conn, start_date, end_date)


def get_monthly_stats(conn, year, month):
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)

    stats = _get_stats_for_dates(conn, start_date, end_date)
    stats["year"] = year
    stats["month"] = month
    return stats


def _get_stats_for_dates(conn, start_date, end_date):
    date_filter = """
        (created_at AT TIME ZONE 'Asia/Seoul')::date BETWEEN %s AND %s
    """
    params = (start_date, end_date)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM recognition
            WHERE {date_filter}
            """,
            params,
        )
        total_recognitions = cur.fetchone()[0]

        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT sender_id AS user_id
                FROM recognition
                WHERE {date_filter}
                UNION
                SELECT receiver_id AS user_id
                FROM recognition
                WHERE {date_filter}
            ) participants
            """,
            params + params,
        )
        participant_count = cur.fetchone()[0]

        cur.execute(
            f"""
            SELECT receiver_id, SUM(unit_count), COUNT(*)
            FROM recognition
            WHERE {date_filter}
            GROUP BY receiver_id
            ORDER BY SUM(unit_count) DESC, COUNT(*) DESC
            LIMIT 3
            """,
            params,
        )
        top_receivers = [
            {
                "user_id": user_id,
                "unit_count": unit_count,
                "recognition_count": recognition_count,
            }
            for user_id, unit_count, recognition_count in cur.fetchall()
        ]

        cur.execute(
            f"""
            SELECT sender_id, SUM(unit_count), COUNT(*)
            FROM recognition
            WHERE {date_filter}
            GROUP BY sender_id
            ORDER BY SUM(unit_count) DESC, COUNT(*) DESC
            LIMIT 3
            """,
            params,
        )
        top_senders = [
            {
                "user_id": user_id,
                "unit_count": unit_count,
                "recognition_count": recognition_count,
            }
            for user_id, unit_count, recognition_count in cur.fetchall()
        ]

    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_recognitions": total_recognitions,
        "participant_count": participant_count,
        "top_receivers": top_receivers,
        "top_senders": top_senders,
    }
