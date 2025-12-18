from typing import Literal, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class AgentState(BaseModel):
    """
    에이전트 상태 모델

    Agent Loop를 따라 상태 전이를 관리합니다.
    Observe → Decide → Act → Validate → Iterate
    """

    # 상태 식별자
    session_id: str = Field(..., description="세션 고유 ID")

    # 현재 단계
    step: Literal[
        "upload",      # 문서 업로드
        "extract",     # 정보 추출
        "classify",    # 공고 유형 분류
        "generate",    # 공고문 생성
        "validate",    # 법령 검증
        "revise",      # 수정
        "complete"     # 완료
    ] = Field(default="upload", description="현재 에이전트 단계")

    # 재시도 관리
    retry_count: int = Field(default=0, ge=0, le=3, description="재시도 횟수")
    max_retry: int = Field(default=2, description="최대 재시도 횟수")

    # 에러 추적
    last_error: Optional[str] = Field(default=None, description="마지막 에러 메시지")
    error_history: list[str] = Field(default_factory=list, description="에러 이력")

    # 템플릿 선택
    selected_template_id: Optional[str] = Field(default=None, description="선택된 템플릿 ID")

    # 데이터 저장
    raw_text: Optional[str] = Field(default=None, description="원본 문서 텍스트")
    file_content_base64: Optional[str] = Field(default=None, description="Base64 인코딩된 파일 내용 (HWP 등 특수 파일용)")
    file_name: Optional[str] = Field(default=None, description="파일명")
    extracted_data: Optional[dict] = Field(default=None, description="추출된 데이터")
    classification: Optional[dict] = Field(default=None, description="분류 결과")
    generated_document: Optional[str] = Field(default=None, description="생성된 공고문")
    validation_issues: list[dict] = Field(default_factory=list, description="검증 이슈 목록")

    # 메타데이터
    created_at: datetime = Field(default_factory=datetime.now, description="생성 시간")
    updated_at: datetime = Field(default_factory=datetime.now, description="수정 시간")

    # 사용자 피드백
    user_feedback: Optional[str] = Field(default=None, description="사용자 피드백")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "abc123",
                "step": "extract",
                "retry_count": 0,
                "max_retry": 2,
                "last_error": None,
                "selected_template_id": "template_001"
            }
        }

    def can_retry(self) -> bool:
        """재시도 가능 여부 확인"""
        return self.retry_count < self.max_retry

    def increment_retry(self) -> None:
        """재시도 횟수 증가"""
        self.retry_count += 1
        self.updated_at = datetime.now()

    def add_error(self, error: str) -> None:
        """에러 추가"""
        self.last_error = error
        self.error_history.append(f"{datetime.now().isoformat()}: {error}")
        self.updated_at = datetime.now()

    def transition_to(self, next_step: str) -> None:
        """다음 단계로 전이"""
        self.step = next_step
        self.updated_at = datetime.now()

    def reset_retry(self) -> None:
        """재시도 횟수 초기화"""
        self.retry_count = 0
        self.updated_at = datetime.now()
