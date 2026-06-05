from config import DAILY_LIMIT, FEED_CHANNEL_ID, RECOGNITION_EMOJI, RECOGNITION_UNIT
from db.queries import get_connection, get_sent_today, get_total_received, update_feed_ts
from services.feed import post_to_feed
from services.recognition import (
    BOT_RECEIVER,
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

        print(f"DEBUG text: {repr(body.get('text', ''))}")

        sender_id = body["user_id"]
        text = body.get("text", "")
        if text.strip().lower() == "status":
            handle_status(client, body, sender_id)
            return

        try:
            request = parse_thanks_text(text, sender_id)
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
            else:
                post_ephemeral(client, body, f"❌ {exc.reason}")
            return

        try:
            # Slack client is already here, so bot lookup stays in the handler and the parser remains Slack-free.
            if receiver_is_bot(client, request.receiver_id):
                raise ParseError(BOT_RECEIVER)
        except ParseError as exc:
            post_ephemeral(client, body, f"❌ {exc.reason}")
            return
        except Exception:
            post_ephemeral(
                client,
                body,
                "❌ 사용자 정보를 확인할 수 없습니다. 잠시 후 다시 시도해주세요.",
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


def handle_status(client, body, user_id):
    conn = get_connection()
    try:
        sent_today = get_sent_today(conn, user_id)
        total_received = get_total_received(conn, user_id)
    finally:
        conn.close()

    remaining = max(DAILY_LIMIT - sent_today, 0)
    post_ephemeral(
        client,
        body,
        (
            f"{RECOGNITION_EMOJI} 오늘 남은 {RECOGNITION_UNIT}: {remaining}잔\n"
            f"📬 내가 받은 {RECOGNITION_UNIT} (누적): {total_received}잔"
        ),
    )


def receiver_is_bot(client, receiver_id):
    response = client.users_info(user=receiver_id)
    user = response["user"]
    return bool(user.get("is_bot"))
