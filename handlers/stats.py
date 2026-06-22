import logging

from config import ADMIN_USER_IDS
from db.queries import get_connection
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


logger = logging.getLogger(__name__)


def post_ephemeral(client, body, text):
    client.chat_postEphemeral(
        channel=body["channel_id"],
        user=body["user_id"],
        text=text,
    )


def is_summary_admin(user_id):
    return user_id in ADMIN_USER_IDS


def register(app):
    @app.command("/summary")
    def handle_summary(ack, body, client):
        ack()

        parts = (body.get("text") or "").strip().lower().split()
        is_admin = is_summary_admin(body["user_id"])
        if not parts or parts == ["help"]:
            post_ephemeral(client, body, build_summary_help(is_admin))
            return

        if not is_admin:
            post_ephemeral(client, body, build_summary_help(False))
            return

        summary_type = parts[0] if parts else ""
        preview = len(parts) == 2 and parts[1] == "preview"
        this_month_preview = parts == ["this-month", "preview"]
        valid_summary = summary_type in {"weekly", "monthly"} and (
            len(parts) == 1 or preview
        )
        if not valid_summary and not this_month_preview:
            post_ephemeral(client, body, build_summary_help(True, "요약 명령어를 다시 확인해주세요."))
            return

        try:
            summary_text = _build_summary_text(summary_type)
            if preview:
                post_ephemeral(client, body, summary_text)
                return

            feed_message_ts = post_summary(client, summary_text)
        except Exception:
            logger.exception("Failed to post %s summary", summary_type)
            post_ephemeral(
                client,
                body,
                "❌ 요약을 게시하지 못했어요. 앱 로그와 feed 채널 설정을 확인해주세요.",
            )
            return

        if feed_message_ts:
            post_ephemeral(client, body, "✅ 모카 감사 요약을 feed 채널에 올렸어요.")
        else:
            post_ephemeral(
                client,
                body,
                "✅ 모카 감사 요약을 만들었어요. FEED_ENABLED=false라 feed 채널에는 올리지 않았어요.",
            )


def build_summary_help(is_admin, prefix=None):
    if not is_admin:
        return "❌ 모카 요약 명령어는 운영자 권한이 필요해요."

    lines = []
    if prefix:
        lines.extend([f"❌ {prefix}", ""])

    lines.extend(
        [
            "📊 모카 요약은 이렇게 볼 수 있어요.",
            "`/summary weekly`",
            "`/summary monthly`",
            "`/summary weekly preview`",
            "`/summary monthly preview`",
            "`/summary this-month preview`",
            "",
            "`preview`는 feed에 올리지 않고 나에게만 보여줘요.",
        ]
    )
    return "\n".join(lines)


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
        conn.close()
