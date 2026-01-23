# AICC Pipeline 모듈화 변경 기록

## 버전: 2.0.0
## 날짜: 2025-01-23

---

## 1. 구조 변경

### 기존
```
aicc_pipeline.py (821줄 단일 파일)
```

### 변경 후
```
aicc_pipeline/
├── __init__.py
├── __main__.py
├── requirements.txt
├── .env.example
├── config/settings.py
├── audio/rtp.py, converter.py
├── vad/detector.py
├── stt/google_stt.py
├── turn/morpheme.py, detector.py
├── websocket/manager.py
└── core/udp_receiver.py, pipeline.py
```

---

## 2. 모듈별 변경 상세

### 2.1 config/settings.py

**기존 코드 (aicc_pipeline.py:74-101)**
```python
@dataclass
class PipelineConfig:
    customer_port: int = 12345
    agent_port: int = 12346
    ws_url: str = "wss://51ac652b2c5c.ngrok-free.app/api/v1/agent/check"  # 하드코딩
    ws_urls: List[str] = field(default_factory=lambda: [
        "wss://51ac652b2c5c.ngrok-free.app/api/v1/agent/check",  # 하드코딩
    ])
```

**변경 후**
```python
@dataclass
class PipelineConfig:
    customer_port: int = field(
        default_factory=lambda: int(os.getenv("AICC_CUSTOMER_PORT", "12345"))
    )
    ws_urls: List[str] = field(default_factory=_get_ws_urls_from_env)
    # 모든 설정이 환경변수에서 로드됨
```

**변경 이유**: URL 하드코딩 문제 해결, 배포 환경별 설정 분리

---

### 2.2 turn/detector.py

**기존 코드 (aicc_pipeline.py:512-519)**
```python
# Simple fusion (without Smart Turn for now)
if morpheme_score >= 0.7 or duration > 2.0:  # 단순 OR 조건
    decision = TurnDecision.COMPLETE
else:
    decision = TurnDecision.INCOMPLETE
```

**변경 후**
```python
# 가중치 융합 판정
fusion_score = (
    self.morpheme_weight * morpheme_score +   # 0.6
    self.duration_weight * duration_score +    # 0.2
    self.silence_weight * silence_score        # 0.2
)

# duration_score 로직:
# - < 0.5초: 0.3 (너무 짧음)
# - 0.5~2초: 0.7 (적당)
# - 2~5초: 0.5 (중립)
# - > 5초: 0.4 (길면 incomplete일 가능성)

# 예외 처리
if duration > 5.0 and morpheme_score < 0.4:
    decision = TurnDecision.INCOMPLETE  # 연결어미로 끝나면 무조건 incomplete
```

**변경 이유**: 기존 단순 OR 조건은 "네" 같은 짧은 응답도 complete로 판정하는 문제, 긴 발화가 연결어미로 끝나도 complete로 판정하는 문제 있음

---

### 2.3 websocket/manager.py

**기존 코드 (aicc_pipeline.py:564-570)**
```python
class WebSocketManager:
    def __init__(self, config: PipelineConfig):
        self._queue: asyncio.Queue = asyncio.Queue()  # 무제한 크기
```

**변경 후**
```python
class WebSocketManager:
    def __init__(self, urls, queue_maxsize=1000, ...):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)

    async def send(self, event):
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            # 오래된 이벤트 드롭 + 로깅
            dropped = self._queue.get_nowait()
            self._dropped_count += 1
            self._queue.put_nowait(event)
```

**변경 이유**: WebSocket 연결 끊기면 큐에 이벤트 무한 쌓임 -> 메모리 문제

---

### 2.4 stt/google_stt.py

**기존 코드 (aicc_pipeline.py:296-331)**
```python
def get_transcript(self) -> str:
    # 동기 호출 - 블로킹!
    response = self._client.recognize(request=request)
    return transcript
```

**변경 후**
```python
async def transcribe(self, audio_bytes=None) -> TranscriptResult:
    # executor로 비동기화
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        self._executor,
        self._sync_transcribe,
        audio_bytes
    )
    return result

def _sync_transcribe(self, audio_data) -> TranscriptResult:
    # 재시도 로직 추가
    for attempt in range(self.max_retries):
        try:
            response = self._client.recognize(request=request)
            return TranscriptResult(text=transcript, ...)
        except Exception as e:
            if attempt < self.max_retries - 1:
                continue
    return TranscriptResult(text="", is_final=True)
```

**변경 이유**:
1. STT 호출이 블로킹되면 다른 오디오 처리 지연
2. STT 실패 시 빈 문자열 반환만 하고 재시도 없음

---

### 2.5 turn/morpheme.py

**기존 코드 (aicc_pipeline.py:203-255)**
- 동일한 패턴 유지

**변경 후**
- 패턴 추가: `었어요$`, `았어요$`, `드릴게요$`, `네네$` 등
- Kiwi 분석 시 SF(문장부호) 처리 개선

---

### 2.6 core/udp_receiver.py

**기존 코드 (aicc_pipeline.py:665-710)**
- `_udp_receiver()` 메서드가 pipeline 클래스 내부에 있음

**변경 후**
- 독립 클래스로 분리
- 통계 추적 추가 (packet_count, error_count)
- RTP 파싱 에러 처리 개선

---

## 3. 새로 추가된 기능

### 3.1 환경변수 기반 설정
- `AICC_WS_URL`, `AICC_WS_URL_1`, `AICC_WS_URL_2`... 다중 URL 지원
- 모든 설정값 환경변수로 오버라이드 가능

### 3.2 가중치 조정 가능한 턴 판정
- `AICC_TURN_MORPHEME_WEIGHT=0.6`
- `AICC_TURN_DURATION_WEIGHT=0.2`
- `AICC_TURN_SILENCE_WEIGHT=0.2`
- `AICC_TURN_COMPLETE_THRESHOLD=0.65`

### 3.3 WebSocket 큐 크기 제한
- `AICC_WS_QUEUE_MAXSIZE=1000`
- 드롭 카운트 로깅

### 3.4 STT 재시도 로직
- `max_retries=3` (기본값)

---

## 4. 삭제/간소화된 코드

- 하드코딩된 ngrok URL 제거
- 중복 import 정리
- 주석 처리된 코드 제거

---

## 5. 테스트 방법

```bash
# 환경변수 설정
export AICC_WS_URL="wss://YOUR_URL/api/v1/agent/check"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credentials.json"

# 실행
cd ~/aws_asterisk/python
python -m aicc_pipeline

# 테스트 체크리스트
# [ ] UDP 12345 고객 오디오 수신 확인
# [ ] UDP 12346 상담사 오디오 수신 확인
# [ ] metadata_start 이벤트 전송 확인
# [ ] turn_complete 이벤트 전송 확인
# [ ] metadata_end 이벤트 전송 확인 (Ctrl+C 시)
# [ ] WebSocket 재연결 확인 (서버 재시작 시)
```

---

## 6. 마이그레이션 가이드

1. 기존 `aicc_pipeline.py` 백업
2. 새 디렉토리 구조 배포
3. `.env` 파일 생성 (`.env.example` 참고)
4. `python -m aicc_pipeline` 으로 실행
