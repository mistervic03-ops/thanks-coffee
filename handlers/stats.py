import logging

from config import ADMIN_USER_IDS
from db.queries import get_connection
from services.feed import post_summary
from services.stats import (
    build_monthly_summary,
    build_weekly_summary,
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

        if not is_summary_admin(body["user_id"]):
            post_ephemeral(client, body, "❌ 이 명령어를 실행할 권한이 없습니다.")
            return

        parts = (body.get("text") or "").strip().lower().split()
        summary_type = parts[0] if parts else ""
        preview = len(parts) == 2 and parts[1] == "preview"
        if summary_type not in {"weekly", "monthly"} or len(parts) > 2 or (len(parts) == 2 and not preview):
            post_ephemeral(
                client,
                body,
                (
                    "❌ 사용법: `/summary weekly`, `/summary monthly`, "
                    "`/summary weekly preview`, `/summary monthly preview`"
                ),
            )
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
                "❌ 요약 게시에 실패했습니다. 앱 로그와 feed 채널 설정을 확인해주세요.",
            )
            return

        if feed_message_ts:
            post_ephemeral(client, body, "✅ 요약을 feed 채널에 게시했습니다.")
        else:
            post_ephemeral(
                client,
                body,
                "✅ 요약을 생성했습니다. FEED_ENABLED=false라 feed 채널에는 게시하지 않았습니다.",
            )


def _build_summary_text(summary_type):
    conn = get_connection()
    try:
        if summary_type == "weekly":
            start_date, end_date = get_previous_week_range()
            stats = load_weekly_stats(conn, start_date, end_date)
            return build_weekly_summary(stats)

        year, month = get_previous_month()
        stats = load_monthly_stats(conn, year, month)
        return build_monthly_summary(stats)
    finally:
        conn.close()
