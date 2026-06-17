from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from fastapi import FastAPI
import logging
import threading

from config import HEALTH_CHECK_ENABLED, SCHEDULER_ENABLED, SLACK_BOT_TOKEN, SLACK_APP_TOKEN
from db.queries import init_db
from handlers.thanks import register as register_thanks
from handlers.stats import register as register_stats
from scheduler import start_scheduler

# Slack Bolt App
bolt_app = App(token=SLACK_BOT_TOKEN)
register_thanks(bolt_app)
register_stats(bolt_app)

# FastAPI (헬스체크용)
api = FastAPI()


@api.get("/health")
def health():
    return {"status": "ok"}


def run_fastapi():
    import uvicorn
    uvicorn.run(api, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    if SCHEDULER_ENABLED:
        start_scheduler(bolt_app.client)
    if HEALTH_CHECK_ENABLED:
        threading.Thread(target=run_fastapi, daemon=True).start()
    SocketModeHandler(bolt_app, SLACK_APP_TOKEN).start()
