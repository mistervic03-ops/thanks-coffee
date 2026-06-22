from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from fastapi import FastAPI, HTTPException
import logging
import threading

from config import (
    HEALTH_CHECK_ENABLED,
    HEALTH_CHECK_PORT,
    SCHEDULER_ENABLED,
    SLACK_APP_TOKEN,
    SLACK_BOT_TOKEN,
)
from db.queries import get_connection, init_db
from handlers.home import register as register_home
from handlers.thanks import register as register_thanks
from handlers.stats import register as register_stats
from scheduler import start_scheduler

# Slack Bolt App
bolt_app = App(token=SLACK_BOT_TOKEN)
register_home(bolt_app)
register_thanks(bolt_app)
register_stats(bolt_app)

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    if SCHEDULER_ENABLED:
        start_scheduler(bolt_app.client)
    if HEALTH_CHECK_ENABLED:
        threading.Thread(target=run_fastapi, daemon=True).start()
    SocketModeHandler(bolt_app, SLACK_APP_TOKEN).start()
