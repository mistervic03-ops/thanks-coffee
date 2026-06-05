# AGENTS.md

## 1. 프로젝트 한 줄 설명

이 프로젝트는 HeyTaco류 Recognition Bot을 SME 환경에 맞게 작게 구현하는 실험이다. Slack 안에서 팀원이 서로 감사를 표현하고 기록하도록 돕는 것이 목적이며, 웹 대시보드나 복잡한 리워드 플랫폼이 아니라 Slack-native first 원칙을 따르는 작은 제품으로 만든다.

## 2. 핵심 철학

### Opinionated Product

이 봇은 설정 가능한 플랫폼이 아니다. 중요한 정책만 `config.py`로 빼고, 사용 사례가 확인되지 않은 옵션은 만들지 않는다.

- 판단 예시: daily limit, feed 사용 여부, 표현 이모지/단위처럼 운영에 직접 필요한 값만 환경변수로 둔다.
- 이 원칙이 없었다면: 정책 엔진이나 관리자 설정 화면을 먼저 만들었을 것이다.

### Slack-native first

사용자 경험은 Slack 안에서 끝나야 한다. 기능을 설계할 때 웹 UI보다 slash command, ephemeral message, feed channel, scheduled post를 우선한다.

- 판단 예시: 사용자가 `/thanks`로 감사를 보내고 Slack 메시지로 결과를 확인하게 한다.
- 이 원칙이 없었다면: MVP에 웹 대시보드와 별도 로그인 흐름을 추가했을 것이다.

### Recognition First, Reward Second

감사 표현과 기록이 핵심이다. 리워드, 배지, 리더보드는 후순위이며 MVP 판단 기준이 아니다.

- 판단 예시: 누가 누구에게 어떤 메시지로 감사를 보냈는지 저장하는 것을 포인트 교환보다 먼저 구현한다.
- 이 원칙이 없었다면: 복잡한 보상 정산, 배지, 경쟁형 랭킹을 먼저 만들었을 것이다.

### 문서는 코드와 함께 유지된다

기능, 구조, 운영 방식이 바뀌면 관련 문서도 함께 바꾼다. 문서는 구현 후에 따로 쓰는 부록이 아니라 에이전트와 운영자가 판단할 때 보는 기준이다.

- 판단 예시: 새 환경변수를 추가하면 `.env.example`과 `docs/SLACK_SETUP.md`를 함께 수정한다.
- 이 원칙이 없었다면: 코드만 바뀌고 Slack 설정이나 운영 문서가 낡은 상태로 남았을 것이다.

### 과도한 추상화 금지

지금 필요하지 않은 유연성을 미리 만들지 않는다. 단일 사용처를 위한 인터페이스, 플러그인 구조, 범용 정책 레이어는 추가하지 않는다.

- 판단 예시: SQL은 `db/queries.py`에 직접 작성하고, ORM이나 repository abstraction은 도입하지 않는다.
- 이 원칙이 없었다면: 작은 MVP에 다층 abstraction과 확장 포인트를 만들었을 것이다.

## 3. Document Map

| 문서 | 위치 | 읽어야 할 때 |
|------|------|-------------|
| AGENTS.md | ./AGENTS.md | 항상. 작업 시작 전 반드시 읽는다. |
| PRODUCT.md | ./docs/PRODUCT.md | 기능 추가/삭제 판단이 필요할 때 |
| ARCHITECTURE.md | ./docs/ARCHITECTURE.md | 구조, 흐름, DB 스키마 확인할 때 |
| SLACK_SETUP.md | ./docs/SLACK_SETUP.md | Slack App 설정, 환경변수 확인할 때 |
| OPERATIONS.md | ./docs/OPERATIONS.md | 운영 정책, 스케줄, 장애 대응 확인할 때 |

## 4. 아키텍처 요약

```text
.
├── app.py
├── config.py
├── scheduler.py
├── handlers/
├── services/
├── db/
│   ├── queries.py
│   └── migrations/
└── docs/
```

