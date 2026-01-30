# AICC Pipeline - AWS Asterisk

## 이 프로젝트 작업 규칙

### 금지 사항
- `aws` CLI 명령어 사용 금지
- `ssh` 직접 접속 금지
- `ssm` 직접 접속 금지
- EC2 인스턴스 직접 제어 금지

### 배포 방법
- 코드 수정 후 `git push origin dev` 또는 `git push origin main`
- GitHub Actions가 자동으로 배포함

### 테스트
- 로컬에서 `docker-compose up`으로 테스트
- EC2 로그 확인 필요시 사용자에게 요청

---

AI Contact Center 시스템. Asterisk PBX로 SIP 통화를 받아 화자별 음성을 분리하고, STT + 턴 분석 후 WebSocket으로 전송.

## 아키텍처

```
Linphone → Asterisk PBX → Stasis App (Node.js) → UDP RTP
                                                    ↓
                         WebSocket ← AICC Pipeline (Python)
```

- **Asterisk**: SIP 통화 수신, ARI로 통화 제어
- **app.js**: Snoop으로 고객/상담사 음성 분리 → ExternalMedia로 UDP 전송
- **aicc_pipeline.py**: UDP RTP 수신 → VAD → Google STT → 형태소 분석 → WebSocket

## 핵심 파일

| 파일 | 역할 |
|------|------|
| `app.js` | Stasis 앱. 통화 이벤트 처리, Dual Snoop (in/out), ExternalMedia 생성 |
| `aicc_pipeline.py` | 메인 파이프라인. RTP 파싱, 오디오 변환, VAD, STT, 턴 판정 |
| `python/aicc_pipeline/` | 모듈화된 버전 (config, audio, vad, stt, turn, websocket) |
| `config/` | Asterisk 설정 (pjsip.conf, extensions.conf, ari.conf 등) |
| `deploy.sh` | EC2 배포 스크립트 |

## 포트

- **UDP 12345**: 고객(customer) 음성 - Snoop spy: `in`
- **UDP 12346**: 상담사(agent) 음성 - Snoop spy: `out`
- **8088**: Asterisk ARI HTTP
- **5060**: SIP 시그널링

## 실행 방법

```bash
# 1. Python 파이프라인 (터미널 1)
python3 aicc_pipeline.py

# 또는 모듈로 실행
cd python && python -m aicc_pipeline

# 2. Stasis App (터미널 2)
cd stasis_app && npm install && node app.js

# 3. Asterisk 상태 확인
sudo asterisk -rx "pjsip show registrations"
sudo asterisk -rx "ari show apps"
```

## 환경 변수

### 파일 구조
- **루트 `.env`**: 통합 환경변수 파일 (Node.js + Python 모두 포함)
- **루트 `.env.example`**: 템플릿

> **참고**: `.env` 파일은 하나만 관리. 앱별 분리 불필요.

### Node.js (stasis_app) 전용

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ARI_URL` | `http://127.0.0.1:8088/ari` | Asterisk ARI 엔드포인트 |
| `ARI_USERNAME` | `asterisk` | ARI 인증 사용자 |
| `ARI_PASSWORD` | (필수) | ARI 인증 비밀번호 |
| `EXTERNAL_HOST` | `127.0.0.1` | ExternalMedia UDP 호스트 |
| `CUSTOMER_PORT` | `12345` | 고객 음성 UDP 포트 |
| `AGENT_PORT` | `12346` | 상담사 음성 UDP 포트 |

### Python (aicc_pipeline) 전용

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `AICC_WS_URL` | (필수) | WebSocket 엔드포인트 |
| `AICC_CUSTOMER_PORT` | `12345` | 고객 음성 UDP 포트 |
| `AICC_AGENT_PORT` | `12346` | 상담사 음성 UDP 포트 |
| `AICC_VAD_THRESHOLD` | `0.5` | VAD 임계값 |
| `AICC_STT_LANGUAGE` | `ko-KR` | STT 언어 |
| `GOOGLE_APPLICATION_CREDENTIALS` | - | GCP 인증 JSON 경로 |

### 공유 변수 (포트 동기화 필요)

```bash
# Node.js와 Python이 같은 포트를 사용해야 함
CUSTOMER_PORT=12345        # Node.js용
AICC_CUSTOMER_PORT=12345   # Python용 (동일 값)

AGENT_PORT=12346           # Node.js용
AICC_AGENT_PORT=12346      # Python용 (동일 값)
```

### 로컬 개발 실행

```bash
# dotenv 미사용이므로 직접 source 필요
source .env
node stasis_app/app.js &
python -m aicc_pipeline
```

### Docker 환경
docker-compose.yml이 루트 `.env`를 자동으로 읽어서 컨테이너에 전달.

## WebSocket 메시지 타입

```json
// 통화 시작
{"type": "metadata_start", "call_id": "uuid", "customer_number": "...", "agent_id": "..."}

// 턴 완료
{"type": "turn_complete", "call_id": "uuid", "speaker": "customer|agent",
 "transcript": "...", "decision": "complete|incomplete", "fusion_score": 0.95}

// 통화 종료
{"type": "metadata_end", "call_id": "uuid", "total_duration": 120.5, "turn_count": 15}
```

## 주요 의존성

- **Node.js**: `ari-client` (Asterisk ARI 클라이언트)
- **Python**: `websockets`, `google-cloud-speech`, `kiwipiepy`, `numpy`
- **Optional**: `pipecat-ai[silero]` (고급 VAD)

## 개발 시 참고

1. **오디오 포맷**: Asterisk ExternalMedia는 ulaw 8kHz → Pipeline에서 PCM 16kHz로 변환
2. **VAD**: Pipecat/Silero 없으면 에너지 기반 간단 VAD fallback
3. **턴 판정**: 형태소 분석(kiwipiepy)으로 한국어 문장 완결성 판단
4. **STT**: Google Cloud Speech V2 API, `ko-KR` 모델

## 트러블슈팅

```bash
# RTP 패킷 안 오면
sudo asterisk -rx "rtp set debug on"

# ARI 연결 실패
sudo asterisk -rx "http show status"
netstat -tlnp | grep 8088

# WebSocket 연결 확인
# aicc_pipeline.py의 ws_url 설정 확인
```
