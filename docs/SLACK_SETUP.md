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
      usage_hint: "@팀원 [수량] 메시지"
      should_escape: false
    - command: /summary
      description: Recognition 요약을 feed 채널에 게시합니다
      usage_hint: "weekly 또는 monthly"
      should_escape: false
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

## 3. Socket Mode 설정

Socket Mode를 켜고 app-level token을 발급한다.

## 4. 환경변수 목록

`.env.example`의 값을 실제 Slack/DB 값으로 채운다.

## 5. recognition 채널에 봇 초대

feed를 게시할 채널에 RecognitionBot을 초대한다.

## 6. 동작 확인 체크리스트

health check, DB 초기화, `/thanks` ephemeral 응답을 확인한다.
