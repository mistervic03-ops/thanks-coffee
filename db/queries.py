import hashlib
import os
import psycopg2
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from config import DATABASE_URL
from logger import get_logger


KST = ZoneInfo("Asia/Seoul")
logger = get_logger(__name__)
_connections = []
_connections_lock = threading.Lock()


def get_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
    except Exception as exc:
        logger.error("", extra={"event": "db_connection_failed", "detail": str(exc)})
        raise

    with _connections_lock:
        _connections.append(conn)
    return conn


def close_connection():
    with _connections_lock:
        connections = list(_connections)
        _connections.clear()

    for conn in connections:
        if getattr(conn, "closed", False):
            continue
        conn.close()


def init_db():
    """migrations 디렉터리의 SQL 파일을 이름순으로 한 번씩 실행한다."""
    migration_dir = os.path.join(os.path.dirname(__file__), "migrations")
    migration_paths = [
        os.path.join(migration_dir, filename)
        for filename in sorted(os.listdir(migration_dir))
        if filename.endswith(".sql")
    ]
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename   TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            for migration_path in migration_paths:
                filename = os.path.basename(migration_path)
                cur.execute(
                    """
                    SELECT 1
                    FROM schema_migrations
                    WHERE filename = %s
                    """,
                    (filename,),
                )
                if cur.fetchone():
                    continue

                try:
                    with open(migration_path, "r") as f:
                        cur.execute(f.read())
                    cur.execute(
                        """
                        INSERT INTO schema_migrations (filename)
                        VALUES (%s)
                        """,
                        (filename,),
                    )
                except Exception as exc:
                    logger.error(
                        "",
                        extra={
                            "event": "migration_failed",
                            "detail": f"{filename}: {exc}",
                        },
                    )
                    raise

                logger.info("", extra={"event": "migration_applied", "detail": filename})
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
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


def lock_daily_limit(conn, sender_id):
    today = datetime.now(KST).date().isoformat()
    lock_key = _daily_limit_lock_key(sender_id, today)
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))


def _daily_limit_lock_key(sender_id, kst_date):
    digest = hashlib.blake2b(
        f"daily-limit:{sender_id}:{kst_date}".encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


def _summary_lock_key(summary_type):
    digest = hashlib.blake2b(
        f"summary-scheduler:{summary_type}".encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


def try_summary_lock(conn, summary_type):
    lock_key = _summary_lock_key(summary_type)
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
        return cur.fetchone()[0]


def release_summary_lock(conn, summary_type):
    lock_key = _summary_lock_key(summary_type)
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))