- `handlers/`: Slack 이벤트를 수신하고 `ack`를 호출한다. Slack `client`를 service로 전달할 수 있지만 비즈니스 로직은 넣지 않는다.
- `services/`: 비즈니스 로직을 담당한다. Slack API 호출은 `services/feed.py`에만 허용한다.
- `db/queries.py`: SQL을 직접 작성한다. ORM을 사용하지 않는다.
- `config.py`: 환경변수의 단일 진입점이다. 다른 파일에서 `os.environ`에 직접 접근하지 않는다.
- `scheduler.py`: 주간/월간 자동 요약 스케줄만 담당한다.

## 5. Key Decisions

- DB 컬럼명은 `unit_count`를 사용한다. `amount`, `taco_count`로 바꾸지 않는다.
- Daily limit은 별도 테이블 없이 `recognition.unit_count`의 당일 합산으로 계산한다.
- Daily limit의 하루 기준은 KST (UTC+9)다.
- feed 게시는 봇을 채널에 초대하는 방식으로 처리한다. `chat:write.public`은 사용하지 않는다.
- 이모지와 단위는 `RECOGNITION_EMOJI`, `RECOGNITION_UNIT` config 변수를 사용한다. 코드에 하드코딩하지 않는다.
- Socket Mode를 우선한다. 외부 URL을 필수로 만들지 않는다.
- 웹 대시보드는 만들지 않는다.
- Recognition 입력 방식은 MVP에서 `/thanks` slash command만 지원한다.
- HeyTaco처럼 일반 채널 메시지에서 이모지를 감지하는 message event 기반 입력은 의도적으로 제외했다.
- 이유: 봇이 채널의 모든 메시지를 읽는 `message.channels` 권한이 필요하며, SME 환경에서 심리적 거부감을 유발할 수 있다.
- Recognition 생성 로직은 command와 분리되어 `services/recognition.py`에 있으므로, V2에서 필요해지면 message event handler를 추가하는 방식으로 확장한다.
- 이 입력 방식 결정을 임의로 바꾸지 않는다. 변경이 필요하면 `docs/PRODUCT.md`를 먼저 업데이트한다.

## 6. Slack manifest commands

- `/thanks`: 팀원에게 감사를 전하거나 내 상태를 조회한다. 예: `/thanks @팀원 감사합니다`, `/thanks @팀원 3 감사합니다`, `/thanks ☕☕☕ @팀원 감사합니다`, `/thanks status`
- `/summary`: 운영자가 `weekly` 또는 `monthly` 요약을 feed 채널에 게시한다.

## 7. 문서 업데이트 규칙

| 변경 | 함께 수정할 문서 |
|------|------------------|
| 새 기능 추가 | `docs/PRODUCT.md` 기능 목록, `docs/ARCHITECTURE.md` 구조/흐름 |
| 기능 삭제 또는 범위 변경 | `docs/PRODUCT.md`, 필요 시 `docs/ARCHITECTURE.md` |
| DB 스키마 변경 | `docs/ARCHITECTURE.md` 스키마 섹션, 새 마이그레이션 파일 |
| 새 환경변수 추가 | `docs/SLACK_SETUP.md` 환경변수 목록, `.env.example` |
| 운영 정책 변경 | `docs/OPERATIONS.md` |
| Slack manifest 변경 | `docs/SLACK_SETUP.md` |

문서를 업데이트하지 않아도 되는 경우:

- 외부 동작이 바뀌지 않는 버그 수정
- 외부 동작이 바뀌지 않는 리팩토링
- 테스트 추가

문서 업데이트가 필요한 변경인지 판단이 안 되면 업데이트한다.

## 8. Anti-patterns

- 웹 대시보드 추가: Slack 안에서 UX를 완결하는 것이 이 프로젝트의 원칙이다.
- 마이크로서비스 분리: SME 규모에서는 불필요한 복잡성이다.
- ORM 도입: 이 규모에서는 SQL 직접 작성이 더 단순하고 추적 가능하다.
- 기존 마이그레이션 파일 수정: 변경은 새 파일(`002_...`)로 추가한다.
- `config.py` 외에서 `os.environ` 직접 접근: 설정 진입점이 분산된다.
- `RECOGNITION_EMOJI`, `RECOGNITION_UNIT` 하드코딩: 표현 레이어 정책이 깨진다.
- 리워드, 배지, 복잡한 리더보드를 MVP에 포함: recognition 중심의 MVP 범위를 흐린다.
