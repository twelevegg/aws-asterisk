# AWS Asterisk + Linphone UDP Packet Capture POC

AWS EC2에서 Asterisk PBX와 Linphone SIP 계정을 연동하여 통화 시 UDP(RTP) 패킷을 캡처하는 POC입니다.

## 아키텍처

```
┌──────────────────┐     SIP/RTP      ┌─────────────────────────────────────────┐
│   Linphone App   │ ◄──────────────► │              AWS EC2                    │
│  (Test Caller)   │                  │  ┌─────────────────────────────────┐    │
└──────────────────┘                  │  │         Asterisk PBX            │    │
                                      │  │  - pjsip.conf (Linphone 등록)   │    │
                                      │  │  - extensions.conf (Stasis)     │    │
                                      │  └──────────────┬──────────────────┘    │
                                      │                 │ ARI                   │
                                      │                 ▼                       │
                                      │  ┌─────────────────────────────────┐    │
                                      │  │      Stasis App (Node.js)       │    │
                                      │  │  - ExternalMedia 채널 생성      │    │
                                      │  │  - 믹싱 브릿지 연결             │    │
                                      │  └──────────────┬──────────────────┘    │
                                      │                 │ RTP (UDP)             │
                                      │                 ▼                       │
                                      │  ┌─────────────────────────────────┐    │
                                      │  │    UDP Receiver (Python)        │    │
                                      │  │  - 포트 12345 리스닝            │    │
                                      │  │  - RTP 헤더 파싱                │    │
                                      │  │  - Hexdump 출력                 │    │
                                      │  │  - .ulaw 파일 저장              │    │
                                      │  └─────────────────────────────────┘    │
                                      └─────────────────────────────────────────┘
```

## 파일 구조

```
aws_asterisk/
├── config/
│   ├── pjsip.conf           # SIP 엔드포인트 및 Linphone 등록
│   ├── extensions.conf      # 다이얼플랜 (Stasis 라우팅)
│   ├── rtp.conf             # RTP 포트 범위 설정
│   ├── ari.conf             # ARI REST API 설정
│   └── http.conf            # HTTP 서버 설정
├── stasis_app/
│   ├── app.js               # Stasis 앱 (ExternalMedia 생성)
│   └── package.json         # Node.js 의존성
├── python/
│   ├── udp_receiver.py      # UDP RTP 패킷 수신기
│   └── requirements.txt     # Python 의존성
├── deploy.sh                # EC2 배포 스크립트
└── README.md                # 이 문서
```

## 사전 요구사항

### AWS EC2
- Asterisk 20.x 설치됨
- Node.js 16+ 설치됨
- Python 3.8+ 설치됨

### Security Group 포트 개방
| 포트 | 프로토콜 | 용도 |
|------|----------|------|
| 5060 | UDP | SIP 시그널링 |
| 8088 | TCP | ARI HTTP/WebSocket |
| 10000-20000 | UDP | RTP 미디어 |

### Linphone 계정
- 테스트 대상 계정: `youngho@sip.linphone.org`
- 발신용 별도 Linphone 계정 필요

## 설치 방법

### 1. EC2에 파일 복사

```bash
# 로컬에서 EC2로 전체 폴더 복사
scp -i your-key.pem -r aws_asterisk/ ubuntu@<EC2-IP>:~/
```

### 2. 배포 스크립트 실행

```bash
# EC2에서 실행
cd ~/aws_asterisk

# 환경변수로 비밀번호 전달
export LINPHONE_PASSWORD="your_password"
sudo -E ./deploy.sh

# 또는 인자로 전달
sudo ./deploy.sh --password "your_password"
```

### 3. Node.js 설치 (없는 경우)

```bash
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
```

## 실행 방법

### 터미널 1: Python UDP 수신기

