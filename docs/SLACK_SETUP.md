# SLACK_SETUP.md

## 1. Slack App 생성

Slack API 콘솔에서 RecognitionBot 앱을 생성한다.

## 2. manifest.yaml

```yaml
display_information:
  name: RecognitionBot
  description: 팀원에게 감사를 전하는 Recognition Bot
  background_color: "#7C3AED"

features:
  slash_commands:
    - command: /thanks
      description: 팀원에게 감사를 전합니다
      usage_hint: "@팀원 [수량] 메시지 또는 status"
      should_escape: true
    - command: /summary
      description: Recognition 요약을 feed 채널에 게시합니다
      usage_hint: "weekly 또는 monthly"
      should_escape: true
  bot_user:
    display_name: RecognitionBot
    always_online: true

oauth_config:
  scopes:
    bot:
      - commands
      - chat:write
      - users:read

settings:
  socket_mode_enabled: true
  token_rotation_enabled: false
```

Slash command 설정에서 **Escape channels, users, and links**를 반드시 켠다. `/thanks` parser는 Slack이 변환한 `<@USER_ID>` 형태의 mention payload를 사용한다. 이 설정이 꺼져 있으면 `@username` 형태가 들어와 `invalid_format`이 날 수 있다.

## 3. Socket Mode 설정

Socket Mode를 켜고 app-level token을 발급한다.

## 4. 환경변수 목록

`.env.example`의 값을 실제 Slack/DB 값으로 채운다. 환경변수를 바꾼 뒤에는 프로세스를 재시작한다.

Boolean flag는 문자열 `"true"`일 때만 true로 처리한다. 미설정이거나 다른 값이면 false로 처리된다. 단, `FEED_ENABLED`는 코드 기본값이 true다.

| 환경변수 | 필수 여부 | 기본값 | 설명 | 재시작 필요 |
|----------|-----------|--------|------|-------------|
| `SLACK_BOT_TOKEN` | 필수 | 없음 | Slack bot token이다. Bolt app 생성에 사용한다. | 예 |
| `SLACK_APP_TOKEN` | 필수 | 없음 | Socket Mode app-level token이다. | 예 |
| `DATABASE_URL` | 필수 | 없음 | PostgreSQL 연결 문자열이다. | 예 |
| `DAILY_LIMIT` | 선택 | `5` | 한 사용자가 KST 하루 동안 보낼 수 있는 최대 수량이다. | 예 |
| `FEED_ENABLED` | 선택 | `true` | recognition과 summary를 feed 채널에 게시할지 결정한다. | 예 |
| `FEED_CHANNEL_ID` | 조건부 필수 | 빈 값 | `FEED_ENABLED=true`이면 필수다. `FEED_ENABLED=false`이면 비워둘 수 있다. | 예 |
| `ADMIN_USER_IDS` | 선택 | 빈 값 | `/summary`를 실행할 수 있는 Slack user ID 목록이다. 쉼표로 구분한다. 비어 있으면 아무도 `/summary`를 실행할 수 없다. | 예 |
| `SCHEDULER_ENABLED` | 선택 | `false` | `true`이면 자동 주간/월간 summary scheduler를 실행한다. PoC 기본 운영은 `false`로 두고 수동 `/summary`를 사용한다. | 예 |
| `HEALTH_CHECK_ENABLED` | 선택 | `false` | `true`이면 `http://localhost:8000/health` HTTP health check 서버를 실행한다. PoC 기본 운영은 `false`다. | 예 |
| `RECOGNITION_EMOJI` | 선택 | `☕` | 수량 표현에 사용할 이모지다. | 예 |
| `RECOGNITION_UNIT` | 선택 | `커피` | 사용자 메시지에 표시할 단위 이름이다. | 예 |

## 5. recognition 채널에 봇 초대

feed를 게시할 채널에 RecognitionBot을 초대한다.

## 6. 동작 확인 체크리스트

DB 초기화와 `/thanks` ephemeral 응답을 확인한다. `HEALTH_CHECK_ENABLED=true`이면 health check도 함께 확인한다.
