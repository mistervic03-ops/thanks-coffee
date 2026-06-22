# PRODUCT.md

## 1. 왜 이 봇을 만드는가

모카는 SME 팀이 Slack 안에서 가볍게 감사를 표현하고 기록하기 위한 작은 Slack-native 도구다.

## 2. HeyTaco와의 차이

복잡한 보상 플랫폼이 아니라 감사 문화 중심의 작은 Slack-native 제품이다.

## 3. Recognition First, Reward Second

보상보다 감사 표현과 팀 문화 기록을 우선한다.

## 4. MVP 기능 목록

- `/thanks` slash command 방식으로 감사를 전달한다.
- 수량은 이모지 반복(`☕☕☕`) 또는 숫자로 지정할 수 있다.
- `/thanks status`로 잔여 수량과 누적 수신량을 조회한다.
- `/thanks help`와 `/summary help`로 Slack 안에서 사용법을 확인할 수 있다.
- feed 게시, 주간/월간 요약 게시, 기본 집계를 MVP 범위로 둔다.

## 5. V2 후순위 기능

- Message event 기반 recognition 감지 (HeyTaco 방식)
  - 일반 채널 메시지에서 `@팀원 메시지 ☕` 형식을 감지한다.
  - 구현 시 `message.channels` 권한 추가와 팀 공지가 필요하다.
  - service layer는 이미 command와 분리되어 있어 handler 추가만으로 확장 가능하다.
- 상세 리포트, 추가 정책, 고급 자동화는 V2 이후에 검토한다.

## 6. 성공 지표

주간 사용량, 참여자 수, 감사 기록 수를 기준으로 본다.