```bash
cd ~/aws_asterisk/python
python3 udp_receiver.py

# 옵션
python3 udp_receiver.py --port 12345 --output captured_audio.ulaw
python3 udp_receiver.py --no-save  # 파일 저장 없이 출력만
```

### 터미널 2: Stasis 앱

```bash
cd ~/aws_asterisk/stasis_app
npm install
node app.js
```

### 터미널 3: Asterisk 상태 확인

```bash
# SIP 등록 상태 확인
sudo asterisk -rx "pjsip show registrations"

# ARI 상태 확인
sudo asterisk -rx "ari show apps"

# 실시간 로그 확인
sudo asterisk -rvvv
```

## 테스트 방법

### 1. 등록 상태 확인

```bash
sudo asterisk -rx "pjsip show registrations"
```

예상 출력:
```
Registration:  linphone/sip:youngho@sip.linphone.org
        Status:        Registered
```

### 2. 테스트 통화

1. **다른 Linphone 계정**에서 `youngho@sip.linphone.org`로 전화
2. Stasis 앱 로그에서 "Incoming call" 확인
3. Python 수신기에서 RTP 패킷 출력 확인

### 3. 예상 출력

**Stasis 앱:**
```
[CALL] Incoming call from: +821012345678
[CALL] Channel ID: 1234567890.0
[INFO] Channel answered
[INFO] ExternalMedia channel created
[INFO] Audio is now flowing to UDP 127.0.0.1:12345
```

**Python 수신기:**
```
[12:34:56.789] Packet #1 from 127.0.0.1:5678
  RTP [V:2 PT:0 (PCMU) Seq:1234 TS:160 SSRC:ABCD1234] Payload: 160 bytes
  Header Hex: 80 00 04 D2 00 00 00 A0 AB CD 12 34
  Payload Hex: FF FE FD FC FB FA F9 F8 F7 F6 F5 F4 F3 F2 F1 F0 EF EE ED EC ...
```

## 캡처된 오디오 재생

```bash
# FFmpeg로 WAV 변환
ffmpeg -f mulaw -ar 8000 -ac 1 -i captured_audio.ulaw captured_audio.wav

# 또는 SoX 사용
sox -t ul -r 8000 -c 1 captured_audio.ulaw captured_audio.wav

# 재생
play captured_audio.wav
```

## 문제 해결

### 등록 실패 (Registration Failed)

```bash
# 상세 로그 확인
sudo asterisk -rvvvv
# pjsip set logger on 실행

# 방화벽 확인
sudo ufw status
sudo iptables -L -n
```

### ARI 연결 실패

```bash
# HTTP 서버 상태 확인
sudo asterisk -rx "http show status"

# 포트 확인
netstat -tlnp | grep 8088
```

### RTP 패킷 수신 안 됨

1. Security Group에서 UDP 포트 확인
2. Asterisk RTP 포트 범위 확인
3. NAT 설정 확인 (`external_media_address`)

```bash
# RTP 디버그
sudo asterisk -rx "rtp set debug on"
```

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LINPHONE_PASSWORD` | - | Linphone 계정 비밀번호 (필수) |
| `EC2_PUBLIC_IP` | 자동 감지 | EC2 퍼블릭 IP |
| `ARI_URL` | `http://127.0.0.1:8088/ari` | ARI 엔드포인트 |
| `ARI_USERNAME` | `asterisk` | ARI 사용자명 |
| `ARI_PASSWORD` | `asterisk` | ARI 비밀번호 |
| `EXTERNAL_MEDIA_HOST` | `127.0.0.1` | ExternalMedia 대상 호스트 |
| `EXTERNAL_MEDIA_PORT` | `12345` | ExternalMedia 대상 포트 |

## 다음 단계

1. **STT 연동**: Google Cloud Speech-to-Text로 실시간 음성 인식
2. **WebSocket 전송**: 프론트엔드로 실시간 트랜스크립트 전송
3. **양방향 통신**: ExternalMedia를 통한 TTS 응답 전송
