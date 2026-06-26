from config import ADMIN_USER_IDS
from logger import get_logger


logger = get_logger(__name__)
_admin_user_ids = frozenset()
_admin_client = None


def get_admin_user_ids(client):
    slack_admin_ids = set()
    try:
        cursor = None
        while True:
            if cursor:
                response = client.users_list(cursor=cursor)
            else:
                response = client.users_list()

            for user in response.get("members", []):
                if user.get("is_admin") or user.get("is_owner"):
                    slack_admin_ids.add(user["id"])

            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    except Exception as exc:
        logger.warning(
            "",
            extra={"event": "admin_list_fetch_failed", "detail": str(exc)},
        )
        return frozenset(ADMIN_USER_IDS)

    return frozenset(ADMIN_USER_IDS).union(slack_admin_ids)


def init_admin_cache(client):
    global _admin_client, _admin_user_ids
    _admin_client = client
    _admin_user_ids = get_admin_user_ids(client)


def is_admin(user_id):
    return user_id in _admin_user_ids


def notify_admins(client, message):
    if not _admin_user_ids:
        logger.warning("", extra={"event": "no_admins_configured"})
        return

    for user_id in _admin_user_ids:
        try:
            client.chat_postMessage(channel=user_id, text=message)
        except Exception:
            logger.warning(
                "",
                extra={"event": "admin_notify_failed", "detail": user_id},
            )


def notify_cached_admins(message):
    if _admin_client is None:
        return

    notify_admins(_admin_client, message)
