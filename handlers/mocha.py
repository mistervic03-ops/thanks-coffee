from slack_sdk.errors import SlackApiError

from db.queries import (
    delete_recognition,
    get_connection,
    get_recognition_by_id,
    release_connection,
)
from lifecycle import tracked_handler
from logger import get_logger
from services.admin import is_admin
from services.feed import post_summary
from services.stats import (
    build_current_month_summary,
    build_monthly_summary,
    build_weekly_summary,
    get_current_month_range,
    get_previous_month,
    get_previous_week_range,
    load_monthly_stats,
    load_weekly_stats,
)


logger = get_logger(__name__)


def post_ephemeral(client, body, text):
    client.chat_postEphemeral(
        channel=body["channel_id"],
        user=body["user_id"],
        text=text,
    )


def register(app):
    @app.command("/mocha")
    @tracked_handler
    def handle_mocha(ack, body, client):
        ack()

        if not is_admin(body["user_id"]):
            post_ephemeral(client, body, "이 커맨드는 관리자만 사용할 수 있습니다.")
            return

        parts = (body.get("text") or "").strip().lower().split()
        if parts and parts[0] == "delete":
            handle_delete_command(client, body, parts)
            return
        if parts and parts[0] == "summary":
            handle_summary_command(client, body, parts[1:])
            return

        post_ephemeral(client, body, build_mocha_help())


def build_mocha_help():
    return "\n".join(
        [
            "사용 가능한 명령어:",
            "- /mocha delete {id} — recognition 삭제",
            "- /mocha summary weekly — 주간 요약 게시",
            "- /mocha summary monthly — 월간 요약 게시",
            "- /mocha summary weekly preview — 주간 요약 미리보기",
            "- /mocha summary monthly preview — 월간 요약 미리보기",
            "- /mocha summary this-month preview — 이번 달 요약 미리보기",
        ]
    )


def handle_summary_command(client, body, parts):
    summary_type = parts[0] if parts else ""
    preview = len(parts) == 2 and parts[1] == "preview"
    this_month_preview = parts == ["this-month", "preview"]
    valid_summary = summary_type in {"weekly", "monthly"} and (
        len(parts) == 1 or preview
    )
    if not valid_summary and not this_month_preview:
        post_ephemeral(client, body, build_mocha_help())
        return

    try:
        summary_text = _build_summary_text(summary_type)
        if preview:
            post_ephemeral(client, body, summary_text)
            return

        feed_message_ts = post_summary(client, summary_text)
    except Exception as exc:
        logger.warning(
            "",
            extra={
                "event": _feed_failure_event(exc),
                "user_id": body["user_id"],
                "detail": _exception_detail(exc),
            },
        )
        post_ephemeral(
            client,
            body,
            "❌ 요약을 게시하지 못했어요. 앱 로그와 feed 채널 설정을 확인해주세요.",
        )
        return

    if feed_message_ts:
        logger.info(
            "",
            extra={
                "event": "summary_posted",
                "user_id": body["user_id"],
                "detail": summary_type,
            },
        )
        post_ephemeral(client, body, "✅ 모카 감사 요약을 feed 채널에 올렸어요.")
    else:
        post_ephemeral(
            client,
            body,
            "✅ 모카 감사 요약을 만들었어요. FEED_ENABLED=false라 feed 채널에는 올리지 않았어요.",
        )


def handle_delete_command(client, body, parts):
    if len(parts) != 2 or not parts[1].isdigit():
        post_ephemeral(client, body, "올바른 recognition ID를 입력해주세요.")
        return

    recognition_id = int(parts[1])
    recognition = _delete_recognition_from_db(recognition_id)
    if not recognition:
        post_ephemeral(client, body, "해당 recognition을 찾을 수 없습니다.")
        return

    feed_deleted = _delete_feed_message(client, recognition)
    if feed_deleted:
        post_ephemeral(
            client,
            body,
            f"recognition #{recognition_id}와 feed 메시지를 삭제했습니다.",
        )
    else:
        post_ephemeral(
            client,
            body,
            f"recognition #{recognition_id}를 삭제했습니다. (feed 메시지 삭제 실패)",
        )


def _delete_recognition_from_db(recognition_id):
    conn = get_connection()
    try:
        recognition = get_recognition_by_id(conn, recognition_id)
        if not recognition:
            return None

        delete_recognition(conn, recognition_id)
        conn.commit()
        logger.info(
            "",
            extra={"event": "recognition_deleted", "detail": str(recognition_id)},
        )
        return recognition
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)


def _delete_feed_message(client, recognition):
    if not recognition.get("feed_channel_id") or not recognition.get("feed_message_ts"):
        return False

    try:
        client.chat_delete(
            channel=recognition["feed_channel_id"],
            ts=recognition["feed_message_ts"],
        )
    except Exception as exc:
        logger.warning(
            "",
            extra={
                "event": "feed_delete_failed",
                "detail": f"{recognition['id']}: {_exception_detail(exc)}",
            },
        )
        return False

    return True


def _build_summary_text(summary_type):
    conn = get_connection()
    try:
        if summary_type == "weekly":
            start_date, end_date = get_previous_week_range()
            stats = load_weekly_stats(conn, start_date, end_date)
            return build_weekly_summary(stats)

        if summary_type == "this-month":
            start_date, end_date = get_current_month_range()
            stats = load_weekly_stats(conn, start_date, end_date)
            return build_current_month_summary(stats)

        year, month = get_previous_month()
        stats = load_monthly_stats(conn, year, month)
        return build_monthly_summary(stats)
    finally:
        release_connection(conn)


def _feed_failure_event(exc):
    if _is_slack_rate_limited(exc):
        return "slack_rate_limited"

    return "feed_post_failed"


def _is_slack_rate_limited(exc):
    if not isinstance(exc, SlackApiError):
        return False

    return exc.response.status_code == 429 or exc.response.get("error") == "ratelimited"


def _exception_detail(exc):
    if isinstance(exc, SlackApiError):
        return exc.response.get("error") or str(exc)

    return str(exc)
