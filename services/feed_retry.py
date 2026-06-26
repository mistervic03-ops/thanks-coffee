from config import FEED_CHANNEL_ID, FEED_ENABLED
from db.queries import (
    get_connection,
    get_failed_feed_records,
    get_total_received,
    increment_retry_count,
    mark_feed_posted,
)
from logger import get_logger
from services.feed import build_feed_text


logger = get_logger(__name__)


def retry_failed_feeds(app):
    if not FEED_ENABLED:
        return

    conn = get_connection()
    try:
        records = get_failed_feed_records(conn)
        if not records:
            return

        for record in records:
            try:
                total_received = get_total_received(conn, record["receiver_id"])
                app.client.chat_postMessage(
                    channel=FEED_CHANNEL_ID,
                    text=build_feed_text(
                        sender_id=record["sender_id"],
                        receiver_id=record["receiver_id"],
                        message=record["message"],
                        total_received=total_received,
                    ),
                )
                mark_feed_posted(conn, record["id"])
                conn.commit()
                logger.info(
                    "",
                    extra={
                        "event": "feed_retry_succeeded",
                        "user_id": record["sender_id"],
                    },
                )
            except Exception:
                conn.rollback()
                result = increment_retry_count(conn, record["id"])
                conn.commit()
                if result["feed_post_status"] == "abandoned":
                    logger.warning(
                        "",
                        extra={
                            "event": "feed_abandoned",
                            "user_id": record["sender_id"],
                        },
                    )
                else:
                    logger.warning(
                        "",
                        extra={
                            "event": "feed_retry_failed",
                            "user_id": record["sender_id"],
                            "detail": f"retry_count={result['retry_count']}",
                        },
                    )
    finally:
        conn.close()
