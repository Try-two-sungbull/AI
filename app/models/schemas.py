from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class QualificationDetail(BaseModel):
    """자격 요건 세부 정보"""
    detail_item_code: Optional[str] = Field(None, description="세부 품목 코드")
    sme_restriction: Optional[str] = Field(None, description="중소기업 제한 여부")
    technical_requirements: Optional[str] = Field(None, description="기술 요건")
    license_requirements: Optional[str] = Field(None, description="면허 요건")


class ExtractedData(BaseModel):
    """
    발주계획서에서 추출된 핵심 정보

    STEP 2에서 Claude가 JSON Schema 기반으로 추출
    """
    # 기본 정보
    project_name: Optional[str] = Field(None, description="사업명")
    item_name: Optional[str] = Field(None, description="품목명")

    # 예산 정보
    estimated_amount: float = Field(0, ge=0, description="추정 금액 (원, VAT 제외)")
    total_budget_vat: Optional[float] = Field(None, ge=0, description="총 예산 (VAT 포함)")

    # 기간 정보
    contract_period: Optional[str] = Field(None, description="계약 기간")
    delivery_deadline_days: Optional[int] = Field(None, description="납품 기한 (일)")

    # 조달 정보
    procurement_type: str = Field("", description="조달 유형 (용역/공사/물품)")
    procurement_method_raw: Optional[str] = Field(None, description="조달 방법 원문 (예: 일반경쟁입찰)")
    determination_method: Optional[str] = Field(None, description="낙찰 방식 추천 (예: 적격심사)")

    # 자격 요건
    qualification_notes: str = Field("", description="자격 요건 및 특이사항")
    qualification: Optional[QualificationDetail] = Field(None, description="자격 요건 세부 정보")
    
    # 구매계획서 추가 정보 (사용자 요구사항 반영)
    detail_item_codes: List[str] = Field(default_factory=list, description="세부 품목 번호 목록")
    industry_codes: List[str] = Field(default_factory=list, description="업종코드 목록")
    is_joint_contract: bool = Field(default=False, description="공동계약 여부")
    has_region_restriction: bool = Field(default=False, description="지역제한 여부")
    restricted_region: Optional[str] = Field(None, description="제한 지역")

    class Config:
        json_schema_extra = {
            "example": {
                "item_name": "광화학유해대기물질측정망 컬럼",
                "total_budget_vat": 157580500,
                "delivery_deadline_days": 60,
                "procurement_type": "물품",
                "procurement_method_raw": "일반경쟁입찰",
                "qualification": {
                    "detail_item_code": "기체크로마토그래피칼럼",
                    "sme_restriction": None
                }
            }
        }


