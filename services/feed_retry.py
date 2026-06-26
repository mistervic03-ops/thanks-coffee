from slack_sdk.errors import SlackApiError

from config import ANNOUNCEMENT_CHANNEL_ID, FEED_ENABLED
from db.queries import (
    get_connection,
    get_failed_feed_records,
    get_total_received,
    increment_retry_count,
    mark_feed_posted,
    release_connection,
)
from logger import get_logger
from services.admin import notify_admins
from services.feed import build_feed_blocks, build_feed_fallback_text


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
                    channel=ANNOUNCEMENT_CHANNEL_ID,
                    text=build_feed_fallback_text(
                        record["sender_id"],
                        record["receiver_id"],
                    ),
                    blocks=build_feed_blocks(
                        sender_id=record["sender_id"],
                        receiver_id=record["receiver_id"],
                        message=record["message"],
                        total_received=total_received,
                        recognition_id=record["id"],
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
            except Exception as exc:
                conn.rollback()
                result = increment_retry_count(conn, record["id"])
                conn.commit()
                if result["feed_post_status"] == "abandoned":
                    notify_admins(
                        app.client,
                        "[mocha] feed 게시가 3회 재시도 후 포기되었습니다. "
                        f"recognition_id: {record['id']}",
                    )
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
                            "event": _feed_retry_failure_event(exc),
                            "user_id": record["sender_id"],
                            "detail": _feed_retry_failure_detail(record, result, exc),
                        },
                    )
    finally:
        release_connection(conn)


def _feed_retry_failure_event(exc):
    if _is_slack_rate_limited(exc):
        return "slack_rate_limited"

    return "feed_retry_failed"


def _feed_retry_failure_detail(record, result, exc):
    if _is_slack_rate_limited(exc):
        return f"feed retry rate limited, recognition_id: {record['id']}"

    return f"retry_count={result['retry_count']}"


def _is_slack_rate_limited(exc):
    if not isinstance(exc, SlackApiError):
        return False

    return exc.response.status_code == 429 or exc.response.get("error") == "ratelimited"