def get_recognition_by_idempotency_key(conn, idempotency_key):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                receiver_id,
                message,
                unit_count,
                feed_post_status
            FROM recognition
            WHERE idempotency_key = %s
            """,
            (idempotency_key,),
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "receiver_id": row[1],
        "message": row[2],
        "unit_count": row[3],
        "feed_post_status": row[4],
    }


def insert_recognition(
    conn,
    sender_id,
    receiver_id,
    message,
    unit_count,
    source_channel_id,
    idempotency_key,
):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO recognition (
                sender_id,
                receiver_id,
                message,
                unit_count,
                source_channel_id,
                idempotency_key
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (
                sender_id,
                receiver_id,
                message,
                unit_count,
                source_channel_id,
                idempotency_key,
            ),
        )
        row = cur.fetchone()
        return row[0] if row else None


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


def get_recent_received_recognitions(conn, receiver_id, limit=10):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sender_id, message, unit_count, created_at
            FROM recognition
            WHERE receiver_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (receiver_id, limit),
        )
        return [
            {
                "sender_id": sender_id,
                "message": message,
                "unit_count": unit_count,
                "created_at": created_at,
            }
            for sender_id, message, unit_count, created_at in cur.fetchall()
        ]


def get_recent_sent_recognitions(conn, sender_id, limit=10):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT receiver_id, message, unit_count, created_at
            FROM recognition
            WHERE sender_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (sender_id, limit),
        )
        return [
            {
                "receiver_id": receiver_id,
                "message": message,
                "unit_count": unit_count,
                "created_at": created_at,
            }
            for receiver_id, message, unit_count, created_at in cur.fetchall()
        ]


def get_personal_recognition_summary(conn, user_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COALESCE(SUM(unit_count) FILTER (
                    WHERE receiver_id = %s
                      AND (created_at AT TIME ZONE 'Asia/Seoul')::date
                          BETWEEN date_trunc('week', now() AT TIME ZONE 'Asia/Seoul')::date
                          AND (now() AT TIME ZONE 'Asia/Seoul')::date
                ), 0) AS received_week,
                COALESCE(SUM(unit_count) FILTER (
                    WHERE receiver_id = %s
                      AND (created_at AT TIME ZONE 'Asia/Seoul')::date
                          BETWEEN date_trunc('month', now() AT TIME ZONE 'Asia/Seoul')::date
                          AND (now() AT TIME ZONE 'Asia/Seoul')::date
                ), 0) AS received_month,
                COALESCE(SUM(unit_count) FILTER (
                    WHERE receiver_id = %s
                ), 0) AS received_total,
                COALESCE(SUM(unit_count) FILTER (
                    WHERE sender_id = %s
                      AND (created_at AT TIME ZONE 'Asia/Seoul')::date
                          BETWEEN date_trunc('week', now() AT TIME ZONE 'Asia/Seoul')::date
                          AND (now() AT TIME ZONE 'Asia/Seoul')::date
                ), 0) AS sent_week,
                COALESCE(SUM(unit_count) FILTER (
                    WHERE sender_id = %s
                      AND (created_at AT TIME ZONE 'Asia/Seoul')::date
                          BETWEEN date_trunc('month', now() AT TIME ZONE 'Asia/Seoul')::date
                          AND (now() AT TIME ZONE 'Asia/Seoul')::date
                ), 0) AS sent_month,
                COALESCE(SUM(unit_count) FILTER (
                    WHERE sender_id = %s
                ), 0) AS sent_total
            FROM recognition
            WHERE sender_id = %s OR receiver_id = %s
            """,
            (user_id, user_id, user_id, user_id, user_id, user_id, user_id, user_id),
        )
        row = cur.fetchone()

    return {
        "received_week": row[0],
        "received_month": row[1],
        "received_total": row[2],
        "sent_week": row[3],
        "sent_month": row[4],
        "sent_total": row[5],
    }


def update_feed_ts(conn, recognition_id, feed_channel_id, feed_message_ts):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE recognition
            SET feed_channel_id = %s,
                feed_message_ts = %s,
                feed_post_status = 'posted',
                feed_posted_at = now()
            WHERE id = %s
            """,
            (feed_channel_id, feed_message_ts, recognition_id),
        )


def update_feed_status(conn, recognition_id, feed_post_status):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE recognition
            SET feed_post_status = %s
            WHERE id = %s
            """,
            (feed_post_status, recognition_id),
        )


def get_failed_feed_records(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                sender_id,
                receiver_id,
                message,
                unit_count,
                retry_count
            FROM recognition
            WHERE feed_post_status = 'failed'
              AND retry_count < 3
            ORDER BY created_at ASC, id ASC
            """
        )
        return [
            {
                "id": recognition_id,
                "sender_id": sender_id,
                "receiver_id": receiver_id,
                "message": message,
                "unit_count": unit_count,
                "retry_count": retry_count,
            }
            for recognition_id, sender_id, receiver_id, message, unit_count, retry_count
            in cur.fetchall()
        ]


def mark_feed_posted(conn, recognition_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE recognition
            SET feed_post_status = 'posted',
                feed_posted_at = now()
            WHERE id = %s
            """,
            (recognition_id,),
        )


def increment_retry_count(conn, recognition_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE recognition
            SET retry_count = retry_count + 1,
                feed_post_status = CASE
                    WHEN retry_count + 1 >= 3 THEN 'abandoned'
                    ELSE 'failed'
                END
            WHERE id = %s
            RETURNING retry_count, feed_post_status
            """,
            (recognition_id,),
        )
        retry_count, feed_post_status = cur.fetchone()

    return {
        "retry_count": retry_count,
        "feed_post_status": feed_post_status,
    }


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
