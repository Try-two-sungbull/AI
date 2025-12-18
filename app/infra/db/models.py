from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from .database import Base

class NoticeTemplate(Base):
    __tablename__ = "notice_templates"

    id = Column(Integer, primary_key=True, index=True)
    template_type = Column(String(50), nullable=False) # 적격심사, 소액수의 등
    version = Column(String(20), default="1.0.0")
    content = Column(Text, nullable=False)  # 마크다운 전문 저장
    summary = Column(String(255))           # 변경 사항 요약
    created_at = Column(DateTime(timezone=True), server_default=func.now())
