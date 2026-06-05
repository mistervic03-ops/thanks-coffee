from config import FEED_CHANNEL_ID, RECOGNITION_UNIT
from db.queries import get_connection, update_feed_ts
from services.feed import post_to_feed
from services.recognition import (
    INVALID_FORMAT,
    MISSING_MESSAGE,
    LimitError,
    ParseError,
    SelfRecognitionError,
    create_recognition,
    parse_thanks_text,
)


def post_ephemeral(client, body, text):
    client.chat_postEphemeral(
        channel=body["channel_id"],
        user=body["user_id"],
        text=text,
    )


def register(app):
    @app.command("/thanks")
    def handle_thanks(ack, body, client):
        ack()

        sender_id = body["user_id"]
        try:
            request = parse_thanks_text(body.get("text", ""), sender_id)
        except SelfRecognitionError:
            post_ephemeral(client, body, "❌ 자신에게는 보낼 수 없습니다.")
            return
        except ParseError as exc:
            if exc.reason == MISSING_MESSAGE:
                post_ephemeral(client, body, "❌ 감사 메시지를 함께 작성해주세요.")
            elif exc.reason == INVALID_FORMAT:
                post_ephemeral(
                    client,
                    body,
                    "❌ 형식이 올바르지 않습니다. 예: `/thanks @팀원 감사합니다`",
                )
            return

        conn = get_connection()
        try:
            try:
                result = create_recognition(
                    conn=conn,
                    sender_id=sender_id,
                    request=request,
                    source_channel_id=body["channel_id"],
                )
                conn.commit()
            except LimitError as exc:
                conn.rollback()
                post_ephemeral(
                    client,
                    body,
                    (
                        f"❌ 오늘 보낼 수 있는 {RECOGNITION_UNIT}가 "
                        f"{exc.remaining}잔 남았습니다. ({exc.requested}잔 요청)"
                    ),
                )
                return

            try:
                feed_message_ts = post_to_feed(client, sender_id, result)
                if feed_message_ts:
                    update_feed_ts(
                        conn=conn,
                        recognition_id=result.recognition_id,
                        feed_channel_id=FEED_CHANNEL_ID,
                        feed_message_ts=feed_message_ts,
                    )
                    conn.commit()
            except Exception:
                conn.rollback()
                post_ephemeral(
                    client,
                    body,
                    "✅ 감사는 기록되었지만 feed 채널 게시에 실패했습니다.",
                )
                return

        finally:
            conn.close()

        post_ephemeral(
            client,
            body,
            (
                f"✅ <@{request.receiver_id}>님에게 "
                f"{request.unit_count}잔의 {RECOGNITION_UNIT}를 보냈습니다. "
                f"오늘 남은 {RECOGNITION_UNIT}: {result.remaining}잔"
            ),
        )
