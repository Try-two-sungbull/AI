from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.config import get_settings
from app.api.v1 import api_router

# 환경 변수 로드
load_dotenv()

# 설정 로드
settings = get_settings()

# FastAPI 앱 생성
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    ## AI Bidding Document Agent

    CrewAI 기반 입찰 공고문 자동 작성 에이전트

    ### 주요 기능
    - 발주계획서 자동 분석
    - 핵심 정보 추출
    - 공고 유형 분류
    - 공고문 자동 생성
    - 법령 검증 및 수정

    ### Agent Loop
    Observe → Decide → Act → Validate → Iterate

    ### 법적 책임
    본 시스템은 법적 판단 주체가 아닌, 문서 이해·비교·재작성·제안 역할을 수행합니다.
    최종 결정은 언제나 사용자가 합니다.
    """,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 제한 필요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# API 라우터 등록
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "AI Bidding Document Agent API",
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health_check():
    """헬스 체크"""
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
