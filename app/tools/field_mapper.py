"""
Field Mapper Tool

구매계획서에서 추출한 데이터를 템플릿 필드에 매핑하는 도구
"""

from typing import Dict, Any
from datetime import datetime, timedelta


class FieldMapper:
    """
    추출된 데이터를 템플릿 플레이스홀더에 매핑하는 도구

    CLAUDE.md 철학:
    - 데이터 변환 및 매핑만 수행
    - 법적 판단이나 확정은 하지 않음
    """

    def __init__(self):
        # 기본 매핑 규칙
        self.field_mapping = {
            # 추출 데이터 -> 템플릿 필드
            "project_name": "project_name",
            "estimated_amount": "total_budget_vat",
            "contract_period": "contract_period",
            "qualification_notes": "qualification_notes",
            "procurement_type": "procurement_type",
        }

    def map_extracted_to_template(
        self,
        extracted_data: Dict[str, Any],
        template_placeholders: list
    ) -> Dict[str, Any]:
        """
        추출된 데이터를 템플릿 필드에 매핑

        Args:
            extracted_data: Extractor Agent가 추출한 데이터
            template_placeholders: 템플릿의 플레이스홀더 리스트

        Returns:
            매핑된 필드 딕셔너리
        """
        mapped_fields = {}

        # 1. 직접 매핑 가능한 필드
        for extracted_key, template_key in self.field_mapping.items():
            if extracted_key in extracted_data and template_key in template_placeholders:
                mapped_fields[template_key] = extracted_data[extracted_key]

        # 2. 파생 필드 생성
        mapped_fields.update(self._generate_derived_fields(extracted_data))

        # 3. 기본값 설정 (누락된 필수 필드)
        mapped_fields.update(self._set_default_values(template_placeholders, mapped_fields))

        return mapped_fields

    def _generate_derived_fields(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        추출 데이터로부터 파생 필드 생성

        예:
        - announcement_date: 현재 날짜
        - bid_deadline: 공고일 + 14일
        - opening_date: 입찰마감 + 1일
        """
        derived = {}

        # 날짜 관련 필드
        today = datetime.now()
        derived["announcement_date"] = today.strftime("%Y년 %m월 %d일")

        bid_deadline = today + timedelta(days=14)
        derived["bid_deadline"] = bid_deadline.strftime("%Y년 %m월 %d일 %H시")

        opening_date = bid_deadline + timedelta(days=1)
        derived["opening_date"] = opening_date.strftime("%Y년 %m월 %d일 %H시")

        award_date = opening_date + timedelta(days=7)
        derived["award_date"] = award_date.strftime("%Y년 %m월 %d일")

        # 공고번호 생성 (예시)
        derived["announcement_number"] = f"공고 제{today.year}-{today.month:02d}-{today.day:02d}호"

        # 금액 포맷팅
        if "estimated_amount" in extracted_data:
            amount = extracted_data["estimated_amount"]
            if isinstance(amount, (int, float)):
                derived["total_budget_vat"] = f"{amount:,}"
            else:
                derived["total_budget_vat"] = str(amount)

        # 품목명 (사업명과 동일하게 설정 - 필요시 분리)
        if "project_name" in extracted_data:
            derived["item_name"] = extracted_data["project_name"]

        # 계약 기간 파싱
        if "contract_period" in extracted_data:
            period_str = extracted_data["contract_period"]
            # "6개월" 같은 형태에서 일수 추출 시도
            derived["delivery_deadline_days"] = self._parse_period_to_days(period_str)

        return derived

    def _parse_period_to_days(self, period_str: str) -> int:
        """
        계약 기간 문자열을 일수로 변환

        예: "6개월" -> 180일, "90일" -> 90
        """
        import re

        # "N개월" 형태
        month_match = re.search(r'(\d+)\s*개월', str(period_str))
        if month_match:
            months = int(month_match.group(1))
            return months * 30

        # "N일" 형태
        day_match = re.search(r'(\d+)\s*일', str(period_str))
        if day_match:
            return int(day_match.group(1))

        # 파싱 실패 시 기본값
        return 90

    def _set_default_values(
        self,
        template_placeholders: list,
        mapped_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        누락된 필수 필드에 기본값 설정

        Args:
            template_placeholders: 템플릿의 모든 플레이스홀더
            mapped_fields: 이미 매핑된 필드

        Returns:
            기본값이 설정된 필드
        """
        defaults = {}

        # 기본값 정의
        default_values = {
            "organization": "발주기관명",
            "contact_department": "담당부서",
            "contact_person": "담당자명",
            "contact_phone": "02-1234-5678",
            "contact_email": "contact@example.go.kr",
            "qualification_detail": "별도 공고 참조",
            "required_documents": "입찰공고문 참조",
            "delivery_deadline_days": "90",
        }

        for placeholder in template_placeholders:
            if placeholder not in mapped_fields and placeholder in default_values:
                defaults[placeholder] = default_values[placeholder]

        return defaults

    def fill_template(
        self,
        template_content: str,
        extracted_data: Dict[str, Any]
    ) -> str:
        """
        템플릿에 추출 데이터를 채워서 반환

        Args:
            template_content: 템플릿 원본 내용
            extracted_data: 추출된 데이터

        Returns:
            데이터가 채워진 템플릿 문자열
        """
        import re

        # 플레이스홀더 추출
        placeholders = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', template_content)
        placeholders = list(set(placeholders))

        # 데이터 매핑
        mapped_fields = self.map_extracted_to_template(extracted_data, placeholders)

        # 템플릿 채우기
        filled_content = template_content
        for key, value in mapped_fields.items():
            placeholder = f"{{{key}}}"
            filled_content = filled_content.replace(placeholder, str(value))

        return filled_content


# Singleton 인스턴스
_field_mapper = None


def get_field_mapper() -> FieldMapper:
    """전역 FieldMapper 인스턴스 반환"""
    global _field_mapper
    if _field_mapper is None:
        _field_mapper = FieldMapper()
    return _field_mapper


def map_and_fill(template_content: str, extracted_data: Dict[str, Any]) -> str:
    """
    템플릿 채우기 편의 함수

    Args:
        template_content: 템플릿 내용
        extracted_data: 추출된 데이터

    Returns:
        채워진 템플릿
    """
    mapper = get_field_mapper()
    return mapper.fill_template(template_content, extracted_data)
