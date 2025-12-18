from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.config import get_settings
from app.api.v1 import api_router

# 환경 변수 로드 (.env 파일 명시적 로드)
# Docker 컨테이너 내부에서는 /app/.env 경로 확인
import os
env_path = os.path.join(os.getcwd(), ".env")
if os.path.exists(env_path):
    print(f"📄 .env 파일 발견: {env_path}")
    load_dotenv(env_path, override=True)  # override=True로 기존 환경 변수 덮어쓰기
else:
    print(f"⚠️ .env 파일을 찾을 수 없습니다: {env_path}")
    print(f"   현재 작업 디렉토리: {os.getcwd()}")
    # 기본 .env 로드 시도
    load_dotenv(override=True)

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

# 환경 변수 로드 확인 (디버깅용)
print("\n" + "="*60)
print("🔍 환경 변수 로드 상태 확인")
print("="*60)
print(f"NARA_API_KEY: {'✅ 설정됨' if settings.nara_api_key and settings.nara_api_key.strip() else '❌ 설정되지 않음'}")
if settings.nara_api_key and settings.nara_api_key.strip():
    print(f"  - 길이: {len(settings.nara_api_key)}")
    print(f"  - 시작: {settings.nara_api_key[:10]}...")
print(f"NARA_BASE_URL: {settings.nara_base_url}")
print(f"DATA_GO_KR_SERVICE_KEY: {'✅ 설정됨' if settings.data_go_kr_service_key and settings.data_go_kr_service_key.strip() else '❌ 설정되지 않음'}")
print("="*60 + "\n")

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
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# OpenAPI 스키마 생성 최적화 (무한 루프 방지)
def custom_openapi():
    """OpenAPI 스키마 생성 최적화"""
    if app.openapi_schema:
        return app.openapi_schema
    
    from fastapi.openapi.utils import get_openapi
    
    # 기본 스키마 생성
    openapi_schema = get_openapi(
        title=settings.app_name,
        version=settings.app_version,
        description=app.description,
        routes=app.routes,
    )
    
    # 복잡한 Dict 타입을 단순화하여 무한 루프 방지
    def simplify_dict_schemas(schema: dict, depth: int = 0) -> dict:
        """스키마의 복잡한 Dict 타입을 단순화 (최대 깊이 제한)"""
        if depth > 10:  # 최대 깊이 제한
            return {"type": "object", "description": "Complex nested object"}
        
        if isinstance(schema, dict):
            # Dict[str, Any] 같은 복잡한 타입을 object로 단순화
            if "additionalProperties" in schema:
                prop_schema = schema["additionalProperties"]
                if isinstance(prop_schema, dict):
                    # anyOf, oneOf가 있으면 단순화
                    if "anyOf" in prop_schema or "oneOf" in prop_schema:
                        schema["additionalProperties"] = {"type": "object"}
                    elif isinstance(prop_schema, dict) and len(prop_schema) > 5:
                        # 너무 복잡한 스키마는 단순화
                        schema["additionalProperties"] = {"type": "object"}
            
            # properties가 있으면 재귀적으로 처리
            if "properties" in schema:
                for prop_name, prop_schema in schema["properties"].items():
                    if isinstance(prop_schema, dict):
                        schema["properties"][prop_name] = simplify_dict_schemas(prop_schema, depth + 1)
            
            # items가 있으면 처리
            if "items" in schema and isinstance(schema["items"], dict):
                schema["items"] = simplify_dict_schemas(schema["items"], depth + 1)
        
        return schema
    
    # 스키마 단순화 적용
    if "components" in openapi_schema and "schemas" in openapi_schema["components"]:
        for schema_name, schema_def in openapi_schema["components"]["schemas"].items():
            # reason_trace 같은 복잡한 필드 단순화
            if schema_name in ["ClassificationResult", "AgentState"]:
                if "properties" in schema_def:
                    for prop_name in ["reason_trace", "extracted_data", "classification", "validation_issues"]:
                        if prop_name in schema_def["properties"]:
                            schema_def["properties"][prop_name] = {
                                "type": "object",
                                "description": "Complex nested object",
                                "additionalProperties": True
                            }
            simplify_dict_schemas(schema_def)
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# 커스텀 OpenAPI 스키마 함수 등록
app.openapi = custom_openapi

# 데이터베이스 테이블 생성 (앱 시작 시점에 비동기로 처리)
@app.on_event("startup")
async def init_db():
    """앱 시작 시 데이터베이스 테이블 생성 (타임아웃 설정)"""
    try:
        from app.infra.db.database import Base, engine
        from sqlalchemy import text
        
        # 연결 테스트 및 테이블 생성 (타임아웃 5초로 설정됨)
        try:
            # 연결 테스트
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            # 테이블 생성
            Base.metadata.create_all(bind=engine)
            print("✅ 데이터베이스 테이블 생성 완료")
        except Exception as db_error:
            print(f"⚠️ 데이터베이스 연결 실패 (앱은 계속 실행됩니다): {str(db_error)}")
            print("⚠️ 데이터베이스 기능은 사용할 수 없습니다.")
            print(f"⚠️ DATABASE_URL 확인 필요: {settings.database_url[:50]}...")
    except Exception as e:
        print(f"⚠️ 데이터베이스 초기화 실패 (앱은 계속 실행됩니다): {str(e)}")

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
