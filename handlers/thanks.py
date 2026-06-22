import logging

from slack_sdk.errors import SlackApiError

from config import DAILY_LIMIT, FEED_CHANNEL_ID, RECOGNITION_EMOJI, RECOGNITION_UNIT
from db.queries import (
    get_connection,
    get_sent_today,
    get_total_received,
    update_feed_status,
    update_feed_ts,
)
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


logger = logging.getLogger(__name__)


def post_ephemeral(client, body, text):
    try:
        client.chat_postEphemeral(
            channel=body["channel_id"],
            user=body["user_id"],
            text=text,
        )
    except SlackApiError as exc:
        if exc.response.get("error") != "channel_not_found":
            raise

        client.chat_postMessage(channel=body["user_id"], text=text)


def register(app):
    @app.command("/thanks")
    def handle_thanks(ack, body, client, context=None):
        ack()

        sender_id = body["user_id"]
        text = body.get("text", "")
        normalized_text = text.strip().lower()
        if not normalized_text or normalized_text == "help":
            post_ephemeral(client, body, build_thanks_help())
            return
        if normalized_text == "status":
            handle_status(client, body, sender_id)
            return

        try:
            request = parse_thanks_text(text, sender_id)
        except SelfRecognitionError:
            post_ephemeral(client, body, "❌ 자신에게는 보낼 수 없어요.")
            return
        except ParseError as exc:
            if exc.reason == MISSING_MESSAGE:
                post_ephemeral(client, body, build_thanks_help("감사 메시지도 함께 적어주세요."))
            elif exc.reason == INVALID_FORMAT:
                post_ephemeral(client, body, build_thanks_help("형식을 다시 확인해주세요."))
            else:
                post_ephemeral(client, body, build_thanks_help(exc.reason))
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
                "❌ 사용자 정보를 확인할 수 없어요. 잠시 후 다시 시도해주세요.",
            )
            return

        idempotency_key = extract_idempotency_key(body, context)
        if not idempotency_key:
            logger.error("Failed to extract idempotency key for /thanks body=%s", _safe_body(body))
            post_ephemeral(
                client,
                body,
                "❌ 요청을 안전하게 식별할 수 없어요. 잠시 후 다시 시도해주세요.",
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
                    idempotency_key=idempotency_key,
                )
                conn.commit()
            except LimitError as exc:
                conn.rollback()
                post_ephemeral(
                    client,
                    body,
                    (
                        f"❌ 오늘은 {_format_unit_count(exc.remaining)}만 "
                        f"더 보낼 수 있어요. (요청: {_format_unit_count(exc.requested)})"
                    ),
                )
                return

            if not result.is_duplicate:
                feed_message_ts = None
                try:
                    feed_message_ts = post_to_feed(client, sender_id, result)
                    if feed_message_ts:
                        update_feed_ts(
                            conn=conn,
                            recognition_id=result.recognition_id,
                            feed_channel_id=FEED_CHANNEL_ID,
                            feed_message_ts=feed_message_ts,
                        )
                    else:
                        update_feed_status(conn, result.recognition_id, "skipped")
                    conn.commit()
                except Exception:
                    conn.rollback()
                    try:
                        update_feed_status(conn, result.recognition_id, "failed")
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        logger.exception(
                            "Failed to record feed failure for recognition_id=%s",
                            result.recognition_id,
                        )

                    logger.exception(
                        (
                            "Failed to post/update feed for recognition_id=%s "
                            "idempotency_key=%s feed_channel_id=%s feed_message_ts=%s"
                        ),
                        result.recognition_id,
                        idempotency_key,
                        FEED_CHANNEL_ID,
                        feed_message_ts,
                    )
                    post_ephemeral(
                        client,
                        body,
                        "✅ 감사는 기록됐지만 feed 채널에는 올리지 못했어요.",
                    )
                    return

        finally:
            conn.close()

        post_ephemeral(
            client,
            body,
            (
                f"☕ 모카가 <@{request.receiver_id}>님께 "
                f"{_format_unit_count(request.unit_count)}을 전해드렸어요.\n"
                f"오늘은 아직 {_format_unit_count(result.remaining)}이 남아 있어요."
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
            f"{RECOGNITION_EMOJI} 오늘은 아직 "
            f"{_format_unit_count(remaining)}이 남아 있어요.\n"
            f"📬 지금까지 받은 {RECOGNITION_UNIT}: {_format_count(total_received)}"
        ),
    )


def build_thanks_help(prefix=None):
    lines = []
    if prefix:
        lines.extend([f"❌ {prefix}", ""])

    lines.extend(
        [
            f"{RECOGNITION_EMOJI} 모카에게 이렇게 부탁할 수 있어요.",
            "`/thanks @user message`",
            "`/thanks @user 3 message`",
            f"`/thanks {RECOGNITION_EMOJI * 3} @user message`",
            "`/thanks status`",
            "",
            f"하루에 보낼 수 있는 수량은 {_format_unit_count(DAILY_LIMIT)}까지예요.",
            "이 안내 응답은 나에게만 보여요.",
        ]
    )
    return "\n".join(lines)


def _format_unit_count(unit_count):
    return f"{RECOGNITION_UNIT} {_format_count(unit_count)}"


def _format_count(unit_count):
    if unit_count == 1:
        return "한 잔"

    return f"{unit_count}잔"


def receiver_is_bot(client, receiver_id):
    response = client.users_info(user=receiver_id)
    user = response["user"]
    return bool(user.get("is_bot"))


def extract_idempotency_key(body, context=None):
    context = context or {}
    for source, value in (
        ("socket_envelope", _get_context_value(context, "envelope_id")),
        ("socket_envelope", body.get("envelope_id")),
        ("slack_request", _get_context_value(context, "request_id")),
        ("slack_request", body.get("request_id")),
        ("trigger", body.get("trigger_id")),
        ("response_url", body.get("response_url")),
    ):
        if value:
            return f"/thanks:{source}:{value}"

    return None


def _get_context_value(context, key):
    if hasattr(context, "get"):
        return context.get(key)
    return None


def _safe_body(body):
    return {
        key: body.get(key)
        for key in (
            "team_id",
            "channel_id",
            "user_id",
            "command",
            "text",
            "trigger_id",
        )
    }
