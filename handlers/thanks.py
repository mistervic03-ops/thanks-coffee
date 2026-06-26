from zoneinfo import ZoneInfo

from slack_sdk.errors import SlackApiError

from config import ANNOUNCEMENT_CHANNEL_ID, DAILY_LIMIT, RECOGNITION_EMOJI, RECOGNITION_UNIT
from db.queries import (
    get_connection,
    get_recent_received_recognitions,
    get_sent_today,
    get_total_received,
    release_connection,
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
from lifecycle import tracked_handler
from logger import get_logger


logger = get_logger(__name__)
KST = ZoneInfo("Asia/Seoul")
RECEIVED_LIMIT = 10


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
    @tracked_handler
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
        if normalized_text == "received":
            handle_received(client, body, sender_id)
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

        receiver_user = get_receiver_user(client, request.receiver_id)
        try:
            # Slack client is already here, so receiver lookup stays in the handler and the parser remains Slack-free.
            if receiver_is_bot(receiver_user):
                raise ParseError(BOT_RECEIVER)
            if not receiver_is_active(receiver_user):
                post_ephemeral(client, body, "❌ 비활성화된 사용자에게는 감사를 보낼 수 없어요.")
                return
        except ParseError as exc:
            post_ephemeral(client, body, f"❌ {exc.reason}")
            return

        idempotency_key = extract_idempotency_key(body, context)
        if not idempotency_key:
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
                if not result.is_duplicate:
                    logger.info(
                        "",
                        extra={"event": "recognition_created", "user_id": sender_id},
                    )
            except LimitError as exc:
                conn.rollback()
                logger.warning(
                    "",
                    extra={
                        "event": "daily_limit_exceeded",
                        "user_id": sender_id,
                        "detail": f"requested={exc.requested} remaining={exc.remaining}",
                    },
                )
                if exc.remaining > 0:
                    text = (
                        f"❌ 오늘은 {_format_unit_count(exc.remaining)}만 "
                        f"더 보낼 수 있어요. (요청: {_format_unit_count(exc.requested)})"
                    )
                else:
                    text = (
                        "❌ 오늘의 감사 한도를 모두 사용했어요. "
                        f"(요청: {_format_unit_count(exc.requested)})"
                    )

                post_ephemeral(client, body, text)
                return

            if not result.is_duplicate:
                feed_message_ts = None
                try:
                    feed_message_ts = post_to_feed(client, sender_id, result)
                    if feed_message_ts:
                        update_feed_ts(
                            conn=conn,
                            recognition_id=result.recognition_id,
                            feed_channel_id=ANNOUNCEMENT_CHANNEL_ID,
                            feed_message_ts=feed_message_ts,
                        )
                    else:
                        update_feed_status(conn, result.recognition_id, "skipped")
                    conn.commit()
                    if feed_message_ts:
                        logger.info("", extra={"event": "feed_posted", "user_id": sender_id})
                except Exception as exc:
                    conn.rollback()
                    try:
                        update_feed_status(conn, result.recognition_id, "failed")
                        conn.commit()
                    except Exception:
                        conn.rollback()
                    logger.warning(
                        "",
                        extra={
                            "event": _feed_failure_event(exc),
                            "user_id": sender_id,
                            "detail": _exception_detail(exc),
                        },
                    )
                    post_ephemeral(
                        client,
                        body,
                        "✅ 감사는 기록됐지만 feed 채널에는 올리지 못했어요.",
                    )
                    return

        finally:
            release_connection(conn)

        post_ephemeral(
            client,
            body,
            (
                f"☕ 모카가 <@{request.receiver_id}>님께 "
                f"{_format_unit_count(request.unit_count)}을 전해드렸어요.\n"
                f"오늘은 아직 {_format_unit_count(result.remaining)}이 남아 있어요."
            ),
        )
        from handlers.home import refresh_home

        refresh_home(client, sender_id)
        refresh_home(client, request.receiver_id)


def handle_status(client, body, user_id):
    conn = get_connection()
    try:
        sent_today = get_sent_today(conn, user_id)
        total_received = get_total_received(conn, user_id)
    finally:
        release_connection(conn)

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


def handle_received(client, body, user_id):
    conn = get_connection()
    try:
        recognitions = get_recent_received_recognitions(conn, user_id, RECEIVED_LIMIT)
    finally:
        release_connection(conn)

    post_ephemeral(client, body, build_received_text(client, recognitions))


def build_received_text(client, recognitions):
    if not recognitions:
        return (
            f"{RECOGNITION_EMOJI} 아직 받은 감사 {RECOGNITION_UNIT}가 없어요.\n"
            "곧 따뜻한 마음이 도착할 거예요."
        )

    sender_names = {}
    lines = [f"{RECOGNITION_EMOJI} 최근 받은 감사 {len(recognitions)}건이에요."]
    for recognition in recognitions:
        sender_id = recognition["sender_id"]
        if sender_id not in sender_names:
            sender_names[sender_id] = get_user_display_name(client, sender_id)

        lines.append(
            (
                f"• {_format_recognition_date(recognition['created_at'])} · "
                f"{sender_names[sender_id]} · "
                f"{_format_unit_count(recognition['unit_count'])}\n"
                f"  \"{recognition['message']}\""
            )
        )

    return "\n".join(lines)


def build_thanks_help(prefix=None):
    lines = []
    if prefix:
        lines.extend([f"❌ {prefix}", ""])

    lines.extend(
        [
            f"{RECOGNITION_EMOJI} 고마운 순간이 있으면 모카에게 이렇게 부탁해주세요.",
            "`/thanks @user 빠르게 도와줘서 고마워요`",
            "`/thanks @user 3 큰 도움을 줘서 고마워요`",
            f"`/thanks {RECOGNITION_EMOJI * 3} @user 정말 고마워요`",
            "",
            f"받은 감사와 오늘 남은 수량은 모카 App Home에서 볼 수 있어요.",
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


def _format_recognition_date(created_at):
    if hasattr(created_at, "astimezone"):
        created_at = created_at.astimezone(KST)

    return created_at.strftime("%Y-%m-%d")


def get_user_display_name(client, user_id):
    try:
        response = client.users_info(user=user_id)
    except SlackApiError:
        return f"<@{user_id}>"

    user = response.get("user", {})
    profile = user.get("profile", {})
    return (
        profile.get("display_name")
        or profile.get("real_name")
        or user.get("real_name")
        or user.get("name")
        or f"<@{user_id}>"
    )


def get_receiver_user(client, receiver_id):
    try:
        response = client.users_info(user=receiver_id)
    except Exception:
        logger.warning(
            "",
            extra={"event": "receiver_status_check_failed", "detail": receiver_id},
        )
        return None

    return response.get("user", {})


def receiver_is_bot(receiver_user):
    return bool(receiver_user and receiver_user.get("is_bot"))


def receiver_is_active(receiver_user):
    return not bool(receiver_user and receiver_user.get("deleted"))


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


def _feed_failure_event(exc):
    if _is_slack_rate_limited(exc):
        return "slack_rate_limited"

    return "feed_post_failed"


def _is_slack_rate_limited(exc):
    if not isinstance(exc, SlackApiError):
        return False

    return exc.response.status_code == 429 or exc.response.get("error") == "ratelimited"


def _exception_detail(exc):
    if isinstance(exc, SlackApiError):
        return exc.response.get("error") or str(exc)

    return str(exc)
