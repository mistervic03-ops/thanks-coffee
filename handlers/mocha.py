from slack_sdk.errors import SlackApiError

from config import ANNOUNCEMENT_CHANNEL_ID
from db.queries import (
    delete_recognition,
    get_connection,
    get_recognition_by_id,
    release_connection,
)
from lifecycle import tracked_handler
from logger import get_logger
from services.admin import is_admin
from services.feed import build_summary_fallback_text, post_summary
from services.stats import (
    build_leaderboard_blocks,
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


def post_ephemeral(client, body, text, blocks=None):
    kwargs = {
        "channel": body["channel_id"],
        "user": body["user_id"],
        "text": text,
    }
    if blocks is not None:
        kwargs["blocks"] = blocks

    client.chat_postEphemeral(
        **kwargs,
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
        if parts == ["pin"]:
            handle_pin_command(client, body)
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
            "• /mocha pin — 채널에 봇 소개 메시지 게시 및 pin",
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
        summary_blocks, leaderboard_blocks = _build_summary_payload(summary_type)
        if preview:
            post_ephemeral(
                client,
                body,
                build_summary_fallback_text(summary_blocks),
                blocks=summary_blocks,
            )
            return

        feed_message_ts = post_summary(client, summary_blocks)
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
        post_ephemeral(
            client,
            body,
            "📋 관리자용 상세 현황",
            blocks=leaderboard_blocks,
        )
    else:
        post_ephemeral(
            client,
            body,
            "✅ 모카 감사 요약을 만들었어요. FEED_ENABLED=false라 feed 채널에는 올리지 않았어요.",
        )


def handle_pin_command(client, body):
    try:
        response = client.chat_postMessage(
            channel=ANNOUNCEMENT_CHANNEL_ID,
            text="☕ 모카(Mocha) 감사 봇입니다.",
            blocks=build_pin_intro_blocks(),
        )
    except Exception:
        logger.warning("", extra={"event": "pin_post_failed"})
        post_ephemeral(client, body, "소개 메시지 게시에 실패했습니다.")
        return

    try:
        client.pins_add(
            channel=ANNOUNCEMENT_CHANNEL_ID,
            timestamp=response["ts"],
        )
    except Exception as exc:
        logger.warning(
            "",
            extra={"event": "pin_failed", "detail": _exception_detail(exc)},
        )
        post_ephemeral(client, body, "메시지는 게시됐지만 pin에 실패했습니다.")
        return

    logger.info("", extra={"event": "pin_posted", "user_id": body["user_id"]})
    post_ephemeral(client, body, "소개 메시지를 게시하고 pin했습니다.")


def build_pin_intro_blocks():
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "☕ *모카(Mocha) 감사 봇입니다.*\n"
                    "고마운 동료에게 커피 한 잔을 전해보세요."
                ),
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*사용법*\n"
                    "`/thanks @동료 고마운 메시지`\n\n"
                    "*더 보내고 싶다면*\n"
                    "`/thanks @동료 3 메시지` — 커피 3잔\n"
                    "`/thanks ☕☕☕ @동료 메시지` — 이모지로도 가능\n\n"
                    "*확인하기*\n"
                    "`/thanks status` — 오늘 남은 수량\n"
                    "`/thanks received` — 받은 감사 목록"
                ),
            },
        },
    ]


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
    summary_blocks, _ = _build_summary_payload(summary_type)
    return summary_blocks


def _build_summary_payload(summary_type):
    conn = get_connection()
    try:
        if summary_type == "weekly":
            start_date, end_date = get_previous_week_range()
            stats = load_weekly_stats(conn, start_date, end_date)
            return build_weekly_summary(stats), build_leaderboard_blocks(stats)

        if summary_type == "this-month":
            start_date, end_date = get_current_month_range()
            stats = load_weekly_stats(conn, start_date, end_date)
            return build_current_month_summary(stats), build_leaderboard_blocks(stats)

        year, month = get_previous_month()
        stats = load_monthly_stats(conn, year, month)
        return build_monthly_summary(stats), build_leaderboard_blocks(stats)
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
