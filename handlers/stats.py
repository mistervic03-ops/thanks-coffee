import logging

from db.queries import get_connection
from services.feed import post_summary
from services.stats import (
    build_monthly_summary,
    build_weekly_summary,
    get_current_week_range,
    get_previous_month,
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


def register(app):
    @app.command("/summary")
    def handle_summary(ack, body, client):
        ack()

        summary_type = (body.get("text") or "").strip().lower()
        if summary_type not in {"weekly", "monthly"}:
            post_ephemeral(
                client,
                body,
                "❌ 사용법: `/summary weekly` 또는 `/summary monthly`",
            )
            return

        try:
            summary_text = _build_summary_text(summary_type)
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
            start_date, end_date = get_current_week_range()
            stats = load_weekly_stats(conn, start_date, end_date)
            return build_weekly_summary(stats)

        year, month = get_previous_month()
        stats = load_monthly_stats(conn, year, month)
        return build_monthly_summary(stats)
    finally:
        conn.close()
