from config import FEED_CHANNEL_ID, FEED_ENABLED, RECOGNITION_EMOJI, RECOGNITION_UNIT


def post_to_feed(client, sender_id, result):
    if not FEED_ENABLED:
        return None

    text = (
        f"{RECOGNITION_EMOJI} <@{sender_id}> → <@{result.receiver_id}>\n"
        f"\"{result.message}\"\n"
        "───────────────────\n"
        f"<@{result.receiver_id}>님의 누적 {RECOGNITION_UNIT}: {result.total_received}잔"
    )
    response = client.chat_postMessage(channel=FEED_CHANNEL_ID, text=text)
    return response["ts"]


def post_summary(client, text):
    if not FEED_ENABLED:
        return None

    response = client.chat_postMessage(channel=FEED_CHANNEL_ID, text=text)
    return response["ts"]
