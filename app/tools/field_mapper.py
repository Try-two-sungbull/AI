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
        # 기본 매핑 규칙 (TEMPLATE_PLACEHOLDER_RULES.md 참조)
        self.field_mapping = {
            # 추출 데이터 -> 템플릿 필드 (직접 매핑)
            "project_name": "project_name",
            "item_name": "item_name",
            "estimated_amount": "total_budget_vat",  # fallback
            "total_budget_vat": "total_budget_vat",
            "contract_period": "contract_period",
            "qualification_notes": "qualification_notes",
            "procurement_type": "procurement_type",
            "delivery_deadline_days": "delivery_deadline_days",
        }
        
        # 필수 필드 목록 (누락 시 에러)
        self.required_fields = {
            "project_name",
            "item_name",
            "announcement_number",
            "announcement_date",
            "total_budget_vat",
            "procurement_type",
            "contract_period",
            "delivery_deadline_days",
            "bid_deadline",
            "opening_date",
            "award_date",
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

        # 3. 기본값 설정 (누락된 선택 필드)
        mapped_fields.update(self._set_default_values(template_placeholders, mapped_fields))

        # 4. 필수 필드 검증
        self._validate_required_fields(mapped_fields, template_placeholders)

        return mapped_fields

    def _generate_derived_fields(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        추출 데이터로부터 파생 필드 생성
        
        완성본 공고문 기준으로 모든 필수 필드 생성
        TEMPLATE_FIELD_KEYS.md 참조
        """
        derived = {}

        # 분류 결과 추출 (Rule Engine 결정값)
        classification = extracted_data.get("classification", {})
        
        # contract_method 추출 (안전장치 강화)
        contract_method = classification.get("recommended_type") or classification.get("contract_method")
        
        # classification이 없거나 contract_method가 없으면 procurement_method_raw에서 추론
        if not contract_method:
            procurement_method_raw = extracted_data.get("procurement_method_raw", "")
            if "소액수의" in procurement_method_raw or "소액" in procurement_method_raw:
                contract_method = "소액수의"
            elif "적격심사" in procurement_method_raw or "적격" in procurement_method_raw:
                contract_method = "적격심사"
            else:
                # 금액 기반으로 판단 (fallback)
                total_budget = extracted_data.get("total_budget_vat") or extracted_data.get("estimated_amount", 0)
                estimated_price_exc_vat = total_budget / 1.1 if total_budget > 0 else 0
                if estimated_price_exc_vat <= 100_000_000:  # 1억원 이하
                    contract_method = "소액수의"
                else:
                    contract_method = "적격심사"
        
        applied_annex = classification.get("applied_annex")
        sme_restriction = classification.get("sme_restriction", "")
        contract_nature = classification.get("contract_nature", {})
        procurement_method_raw = extracted_data.get("procurement_method_raw", "")

        # ===== 1. 입찰에 부치는 사항 =====
        
        # 날짜 관련 필드
        today = datetime.now()
        derived["announcement_date"] = today.strftime("%Y년 %m월 %d일")
        derived["announcement_number"] = f"공고 제{today.year}-{today.month:02d}-{today.day:02d}호"
        
        # 공고명 (구매계획서의 item_name 또는 project_name)
        derived["announcement_name"] = extracted_data.get("item_name") or extracted_data.get("project_name", "")
        
        # 용역기간 (계약기간 또는 납품기한)
        contract_period = extracted_data.get("contract_period", "")
        delivery_days = extracted_data.get("delivery_deadline_days")
        if delivery_days:
            derived["service_period"] = f"계약후 {delivery_days}일"
        elif contract_period:
            derived["service_period"] = contract_period
        else:
            derived["service_period"] = "계약후 120일"  # 기본값
        
        # 예산액 (부가세 포함)
        total_budget = extracted_data.get("total_budget_vat", 0)
        if isinstance(total_budget, (int, float)):
            derived["budget_amount"] = f"{total_budget:,.0f}원 (부가가치세, 배송비 포함)"
        else:
            derived["budget_amount"] = str(total_budget)
        
        # 구매범위
        item_name = extracted_data.get("item_name", "")
        derived["purchase_scope"] = f"물품규격서 및 붙임 참조" if item_name else "물품규격서 참조"
        
        # 전자입찰서 제출기간 (공고 방식에 따라 계산)
        if contract_method == "소액수의":
            # 소액수의: 3일 (공휴일 제외, 단순화: 3일)
            bid_start = today + timedelta(days=1)
            bid_end = today + timedelta(days=3)
        else:
            # 적격심사: 7일
            bid_start = today + timedelta(days=1)
            bid_end = today + timedelta(days=7)
        
        derived["bid_submission_start"] = bid_start.strftime("%Y. %m. %d.(09:00)")
        derived["bid_submission_end"] = bid_end.strftime("%Y. %m. %d.(10:00)")
        derived["bid_submission_period"] = f"{derived['bid_submission_start']} ~ {derived['bid_submission_end']}"
        
        # 개찰일시 및 장소
        opening_datetime = bid_end + timedelta(days=1)
        derived["opening_datetime"] = opening_datetime.strftime("%Y. %m. %d.(11:00)")
        derived["opening_location"] = "국가종합전자조달시스템(나라장터)"
        
        # 하위 호환성 (기존 키)
        derived["bid_deadline"] = derived["bid_submission_end"]
        derived["opening_date"] = derived["opening_datetime"]
        award_date = opening_datetime + timedelta(days=7)
        derived["award_date"] = award_date.strftime("%Y년 %m월 %d일")

        # ===== 2. 견적(입찰) 및 계약방식 =====
        
        # 계약 방법 상세 문구 생성
        if contract_method == "소액수의":
            derived["contract_method_detail"] = "소액수의(총액, 전자) 대상입니다."
        elif "일반경쟁" in procurement_method_raw or not procurement_method_raw:
            procurement_type = extracted_data.get("procurement_type", "용역")
            derived["contract_method_detail"] = f"일반경쟁(총액), 전자입찰대상 {procurement_type}입니다."
        elif "제한경쟁" in procurement_method_raw:
            procurement_type = extracted_data.get("procurement_type", "용역")
            derived["contract_method_detail"] = f"제한경쟁(총액), 전자입찰대상 {procurement_type}입니다."
        else:
            derived["contract_method_detail"] = f"{procurement_method_raw}, 전자입찰대상입니다."
        
        # 적격심사 대상 문구 생성 (별표에 따라)
        # contract_method가 없거나 불명확한 경우 기본값 처리
        if not contract_method or contract_method == "":
            # procurement_method_raw에서 추론 시도
            if "소액수의" in procurement_method_raw or "소액" in procurement_method_raw:
                contract_method = "소액수의"
            elif "적격심사" in procurement_method_raw or "적격" in procurement_method_raw:
                contract_method = "적격심사"
            else:
                # 기본값: 적격심사
                contract_method = "적격심사"
        
        if contract_method == "적격심사":
            if applied_annex == "별표1":
                annex_text = "추정가격이 10억원 이상인 물품 제조입찰 : [별표1]"
            elif applied_annex == "별표2":
                annex_text = "추정가격이 고시금액 이상 10억원 미만인 물품 제조입찰, 추정가격이 고시금액 이상인 물품 구매입찰 : [별표2]"
            elif applied_annex == "별표3":
                annex_text = "추정가격이 고시금액 미만인 물품 제조 또는 구매 입찰 : [별표3]"
            else:
                annex_text = "추정가격 고시금액 미만인 물품 제조 또는 구매입찰 적용"
            
            derived["qualification_review_target"] = (
                f"적격심사대상 물품입니다. "
                f"[우리공단 물품구매 적격심사 세부기준 [{applied_annex or '별표3'}] {annex_text}]"
            )
            derived["integrity_pledge_target"] = "청렴계약이행 서약제 대상입니다."
        elif contract_method == "소액수의":
            # 소액수의
            derived["qualification_review_target"] = "적격심사 제외대상입니다."
            derived["integrity_pledge_target"] = "청렴계약이행 서약제 대상입니다."
        else:
            # 알 수 없는 경우 기본값 (안전장치)
            derived["qualification_review_target"] = "적격심사 제외대상입니다."
            derived["integrity_pledge_target"] = "청렴계약이행 서약제 대상입니다."
        
        # ===== 3. 입찰참가자격 =====
        
        # G2B 등록 요건 (고정값)
        derived["g2b_registration_requirement"] = (
            "국가종합전자조달시스템 입찰참가자격등록규정에 따라 "
            "전자입찰서 제출 마감일 전일까지 나라장터(G2B)에 입찰참가자격을 등록한 자"
        )
        
        # 세부품명번호 (구매계획서에서 추출)
        detail_item_codes = extracted_data.get("detail_item_codes", [])
        if detail_item_codes:
            # 실제로는 나라장터 API에서 품명 조회 필요
            code = detail_item_codes[0]
            derived["detail_item_code_with_name"] = (
                f"[세부품명번호: {code}(품명)] 제조 또는 공급물품으로 등록된 자"
            )
        else:
            derived["detail_item_code_with_name"] = ""
        
        # 업종코드 (구매계획서에서 추출)
        industry_codes = extracted_data.get("industry_codes", [])
        if industry_codes:
            # 실제로는 나라장터 API에서 업종명 조회 필요
            code = industry_codes[0]
            derived["industry_code_with_name"] = (
                f"「법령명」 조항에 의한 업종명(업종코드: {code})"
            )
        else:
            derived["industry_code_with_name"] = ""
        
        # 중소기업 제한 상세 문구
        if sme_restriction == "소기업_소상공인":
            derived["sme_restriction_detail"] = (
                "「중소기업기본법」 제2조에 따른 소기업 또는 "
                "「소상공인 보호 및 지원에 관한 법률」제2조에 따른 소상공인"
            )
        elif sme_restriction == "중소기업_소상공인":
            derived["sme_restriction_detail"] = (
                "「중소기업기본법」 제2조에 따른 중소기업 또는 "
                "「소상공인 보호 및 지원에 관한 법률」제2조에 따른 소상공인"
            )
        else:
            derived["sme_restriction_detail"] = ""
        
        # 법적 결격사유 (고정값)
        derived["legal_disqualification"] = (
            "「국가를 당사자로 하는 계약에 관한 법률」제27조(부정당업자의 입찰참가 자격제한)에 "
            "해당되지 아니한 업체"
        )
        derived["tax_evasion_pledge"] = (
            "「국가를 당사자로 하는 계약에 관한 법률」제27조의5 및 같은 법 시행령 제12조제3항에 따라 "
            "'조세포탈 등을 한 자'로서 유죄판결이 확정된 날부터 2년이 지나지 아니한 자는 입찰에 참여할 수 없습니다."
        )
        
        # ===== 4. 공동계약 =====
        is_joint = extracted_data.get("is_joint_contract", False)
        if is_joint:
            derived["joint_contract_status"] = "공동이행 방식 허용"
            derived["joint_contract_details"] = (
                "단독 또는 공동이행방식으로만 입찰참여가 가능하며, "
                "공동수급체 구성원은 각각 본 입찰에서 요구하는 입찰참가자격을 모두 갖추어야 합니다."
            )
        else:
            # 소액수의일 때는 "공동수급을 허용하지 않습니다" 문구 사용
            if contract_method == "소액수의":
                derived["joint_contract_status"] = "본 계약은 공동수급을 허용하지 않습니다."
            else:
                derived["joint_contract_status"] = "해당 없음"
            derived["joint_contract_details"] = ""
        
        # ===== 5. 예정가격 및 낙찰자 결정방법 =====
        if contract_method == "적격심사":
            derived["estimated_price_method"] = (
                "15개 복수 예비가격중 입찰에 참여하는 각 업체가 추첨(2개씩 선택)한 번호 중 "
                "가장 많이 선택된 4개의 예비가격을 산술 평균한 가격으로 결정합니다."
            )
            derived["award_decision_method"] = (
                "종합평점이 85점 이상인 자를 낙찰자로 결정합니다."
            )
        elif contract_method == "소액수의":
            # 소액수의: 예정가격 결정 방법 동일
            derived["estimated_price_method"] = (
                "예정가격은 예비가격기초금액기준 ±2% 범위내에서 작성된 15개 복수 예비가격 중 "
                "입찰에 참여하는 각 업체가 추첨(2개씩 선택)한 번호 중 가장 많이 선택된 4개의 예비가격을 산술평균한 가격으로 결정됩니다."
            )
            # 소액수의는 낙찰자 결정방법이 다름 (템플릿에서 직접 작성)
            derived["award_decision_method"] = ""
        else:
            derived["estimated_price_method"] = ""
            derived["award_decision_method"] = "최저가 입찰자를 낙찰자로 결정합니다."
        
        derived["same_price_handling"] = (
            "국가계약법시행령 제47조 규정에 의거 낙찰자를 결정합니다."
        )
        
        # ===== 6. 적격심사 자료제출 =====
        if contract_method == "적격심사":
            derived["qualification_submission_deadline"] = "통보받은 날로부터 5일 이내"
            derived["qualification_submission_method"] = (
                "국가종합전자조달(G2B)시스템을 통하여 통보(받은 문서함에서 확인)"
            )
        else:
            derived["qualification_submission_deadline"] = ""
            derived["qualification_submission_method"] = ""
        
        # ===== 7. 기타 필수 필드 =====
        derived["contact_department"] = extracted_data.get("contact_department", "경영지원처 계약부")
        derived["contact_person"] = extracted_data.get("contact_person", "담당자")
        derived["contact_phone"] = extracted_data.get("contact_phone", "032-590-0000")
        derived["organization"] = extracted_data.get("organization", "한국환경공단")
        
        # 하위 호환성 (기존 키)
        derived["item_name"] = derived["announcement_name"]
        if isinstance(total_budget, (int, float)):
            derived["total_budget_vat"] = f"{total_budget:,}"
        else:
            derived["total_budget_vat"] = str(total_budget)
        
        # 계약 기간 파싱
        if contract_period:
            derived["delivery_deadline_days"] = self._parse_period_to_days(contract_period)
        elif delivery_days:
            derived["delivery_deadline_days"] = delivery_days

        # 분류 결과 기반 필드 (Rule Engine 결정값 - 가드용, 템플릿에 직접 사용 안 함)
        # 참고: 이 값들은 템플릿에 하드코딩되어 있고, LLM 프롬프트에서만 가드로 사용
        derived["contract_method"] = contract_method
        if applied_annex:
            derived["applied_annex"] = applied_annex
        if sme_restriction:
            derived["sme_restriction"] = sme_restriction

        # 협상계약 전용 날짜 필드 (negotiation.md 템플릿용)
        # 참고: 템플릿 타입에 따라 조건부 생성 필요 (현재는 항상 생성)
        question_deadline = today + timedelta(days=5)
        derived["question_deadline"] = question_deadline.strftime("%Y년 %m월 %d일")
        
        answer_date = question_deadline + timedelta(days=2)
        derived["answer_date"] = answer_date.strftime("%Y년 %m월 %d일")
        
        proposal_deadline = answer_date + timedelta(days=7)
        derived["proposal_deadline"] = proposal_deadline.strftime("%Y년 %m월 %d일")
        
        evaluation_end = proposal_deadline + timedelta(days=7)
        derived["evaluation_period"] = f"{proposal_deadline.strftime('%Y년 %m월 %d일')} ~ {evaluation_end.strftime('%Y년 %m월 %d일')}"
        
        negotiation_date = proposal_deadline + timedelta(days=10)
        derived["negotiation_date"] = negotiation_date.strftime("%Y년 %m월 %d일")
        
        contract_date = negotiation_date + timedelta(days=7)
        derived["contract_date"] = contract_date.strftime("%Y년 %m월 %d일")

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

        # 기본값 정의 (TEMPLATE_PLACEHOLDER_RULES.md 참조)
        default_values = {
            "organization": "발주기관명",
            "contact_department": "담당부서",
            "contact_person": "담당자명",
            "contact_phone": "02-1234-5678",
            "contact_email": "contact@example.go.kr",
            "contact_address": "서울특별시...",
            "qualification_detail": "별도 공고 참조",
            "required_documents": "입찰공고문 참조",
            "project_scope": "별도 과업지시서 참조",
            "requirements": "별도 과업지시서 참조",
            "deliverables": "별도 과업지시서 참조",
            "technical_spec": "별도 과업지시서 참조",
            # 필수 필드 안전장치
            "qualification_review_target": "적격심사 제외대상입니다.",
            "integrity_pledge_target": "청렴계약이행 서약제 대상입니다.",
            "contract_method_detail": "일반경쟁(총액), 전자입찰대상 물품입니다.",
            # delivery_deadline_days는 파생 필드에서 처리되므로 여기서는 제외
        }

        for placeholder in template_placeholders:
            if placeholder not in mapped_fields and placeholder in default_values:
                defaults[placeholder] = default_values[placeholder]

        return defaults

    def _validate_required_fields(
        self,
        mapped_fields: Dict[str, Any],
        template_placeholders: list
    ) -> None:
        """
        필수 필드 검증

        Args:
            mapped_fields: 매핑된 필드
            template_placeholders: 템플릿의 플레이스홀더 목록

        Raises:
            ValueError: 필수 필드가 누락된 경우
        """
        # 템플릿에 실제로 사용되는 필수 필드만 검증
        missing_fields = []
        for placeholder in template_placeholders:
            if placeholder in self.required_fields:
                if placeholder not in mapped_fields or mapped_fields[placeholder] is None:
                    missing_fields.append(placeholder)

        if missing_fields:
            raise ValueError(
                f"필수 필드가 누락되었습니다: {', '.join(missing_fields)}. "
                f"템플릿 플레이스홀더 규칙(TEMPLATE_PLACEHOLDER_RULES.md)을 참조하세요."
            )

    def fill_template(
        self,
        template_content: str,
        extracted_data: Dict[str, Any]
    ) -> str:
        """
        Document Assembly: 템플릿에 추출 데이터를 채워서 반환
        
        이 메서드는 Pipeline 단계의 핵심입니다:
        - LLM이 아닌 코드가 문서를 "렌더링"합니다
        - 모든 플레이스홀더({})를 실제 값으로 치환합니다
        - 법적 판단이나 확정은 하지 않습니다 (Rule Engine이 담당)
        
        Args:
            template_content: 템플릿 원본 내용 (마크다운 형식)
            extracted_data: 추출된 데이터 (ExtractedData + Classification)

        Returns:
            데이터가 채워진 템플릿 문자열 (완성된 공고문)
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
            # 빈 문자열인 경우 (qualification_notes 등) 해당 라인 제거
            if value == "" and key == "qualification_notes":
                # qualification_notes가 빈 문자열이면 해당 라인 제거
                import re
                pattern = rf"\{re.escape(placeholder)}\s*\n?"
                filled_content = re.sub(pattern, "", filled_content)
            else:
                filled_content = filled_content.replace(placeholder, str(value))

        # 남은 플레이스홀더 처리 (안전장치)
        remaining_placeholders = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', filled_content)
        if remaining_placeholders:
            # 필수 필드에 대한 기본값 적용
            default_fallbacks = {
                "qualification_review_target": "적격심사 제외대상입니다.",
                "integrity_pledge_target": "청렴계약이행 서약제 대상입니다.",
                "contract_method_detail": "일반경쟁(총액), 전자입찰대상 물품입니다.",
            }
            
            for placeholder in set(remaining_placeholders):
                if placeholder in default_fallbacks:
                    filled_content = filled_content.replace(
                        f"{{{placeholder}}}",
                        default_fallbacks[placeholder]
                    )
                else:
                    print(f"⚠️ 경고: 다음 플레이스홀더가 채워지지 않았습니다: {placeholder}")

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
