# =============================================================================
# AICC Pipeline - Voice Processing (Python)
# =============================================================================
# Build context: 프로젝트 루트 (docker-compose.yml 위치)
# =============================================================================
FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 설치 (pydub, kiwipiepy 등에 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 파일 복사 (루트의 requirements.txt)
COPY requirements.txt ./

# Python 의존성 설치
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY python/ ./

# credentials 디렉토리 생성
RUN mkdir -p /app/credentials

# 비root 사용자로 실행
RUN useradd -m -u 1001 appuser && \
    chown -R appuser:appuser /app

USER appuser

# 실행
CMD ["python", "-m", "aicc_pipeline"]
