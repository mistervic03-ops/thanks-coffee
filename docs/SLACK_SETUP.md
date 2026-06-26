# SLACK_SETUP.md

## 1. Slack App 생성

Slack API 콘솔에서 ☕ 모카 앱을 생성한다.

## 2. manifest.yaml

```yaml
display_information:
  name: ☕ 모카
  description: 팀원에게 감사 커피를 전하는 작은 Slack 봇
  background_color: "#7C3AED"

features:
  app_home:
    home_tab_enabled: true
    messages_tab_enabled: false
  slash_commands:
    - command: /thanks
      description: 팀원에게 감사를 전합니다
      usage_hint: "@팀원 메시지"
      should_escape: true
    - command: /mocha
      description: mocha 관리자 명령어
      usage_hint: "delete {recognition_id}, summary weekly|monthly [preview], summary this-month preview"
      should_escape: true
  bot_user:
    display_name: ☕ 모카
    always_online: true

oauth_config:
  scopes:
    bot:
      - commands
      - chat:write
      - users:read

settings:
  event_subscriptions:
    bot_events:
      - app_home_opened
  socket_mode_enabled: true
  token_rotation_enabled: false
```

`users:read`는 Slack workspace Admin/Owner를 자동으로 운영자 목록에 포함하기 위해 필요하다.

Slash command 설정에서 **Escape channels, users, and links**를 반드시 켠다. `/thanks` parser는 Slack이 변환한 `<@USER_ID>` 형태의 mention payload를 사용한다. 이 설정이 꺼져 있으면 `@username` 형태가 들어와 `invalid_format`이 날 수 있다.

PoC 사용자 안내에서는 핵심 명령어를 `/thanks` 하나로 소개한다. 기본 감사 메시지, 숫자 수량, 이모지 수량 예시는 보여주되 별도 조회 명령어는 강조하지 않는다.

Slack 앱 설정 > Slash Commands에서 `/summary` 커맨드는 제거하고 `/mocha` 커맨드를 추가한다. Description은 `mocha 관리자 명령어`, Usage hint는 `delete {recognition_id}, summary weekly|monthly [preview], summary this-month preview`로 설정한다.

`/thanks` 또는 `/thanks help`는 일반 사용자용 핵심 사용법과 App Home 안내를 ephemeral message로 보여준다. `/thanks status`, `/thanks received`는 직접 입력 가능한 보조 조회 명령어로 유지하지만 일반 help에는 노출하지 않는다. `/mocha`는 관리자 전용 운영 명령어이며 잘못 입력된 recognition 삭제와 수동 summary 게시/미리보기에 사용한다.

App Home의 Home tab을 켜고 `app_home_opened` bot event를 구독한다. Home tab은 읽기 전용으로 오늘 남은 수량, 나의 받은/보낸 감사 요약, 최근 받은 감사 메시지, 최근 보낸 감사 메시지, 짧은 사용 예시를 보여준다.

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
| `DB_POOL_MIN` | 선택 | `1` | PostgreSQL connection pool의 최소 연결 수다. | 예 |
| `DB_POOL_MAX` | 선택 | `5` | PostgreSQL connection pool의 최대 연결 수다. | 예 |
| `DAILY_LIMIT` | 선택 | `5` | 한 사용자가 KST 하루 동안 보낼 수 있는 최대 수량이다. | 예 |
| `FEED_ENABLED` | 선택 | `true` | recognition과 summary를 feed 채널에 게시할지 결정한다. | 예 |
| `FEED_CHANNEL_ID` | 조건부 필수 | 빈 값 | `FEED_ENABLED=true`이면 필수다. `FEED_ENABLED=false`이면 비워둘 수 있다. | 예 |
| `ADMIN_USER_IDS` | 선택 | 빈 값 | `/mocha`를 실행할 수 있는 추가 Slack user ID 목록이다. 쉼표로 구분한다. Slack workspace Admin/Owner는 자동 포함된다. | 예 |
| `SCHEDULER_ENABLED` | 선택 | `false` | `true`이면 자동 주간/월간 summary scheduler를 실행한다. Spark PoC 기본 운영은 `false`로 두고 수동 `/mocha summary`를 사용한다. | 예 |
| `HEALTH_CHECK_ENABLED` | 선택 | `false` | `true`이면 `/health` 생존 확인과 `/ready` DB 연결 확인 서버를 실행한다. PoC 기본 운영은 `false`다. | 예 |
| `HEALTH_CHECK_PORT` | 선택 | `8000` | health check 서버 포트다. Spark에서는 기존 서비스와 충돌하지 않도록 `8020`을 사용한다. | 예 |
| `LOG_LEVEL` | 선택 | `INFO` | stdout JSON 로그 레벨이다. 운영 기본값은 `INFO`이며 개발 시 `DEBUG`로 낮출 수 있다. | 예 |
| `RECOGNITION_EMOJI` | 선택 | `☕` | 수량 표현에 사용할 이모지다. | 예 |
| `RECOGNITION_UNIT` | 선택 | `커피` | 사용자 메시지에 표시할 단위 이름이다. | 예 |

## 5. recognition 채널에 봇 초대

feed를 게시할 채널에 ☕ 모카를 초대한다.

## 6. 동작 확인 체크리스트

DB 초기화와 `/thanks` ephemeral 응답을 확인한다. `HEALTH_CHECK_ENABLED=true`이면 `/health`와 `/ready`도 함께 확인한다.

운영자가 feed 게시 없이 summary를 확인하려면 `/mocha summary weekly preview`, `/mocha summary monthly preview`, `/mocha summary this-month preview`를 사용한다. 자세한 운영 절차는 `docs/OPERATIONS.md`를 따른다.
