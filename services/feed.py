from config import FEED_CHANNEL_ID, FEED_ENABLED, RECOGNITION_EMOJI, RECOGNITION_UNIT


def post_to_feed(client, sender_id, result):
    if not FEED_ENABLED:
        return None

    text = (
        f"{RECOGNITION_EMOJI} <@{sender_id}>님이 "
        f"<@{result.receiver_id}>님께 감사 {RECOGNITION_UNIT}를 전했어요.\n"
        f"\"{result.message}\"\n"
        "───────────────────\n"
        f"<@{result.receiver_id}>님이 지금까지 받은 {RECOGNITION_UNIT}: "
        f"{_format_count(result.total_received)}"
    )
    response = client.chat_postMessage(channel=FEED_CHANNEL_ID, text=text)
    return response["ts"]


def post_summary(client, text):
    if not FEED_ENABLED:
        return None

    response = client.chat_postMessage(channel=FEED_CHANNEL_ID, text=text)
    return response["ts"]


def _format_count(unit_count):
    if unit_count == 1:
        return "한 잔"

    return f"{unit_count}잔"
