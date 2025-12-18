"""
애플리케이션 설정
"""

from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache
from typing import Optional
import os


class Settings(BaseSettings):
    """환경 변수 기반 설정"""

    # Application
    app_name: str = "AI Bidding Document Agent"
    app_version: str = "1.0.0"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # OpenAI API
    openai_api_key: str
    openai_model: str = "gpt-4"  # 환경 변수 OPENAI_MODEL로 오버라이드 가능
    openai_model_validator: str = "gpt-4o-mini"  # Validator용 모델 (환경 변수 OPENAI_MODEL_VALIDATOR로 오버라이드 가능)
    
    # Anthropic (Claude) API
    anthropic_api_key: str = ""  # Claude API 키 (선택사항, Extractor/Generator용)
    anthropic_model: str = "claude-opus-4-5-20251101"  # 환경 변수 ANTHROPIC_MODEL로 오버라이드 가능

    # Database (Optional)
    database_url: str = "sqlite:///./agent.db"

    # JWT Settings
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Agent Settings
    max_retry_count: int = 2
    confidence_threshold: float = 0.6

    # External APIs
    law_api_base_url: str = "https://www.law.go.kr/DRF"
    law_api_key: str = ""

    # 공공데이터포탈 API (업종코드 조회)
    data_go_kr_base_url: str = "https://apis.data.go.kr/1230000/ao/IndstrytyBaseLawrgltInfoService/getIndstrytyBaseLawrgltInfoList"
    data_go_kr_service_key: str = ""

    # 기획재정부 고시금액 (중소기업 제한 기준)
    # 선택적 오버라이드용 (테스트/특수 상황에서만 사용)
    # 기본값은 코드에 하드코딩되어 있으며, 크롤링으로 자동 확인됨
    # 설정하지 않으면: 크롤링 → 하드코딩 기본값 순으로 사용
    notice_amount: Optional[int] = None  # 원 단위 (예: 230000000 = 2억 3천만 원)

    @field_validator('notice_amount', mode='before')
    @classmethod
    def parse_notice_amount(cls, v):
        """빈 문자열을 None으로 변환"""
        if v == '' or v is None:
            return None
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return None
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # .env 파일을 명시적으로 로드
        case_sensitive = False
        extra = "allow"  # 추가 필드 허용




@lru_cache()
def get_settings() -> Settings:
    """설정 인스턴스 반환 (캐시됨)"""
    return Settings()