class ClassificationResult(BaseModel):
    """
    공고 유형 분류 결과

    STEP 3에서 Rule Engine이 국가계약법 기준으로 분류
    """
    recommended_type: str = Field(..., description="추천 공고 유형 (예: 적격심사, 최저가)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="신뢰도 (0.0 ~ 1.0)")
    reason: str = Field(..., description="추천 이유 (간단 설명)")
    alternative_types: List[str] = Field(default_factory=list, description="대안 유형들")
    
    # 실 프로젝트 필수: 판단 근거 구조화 (Reason Trace)
    reason_trace: Optional[Dict[str, Any]] = Field(
        None,
        description="판단 근거 상세 정보 (감사, 로그, UI 표시용)"
    )
    """
    reason_trace 구조 예시:
    {
        "estimated_price_exc_vat": 300000000,
        "total_budget_vat": 330000000,
        "threshold_used": {
            "소액수의_최대": 100000000,
            "별표2_최소": 230000000,
            "별표1_최소": 1000000000
        },
        "rule_source": "국가계약법 시행규칙 별표 2",
        "calculation_steps": [
            "VAT 제외 추정가격: 330,000,000 / 1.1 = 300,000,000원",
            "300,000,000 >= 230,000,000 → 별표2 적용",
            "300,000,000 >= 100,000,000 → 적격심사"
        ],
        "contract_nature": {
            "contract_type": "국가계약",
            "execution_type": "단독"
        }
    }
    """

    class Config:
        json_schema_extra = {
            "example": {
                "recommended_type": "적격심사",
                "confidence": 0.85,
                "reason": "금액 기준 및 용역 유형에 부합",
                "alternative_types": ["협상에 의한 계약"]
            }
        }

    def needs_user_confirmation(self, threshold: float = 0.6) -> bool:
        """사용자 확인이 필요한지 판단"""
        return self.confidence < threshold


class ValidationIssue(BaseModel):
    """
    법령 검증 이슈

    STEP 5에서 Claude가 RAG로 법령과 비교하여 발견한 문제
    """
    law: str = Field(..., description="관련 법령명")
    section: str = Field(..., description="조항")
    issue_type: str = Field(..., description="이슈 유형 (예: 표현 수정, 누락, 불일치)")
    current_text: str = Field("", description="현재 텍스트")
    suggestion: str = Field(..., description="수정 제안")
    severity: str = Field("medium", description="심각도 (low/medium/high)")

    class Config:
        json_schema_extra = {
            "example": {
                "law": "국가계약법",
                "section": "제27조",
                "issue_type": "표현 수정",
                "current_text": "예정가격 미만",
                "suggestion": "표현을 '예정가격 이하'로 수정 권장",
                "severity": "medium"
            }
        }


class ValidationResult(BaseModel):
    """
    법령 검증 전체 결과

    STEP 5 출력
    """
    is_valid: bool = Field(..., description="검증 통과 여부")
    issues: List[ValidationIssue] = Field(default_factory=list, description="발견된 이슈 목록")
    checked_laws: List[str] = Field(default_factory=list, description="검증한 법령 목록")
    timestamp: str = Field(..., description="검증 시각")

    class Config:
        json_schema_extra = {
            "example": {
                "is_valid": False,
                "issues": [
                    {
                        "law": "국가계약법",
                        "section": "제27조",
                        "issue_type": "표현 수정",
                        "current_text": "예정가격 미만",
                        "suggestion": "표현을 '예정가격 이하'로 수정 권장",
                        "severity": "medium"
                    }
                ],
                "checked_laws": ["국가계약법", "국가계약법 시행령"],
                "timestamp": "2024-01-01T10:00:00"
            }
        }

    def has_critical_issues(self) -> bool:
        """치명적 이슈가 있는지 확인"""
        return any(issue.severity == "high" for issue in self.issues)


class DocumentTemplate(BaseModel):
    """
    공고문 템플릿

    STEP 4에서 사용
    """
    template_id: str = Field(..., description="템플릿 ID")
    template_type: str = Field(..., description="템플릿 유형 (예: 적격심사)")
    content: str = Field(..., description="템플릿 내용 (마크다운/HTML 또는 파일 경로)")
    placeholders: List[str] = Field(default_factory=list, description="치환 필드 목록")
    template_format: Optional[str] = Field(None, description="템플릿 형식 (hwpx, pdf, md)")
    template_path: Optional[str] = Field(None, description="템플릿 파일 경로 (HWPX/PDF용)")

    class Config:
        json_schema_extra = {
            "example": {
                "template_id": "template_001",
                "template_type": "적격심사",
                "content": "# {project_name}\\n\\n예산: {estimated_amount}원",
                "placeholders": ["project_name", "estimated_amount"]
            }
        }


class UserFeedback(BaseModel):
    """
    사용자 피드백

    STEP 6에서 사람 개입 시 사용
    """
    session_id: str = Field(..., description="세션 ID")
    feedback_type: str = Field(..., description="피드백 유형 (approve/reject/modify)")
    comments: Optional[str] = Field(None, description="피드백 내용")
    modified_content: Optional[str] = Field(None, description="수정된 내용")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "abc123",
                "feedback_type": "modify",
                "comments": "계약 기간을 3개월 연장해주세요",
                "modified_content": None
            }
        }
