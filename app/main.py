from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.config import get_settings
from app.api.v1 import api_router

# 환경 변수 로드 (.env 파일 명시적 로드)
load_dotenv(override=True)  # override=True로 기존 환경 변수 덮어쓰기

# 설정 로드
settings = get_settings()

# API 키 검증 (시작 시점)
def validate_api_keys():
    """시작 시점에 API 키 검증"""
    errors = []
    
    # OpenAI API 키 필수 (Classifier, Validator 사용)
    if not settings.openai_api_key or settings.openai_api_key.strip() == "":
        errors.append("❌ OPENAI_API_KEY가 설정되지 않았습니다. (필수)")
    elif not settings.openai_api_key.startswith("sk-"):
        errors.append("⚠️ OPENAI_API_KEY 형식이 올바르지 않을 수 있습니다.")
    
    # Anthropic API 키 선택사항 (없으면 Extractor/Generator도 OpenAI 사용)
    if not settings.anthropic_api_key or settings.anthropic_api_key.strip() == "":
        print("⚠️ ANTHROPIC_API_KEY가 설정되지 않았습니다. Extractor/Generator는 OpenAI를 사용합니다.")
    elif not settings.anthropic_api_key.startswith("sk-ant-"):
        print("⚠️ ANTHROPIC_API_KEY 형식이 올바르지 않을 수 있습니다.")
    else:
        print("✅ ANTHROPIC_API_KEY 설정됨 (Extractor/Generator는 Claude 사용)")
    
    if errors:
        raise ValueError("\n".join(errors))
    
    print("✅ API 키 검증 완료")

# 시작 시점 API 키 검증
try:
    validate_api_keys()
except ValueError as e:
    print(f"\n🚨 시작 실패: {e}")
    print("\n필요한 환경 변수:")
    print("  - OPENAI_API_KEY (필수)")
    print("  - ANTHROPIC_API_KEY (선택, 없으면 OpenAI 사용)")
    raise

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
