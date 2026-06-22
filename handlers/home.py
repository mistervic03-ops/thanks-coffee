import logging

from config import DAILY_LIMIT, RECOGNITION_EMOJI, RECOGNITION_UNIT
from db.queries import (
    get_connection,
    get_personal_recognition_summary,
    get_recent_received_recognitions,
    get_recent_sent_recognitions,
    get_sent_today,
)
from handlers.thanks import (
    _format_count,
    _format_recognition_date,
    get_user_display_name,
)


logger = logging.getLogger(__name__)
HOME_RECEIVED_LIMIT = 5
HOME_SENT_LIMIT = 5


def register(app):
    @app.event("app_home_opened")
    def handle_app_home_opened(event, client):
        if event.get("tab") and event["tab"] != "home":
            return

        user_id = event["user"]
        try:
            view = build_home_view_for_user(client, user_id)
            client.views_publish(user_id=user_id, view=view)
        except Exception:
            logger.exception("Failed to publish App Home for user_id=%s", user_id)


def build_home_view_for_user(client, user_id):
    conn = get_connection()
    try:
        sent_today = get_sent_today(conn, user_id)
        summary = get_personal_recognition_summary(conn, user_id)
        received_recognitions = get_recent_received_recognitions(
            conn,
            user_id,
            HOME_RECEIVED_LIMIT,
        )
        sent_recognitions = get_recent_sent_recognitions(conn, user_id, HOME_SENT_LIMIT)
    finally:
        conn.close()

    remaining = max(DAILY_LIMIT - sent_today, 0)
    return build_home_view(
        remaining=remaining,
        summary=summary,
        received_recognitions=with_sender_names(client, received_recognitions),
        sent_recognitions=with_receiver_names(client, sent_recognitions),
    )


def with_sender_names(client, recognitions):
    return with_user_names(client, recognitions, source_key="sender_id", target_key="sender_name")


def with_receiver_names(client, recognitions):
    return with_user_names(
        client,
        recognitions,
        source_key="receiver_id",
        target_key="receiver_name",
    )


def with_user_names(client, recognitions, source_key, target_key):
    user_names = {}
    decorated = []
    for recognition in recognitions:
        user_id = recognition[source_key]
        if user_id not in user_names:
            user_names[user_id] = get_user_display_name(client, user_id)

        decorated.append({**recognition, target_key: user_names[user_id]})

    return decorated


def build_home_view(remaining, summary, received_recognitions, sent_recognitions):
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{RECOGNITION_EMOJI} 모카 Home"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "고마운 순간을 놓치지 않도록 모카가 기록해둘게요.\n"
                    "채널에서 `/thanks @user 메시지`로 바로 전할 수 있어요."
                ),
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": "*오늘 남은 커피*",
                },
                {
                    "type": "mrkdwn",
                    "text": f"`{_format_count(remaining)}`",
                },
            ],
        },
        {"type": "divider"},
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "나의 커피 요약"},
        },
        {
            "type": "section",
            "fields": _build_summary_fields(summary),
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "내가 주고받은 감사 흐름을 조용히 돌아보는 용도예요.",
                }
            ],
        },
        {"type": "divider"},
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "최근 받은 감사"},
        },
    ]

    if received_recognitions:
        for recognition in received_recognitions:
            blocks.extend(_build_received_recognition_blocks(recognition))
    else:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "> 아직 받은 감사가 없어요. 곧 따뜻한 마음이 도착할 거예요.",
                },
            }
        )

    blocks.extend(
        [
            {"type": "divider"},
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "최근 보낸 감사"},
            },
        ]
    )

    if sent_recognitions:
        for recognition in sent_recognitions:
            blocks.extend(_build_sent_recognition_blocks(recognition))
    else:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "> 아직 보낸 감사가 없어요. 오늘 도움을 준 동료에게 전해보세요.",
                },
            }
        )

    blocks.extend(
        [
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "💡 *사용 예시*\n"
                        "`/thanks @user 빠르게 도와줘서 고마워요`\n"
                        "`/thanks @user 3 큰 도움을 줘서 고마워요`"
                    ),
                },
            },
        ]
    )

    return {"type": "home", "blocks": blocks}


def _build_received_recognition_blocks(recognition):
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{recognition['sender_name']}*님이 전했어요\n> {recognition['message']}",
            },
        },
        _build_recognition_context(recognition),
    ]


def _build_sent_recognition_blocks(recognition):
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{recognition['receiver_name']}*님에게 보냈어요\n> {recognition['message']}",
            },
        },
        _build_recognition_context(recognition),
    ]


def _build_summary_fields(summary):
    return [
        {
            "type": "mrkdwn",
            "text": (
                "*받은 커피*\n"
                f"이번 주 {_format_count(summary['received_week'])}\n"
                f"이번 달 {_format_count(summary['received_month'])}\n"
                f"누적 {_format_count(summary['received_total'])}"
            ),
        },
        {
            "type": "mrkdwn",
            "text": (
                "*보낸 커피*\n"
                f"이번 주 {_format_count(summary['sent_week'])}\n"
                f"이번 달 {_format_count(summary['sent_month'])}\n"
                f"누적 {_format_count(summary['sent_total'])}"
            ),
        },
    ]


def _build_recognition_context(recognition):
    return {
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": (
                    f"{_format_recognition_date(recognition['created_at'])} · "
                    f"{RECOGNITION_UNIT} {_format_count(recognition['unit_count'])}"
                ),
            }
        ],
    }
