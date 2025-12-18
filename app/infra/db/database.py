from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import get_settings

settings = get_settings()

# 엔진 생성 (예: postgresql+psycopg2://user:password@host:port/dbname)
# psycopg2는 connect_timeout을 connect_args에서 직접 지원하지 않으므로 제거
# 타임아웃은 pool_timeout으로 처리
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # 연결 전에 연결 상태 확인
    pool_recycle=300,  # 5분마다 연결 재사용
    pool_timeout=5,  # 풀에서 연결을 가져올 때 타임아웃 (초)
)
# 세션 생성기
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# 모델의 베이스 클래스
Base = declarative_base()

# DB 세션 의존성 주입 함수
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
