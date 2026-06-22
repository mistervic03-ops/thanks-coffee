# 모카 (Mocha)

Slack 안에서 팀원에게 감사 커피를 전하고 기록하는 작은 Recognition Bot.

## Setup

1. Create a Slack app with Socket Mode enabled.
2. Copy `.env.example` to `.env` and fill in the values. See `docs/SLACK_SETUP.md` for the full environment variable list.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the app:

```bash
python app.py
```

## Optional Health Check

Optional operations flags default to `false`, so the PoC runs Slack-command first unless explicitly enabled.

Set `HEALTH_CHECK_ENABLED=true` to enable the local health check server. `/health` checks process liveness and `/ready` checks DB connectivity. The default port is `8000`; set `HEALTH_CHECK_PORT=8020` on Spark to avoid existing services.

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```
