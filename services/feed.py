from config import ANNOUNCEMENT_CHANNEL_ID, FEED_ENABLED, RECOGNITION_EMOJI, RECOGNITION_UNIT


def post_to_feed(client, sender_id, result):
    if not FEED_ENABLED:
        return None

    response = client.chat_postMessage(
        channel=ANNOUNCEMENT_CHANNEL_ID,
        text=build_feed_fallback_text(sender_id, result.receiver_id),
        blocks=build_feed_blocks(
            sender_id=sender_id,
            receiver_id=result.receiver_id,
            message=result.message,
            total_received=result.total_received,
        ),
    )
    return response["ts"]


def build_feed_blocks(sender_id, receiver_id, message, total_received):
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{RECOGNITION_EMOJI} *<@{sender_id}>님이 "
                    f"<@{receiver_id}>님께 감사 {RECOGNITION_UNIT}를 전했어요.*"
                ),
            },
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"> \"{message}\""},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"<@{receiver_id}>님이 지금까지 받은 {RECOGNITION_UNIT}: "
                        f"{_format_count(total_received)}"
                    ),
                }
            ],
        },
    ]


def build_feed_fallback_text(sender_id, receiver_id):
    return (
        f"{RECOGNITION_EMOJI} <@{sender_id}>님이 "
        f"<@{receiver_id}>님께 감사 {RECOGNITION_UNIT}를 전했어요."
    )


def post_summary(client, blocks):
    if not FEED_ENABLED:
        return None

    response = client.chat_postMessage(
        channel=ANNOUNCEMENT_CHANNEL_ID,
        text=build_summary_fallback_text(blocks),
        blocks=blocks,
    )
    return response["ts"]


def build_summary_fallback_text(blocks):
    if isinstance(blocks, str):
        return blocks

    title = blocks[0]["text"]["text"]
    if title.startswith("📊 직전 주 모카 감사 요약"):
        return "📊 직전 주 모카 감사 요약"

    return title


def _format_count(unit_count):
    if unit_count == 1:
        return "한 잔"

    return f"{unit_count}잔"
