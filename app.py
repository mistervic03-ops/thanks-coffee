from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from fastapi import FastAPI, HTTPException
import signal
import sys
import threading

from config import (
    HEALTH_CHECK_ENABLED,
    HEALTH_CHECK_PORT,
    SCHEDULER_ENABLED,
    SLACK_APP_TOKEN,
    SLACK_BOT_TOKEN,
)
from db.queries import close_connection, get_connection, init_db
from handlers.home import register as register_home
from handlers.thanks import register as register_thanks
from handlers.stats import register as register_stats
from lifecycle import wait_for_requests
from logger import configure_logging, get_logger
from scheduler import start_scheduler
from services.feed_retry import retry_failed_feeds


logger = get_logger(__name__)
socket_mode_handler = None
scheduler_instance = None
_shutdown_started = False

# FastAPI (헬스체크용)
api = FastAPI()


@api.get("/health")
def health():
    return {"status": "ok"}


@api.get("/ready")
def ready():
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="db_unavailable") from exc
    finally:
        if conn:
            conn.close()

    return {"status": "ready"}


def run_fastapi():
    import uvicorn
    uvicorn.run(api, host="0.0.0.0", port=HEALTH_CHECK_PORT)


def create_bolt_app():
    bolt_app = App(token=SLACK_BOT_TOKEN)
    register_home(bolt_app)
    register_thanks(bolt_app)
    register_stats(bolt_app)
    return bolt_app


def register_signal_handlers():
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)


def shutdown(signum=None, frame=None):
    global _shutdown_started

    if _shutdown_started:
        return

    _shutdown_started = True
    logger.info("", extra={"event": "app_shutdown_started"})

    if socket_mode_handler:
        _run_shutdown_step(socket_mode_handler.close)
    _run_shutdown_step(lambda: wait_for_requests(timeout=10))
    if scheduler_instance:
        _run_shutdown_step(lambda: _shutdown_scheduler(scheduler_instance))
    _run_shutdown_step(close_connection)

    logger.info("", extra={"event": "app_shutdown"})
    sys.exit(0)


def _shutdown_scheduler(scheduler):
    try:
        scheduler.shutdown(wait=True, timeout=10)
    except TypeError:
        scheduler.shutdown(wait=True)


def _run_shutdown_step(step):
    try:
        step()
    except Exception as exc:
        logger.error("", extra={"event": "shutdown_error", "detail": str(exc)})


def run_app():
    global scheduler_instance, socket_mode_handler

    configure_logging()
    register_signal_handlers()
    logger.info("", extra={"event": "app_starting"})
    try:
        bolt_app = create_bolt_app()
        init_db()
        if SCHEDULER_ENABLED:
            scheduler_instance = start_scheduler(bolt_app)
        if HEALTH_CHECK_ENABLED:
            threading.Thread(target=run_fastapi, daemon=True).start()
        retry_failed_feeds(bolt_app)
        socket_mode_handler = SocketModeHandler(bolt_app, SLACK_APP_TOKEN)
        socket_mode_handler.start()
    except KeyboardInterrupt:
        shutdown()
    except Exception as exc:
        logger.error("", extra={"event": "unhandled_exception", "detail": str(exc)})
        sys.exit(1)
    else:
        shutdown()


if __name__ == "__main__":
    run_app()
