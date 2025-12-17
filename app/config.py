"""
애플리케이션 설정
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


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
    openai_model: str = "gpt-4"

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """설정 인스턴스 반환 (캐시됨)"""
    return Settings()
