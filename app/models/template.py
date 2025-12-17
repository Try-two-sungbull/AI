"""
공고문 템플릿 모델

템플릿을 구조화하여 고정 부분과 가변 부분을 분리합니다.
"""

from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class TemplateField(BaseModel):
    """
    템플릿 필드 정의

    각 필드는 고정값 또는 가변값을 가질 수 있습니다.
    """
    field_key: str = Field(..., description="필드 키 (예: project_name)")
    field_type: Literal["fixed", "variable", "optional"] = Field(
        ...,
        description="fixed: 고정값, variable: 추출 데이터로 채움, optional: 선택적"
    )
    default_value: Optional[str] = Field(None, description="기본값 (fixed일 경우 사용)")
    source_key: Optional[str] = Field(None, description="추출 데이터의 소스 키")
    required: bool = Field(True, description="필수 필드 여부")
    validation_rule: Optional[str] = Field(None, description="검증 규칙 (예: 금액 형식)")
    description: Optional[str] = Field(None, description="필드 설명")


class TemplateSection(BaseModel):
    """
    템플릿 섹션 (공고문의 각 부분)
    """
    section_id: str = Field(..., description="섹션 ID")
    section_title: str = Field(..., description="섹션 제목")
    section_type: Literal["header", "body", "footer", "table"] = Field(
        default="body",
        description="섹션 유형"
    )
    order: int = Field(..., description="표시 순서")
    is_required: bool = Field(True, description="필수 섹션 여부")
    content_template: str = Field(..., description="섹션 내용 템플릿 (Jinja2 스타일)")
    fields: List[TemplateField] = Field(default_factory=list, description="섹션 내 필드들")


class BiddingTemplate(BaseModel):
    """
    입찰 공고문 템플릿 (DB 저장용)
    """
    template_id: str = Field(..., description="템플릿 고유 ID")
    template_name: str = Field(..., description="템플릿 이름 (예: 적격심사 표준)")
    announcement_type: Literal[
        "lowest_price",      # 최저가낙찰
        "qualified_bid",     # 적격심사
        "negotiation",       # 협상에 의한 계약
        "limited_compete",   # 제한경쟁입찰
    ] = Field(..., description="공고 유형")

    description: str = Field(..., description="템플릿 설명")

    # 템플릿 구조
    sections: List[TemplateSection] = Field(default_factory=list, description="템플릿 섹션들")

    # 글로벌 필드 (모든 섹션에서 사용 가능)
    global_fields: List[TemplateField] = Field(default_factory=list, description="전역 필드")

    # 메타데이터
    version: str = Field(default="1.0.0", description="템플릿 버전")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    is_active: bool = Field(default=True, description="활성화 여부")

    # 법령 기준
    applicable_laws: List[str] = Field(
        default_factory=list,
        description="적용 법령 목록"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "template_id": "qualified_bid_v1",
                "template_name": "적격심사 표준 템플릿",
                "announcement_type": "qualified_bid",
                "description": "3억원 이상 용역 적격심사 표준 양식",
                "sections": [
                    {
                        "section_id": "header",
                        "section_title": "공고 개요",
                        "order": 1,
                        "content_template": "# {{ project_name }}\n\n공고번호: {{ announcement_number }}"
                    }
                ]
            }
        }


class TemplateRenderContext(BaseModel):
    """
    템플릿 렌더링 컨텍스트

    추출된 데이터를 템플릿 필드에 매핑합니다.
    """
    template_id: str
    extracted_data: Dict[str, Any] = Field(..., description="Extractor Agent에서 추출한 데이터")
    user_overrides: Dict[str, Any] = Field(default_factory=dict, description="사용자 수동 입력값")
    computed_fields: Dict[str, Any] = Field(default_factory=dict, description="계산된 필드 (예: 오늘 날짜)")

    def get_field_value(self, field_key: str, default: Any = None) -> Any:
        """
        필드 값 조회 우선순위:
        1. user_overrides (사용자 수동 입력)
        2. extracted_data (AI 추출)
        3. computed_fields (시스템 계산)
        4. default (기본값)
        """
        if field_key in self.user_overrides:
            return self.user_overrides[field_key]
        if field_key in self.extracted_data:
            return self.extracted_data[field_key]
        if field_key in self.computed_fields:
            return self.computed_fields[field_key]
        return default
