"""
템플릿 렌더링 엔진 (보관용)

⚠️ 현재 사용되지 않음 ⚠️

이 파일은 "시스템이 자동으로 렌더링하는 방식"으로 개발되었으나,
최종적으로 "Agent가 템플릿을 학습하고 합성하는 방식"으로 변경되었습니다.

향후 필요 시 참고용으로 보관합니다.

현재 방식:
- Agent가 템플릿 JSON을 받아서 구조 학습
- 추출된 키워드로 직접 합성
- Few-Shot 예시로 문체 학습

이전 방식 (이 파일):
- 시스템이 Jinja2로 템플릿 렌더링 (90%)
- Agent가 다듬기만 수행 (10%)
"""

from typing import Dict, Any, Optional
from jinja2 import Template, Environment, StrictUndefined
from datetime import datetime, timedelta
import re

from app.models.template import (
    BiddingTemplate,
    TemplateRenderContext,
    TemplateSection,
    TemplateField
)


class TemplateRenderer:
    """
    템플릿 렌더링 엔진 (현재 미사용)
    
    Agent가 직접 템플릿을 학습하고 합성하는 방식으로 변경됨
    """

    def __init__(self):
        self.jinja_env = Environment(
            autoescape=False,
            undefined=StrictUndefined
        )
        self.jinja_env.filters['currency'] = self._format_currency
        self.jinja_env.filters['date_kr'] = self._format_date_korean

    def render(
        self,
        template: BiddingTemplate,
        context: TemplateRenderContext
    ) -> str:
        """템플릿 렌더링 (현재 미사용)"""
        full_context = self._prepare_context(template, context)
        rendered_sections = []
        
        for section in sorted(template.sections, key=lambda s: s.order):
            if section.is_required or self._should_include_optional_section(section, full_context):
                rendered_section = self._render_section(section, full_context)
                rendered_sections.append(rendered_section)

        return "\n\n".join(rendered_sections)

    def _prepare_context(
        self,
        template: BiddingTemplate,
        context: TemplateRenderContext
    ) -> Dict[str, Any]:
        """컨텍스트 준비"""
        full_context = {}

        for field in template.global_fields:
            if field.field_type == "fixed" and field.default_value:
                full_context[field.field_key] = field.default_value

        full_context.update(context.extracted_data)
        full_context.update(context.user_overrides)
        
        computed = self._compute_fields(context.extracted_data)
        full_context.update(computed)
        full_context.update(context.computed_fields)
        full_context = self._validate_and_transform_fields(template, full_context)

        return full_context

    def _compute_fields(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """자동 계산 필드"""
        today = datetime.now()

        computed = {
            "announcement_date": today.strftime("%Y년 %m월 %d일"),
            "announcement_date_iso": today.strftime("%Y-%m-%d"),
            "current_year": today.year,
        }

        deadline = today + timedelta(days=7)
        computed["deadline"] = deadline.strftime("%Y년 %m월 %d일")
        computed["deadline_iso"] = deadline.strftime("%Y-%m-%d")

        opening = deadline + timedelta(days=1)
        computed["opening_date"] = opening.strftime("%Y년 %m월 %d일")
        computed["opening_date_iso"] = opening.strftime("%Y-%m-%d")

        import random
        computed["announcement_number"] = f"{today.year}-{random.randint(1000, 9999)}"

        return computed

    def _validate_and_transform_fields(
        self,
        template: BiddingTemplate,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """필드 검증 및 변환"""
        validated = context.copy()

        amount_fields = ["estimated_amount", "budget", "contract_amount"]
        for field in amount_fields:
            if field in validated and validated[field]:
                validated[field] = self._format_currency(validated[field])

        return validated

    def _render_section(
        self,
        section: TemplateSection,
        context: Dict[str, Any]
    ) -> str:
        """섹션 렌더링"""
        try:
            template = self.jinja_env.from_string(section.content_template)
            rendered = template.render(**context)
            return rendered.strip()
        except Exception as e:
            return f"[섹션 '{section.section_title}' 렌더링 실패: {str(e)}]"

    def _should_include_optional_section(
        self,
        section: TemplateSection,
        context: Dict[str, Any]
    ) -> bool:
        """선택적 섹션 포함 여부"""
        if not section.fields:
            return True

        for field in section.fields:
            if field.field_key in context and context[field.field_key]:
                return True

        return False

    @staticmethod
    def _format_currency(value: Any) -> str:
        """금액 포맷팅"""
        if value is None:
            return "미정"

        try:
            amount = int(value)
            return f"{amount:,}원"
        except (ValueError, TypeError):
            return str(value)

    @staticmethod
    def _format_date_korean(value: Any) -> str:
        """날짜 한국어 포맷팅"""
        if isinstance(value, datetime):
            return value.strftime("%Y년 %m월 %d일")
        return str(value)


class TemplateValidator:
    """템플릿 검증 (현재 미사용)"""

    @staticmethod
    def validate_rendered_document(
        template: BiddingTemplate,
        rendered_doc: str,
        context: TemplateRenderContext
    ) -> Dict[str, Any]:
        """렌더링된 문서 검증"""
        issues = []
        missing_fields = []

        for field in template.global_fields:
            if field.required:
                field_key = field.field_key
                if field_key not in context.extracted_data and field_key not in context.user_overrides:
                    missing_fields.append(field_key)

        placeholders = re.findall(r'\{\{([^}]+)\}\}', rendered_doc)
        if placeholders:
            issues.append(f"미치환 변수 발견: {', '.join(placeholders)}")

        return {
            "is_valid": len(missing_fields) == 0 and len(issues) == 0,
            "missing_fields": missing_fields,
            "warnings": issues
        }
