from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import get_settings

settings = get_settings()

# 엔진 생성 (예: postgresql+psycopg2://user:password@host:port/dbname)
engine = create_engine(settings.database_url)
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
