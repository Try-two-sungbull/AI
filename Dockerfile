# Python 3.10 기반 이미지 사용
FROM python:3.10-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필수 패키지 설치
# weasyprint를 위한 시스템 라이브러리 포함
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    # weasyprint 의존성
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev \
    shared-mime-info \
    # 한글 폰트 (한국어 문서 처리용)
    fonts-nanum \
    # pdf2image를 위한 poppler-utils
    poppler-utils \
    # 기타 유틸리티
    git \
    && rm -rf /var/lib/apt/lists/*

# 비root 사용자 생성 (보안)
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# requirements.txt 복사 및 의존성 설치 (레이어 캐싱 최적화)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY --chown=appuser:appuser . .

# 비root 사용자로 전환
USER appuser

# 포트 노출
EXPOSE 8000

# 빌드 타임 인자 (환경 변수)
ARG NARA_API_KEY
ARG OPENAI_API_KEY
ARG ANTHROPIC_API_KEY
ARG SECRET_KEY
ARG DATA_GO_KR_SERVICE_KEY
ARG LAW_API_KEY

# 환경 변수 설정
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# 환경 변수 전달 (ARG에서 ENV로)
ENV NARA_API_KEY=${NARA_API_KEY}
ENV OPENAI_API_KEY=${OPENAI_API_KEY}
ENV ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
ENV SECRET_KEY=${SECRET_KEY}
ENV DATA_GO_KR_SERVICE_KEY=${DATA_GO_KR_SERVICE_KEY}
ENV LAW_API_KEY=${LAW_API_KEY}

# 애플리케이션 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
