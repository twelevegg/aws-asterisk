# AICC Pipeline - AWS Asterisk

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

```bash
# .env 파일 또는 export
LINPHONE_PASSWORD=xxx              # Linphone 계정 비밀번호
WEBSOCKET_URLS=wss://...           # WebSocket 엔드포인트
GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/credentials.json
```

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

---

## AWS 인프라 정보

| 리소스 | 값 |
|--------|-----|
| **EC2 Instance ID** | `i-064d4c32c1abb08df` |
| **EC2 Public IP (Elastic IP)** | `3.36.250.255` |
| **EC2 Private IP** | `172.31.35.142` |
| **RDS Endpoint** | `asterisk-realtime-db.cvu6ye6s6u9k.ap-northeast-2.rds.amazonaws.com` |
| **RDS Database** | `asterisk` |
| **RDS Username** | `admin` |
| **VPC CIDR** | `172.31.0.0/16` |

## 세션 시작 체크리스트

**Claude Code 세션 시작 시 반드시 아래 항목을 확인할 것:**

### 1. EC2 서비스 상태 확인 (SSM으로)
```bash
# SSM 명령 실행 방법
aws ssm send-command --instance-ids i-064d4c32c1abb08df \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["systemctl status asterisk --no-pager | head -5","systemctl status stasis-app --no-pager | head -5","systemctl status aicc-pipeline --no-pager | head -5"]' \
  --output text --query "Command.CommandId"

# 결과 확인 (CommandId로)
aws ssm get-command-invocation --command-id <COMMAND_ID> --instance-id i-064d4c32c1abb08df
```

### 2. Asterisk 상태 확인
```bash
# Linphone 등록 상태
asterisk -rx "pjsip show registrations"

# Agent 등록 상태
asterisk -rx "pjsip show endpoints" | head -30

# ARI 앱 상태
asterisk -rx "ari show apps"
```

### 3. 필수 확인 항목
- [ ] Asterisk 프로세스 실행 중
- [ ] Linphone 등록 상태 = `Registered`
- [ ] Stasis App이 ARI에 연결됨
- [ ] AICC Pipeline 실행 중

## 현재 설정값 (2026-01-29 기준)

### PJSIP Transport (NAT 설정)
```ini
[transport-udp]
external_media_address=3.36.250.255
external_signaling_address=3.36.250.255
local_net=172.31.0.0/16
```

### SRTP 설정
```ini
# linphone-endpoint 및 모든 agent 동일
media_encryption=sdes
media_encryption_optimistic=yes
```

### ARI 인증
```ini
[asterisk]
password=asterisk123
```

### WebSocket URL
```
ws://ec2-54-180-116-153.ap-northeast-2.compute.amazonaws.com:8080/api/v1/agent/check
```

## 리팩토링 규칙

코드 수정 시 반드시 다음을 준수:

1. **수정 전**: 현재 서비스 상태 확인
2. **수정 후**: 서비스 재시작 및 동작 확인
3. **설정 변경 시**:
   - EC2의 `/etc/asterisk/` 파일 직접 수정
   - `asterisk -rx "pjsip reload"` 또는 Asterisk 재시작
   - RDS 변경 시 `pjsip reload`로 적용
4. **테스트**: 실제 전화 연결로 검증

## 알려진 이슈 및 제한사항

### Opus 코덱 미지원
- `codec_opus.so`가 설치되어 있지 않음 (libopus-dev 필요)
- `res_format_attr_opus.so`는 SDP 협상만 처리, 실제 인코딩/디코딩 불가
- **증상**: 통화 연결되나 **One-way audio** (한쪽만 들림)
- **해결**: 모든 endpoint에서 opus 비활성화 (alaw, ulaw, gsm만 사용)

### 허용 코덱 (현재 설정)
| Endpoint | 코덱 |
|----------|------|
| linphone-endpoint | alaw, ulaw, gsm |
| anonymous | alaw, ulaw, gsm |
| agent01~06 (RDS) | g722, ulaw, alaw, gsm |

## 빠른 상태 확인 명령어

```bash
# 전체 상태 한번에 확인 (SSM)
aws ssm send-command --instance-ids i-064d4c32c1abb08df \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["echo === Services ===","systemctl is-active asterisk stasis-app aicc-pipeline","echo === Linphone ===","asterisk -rx pjsip\\ show\\ registrations","echo === Endpoints ===","asterisk -rx pjsip\\ show\\ endpoints | grep -E \"Endpoint:|Available|Unavailable\" | head -20"]' \
  --output text --query "Command.CommandId"
```
