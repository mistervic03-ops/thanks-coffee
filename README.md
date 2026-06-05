# Recognition Bot

Slack-native recognition bot for small teams.

## Setup

1. Create a Slack app with Socket Mode enabled.
2. Copy `.env.example` to `.env` and fill in the values.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the app:

```bash
python app.py
```

## Health Check

```bash
curl http://localhost:8000/health
```
