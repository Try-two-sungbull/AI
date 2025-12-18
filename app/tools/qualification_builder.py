"""
입찰참가자격 블록 생성 도구

구매계획서 데이터를 기반으로 입찰참가자격 블록을 자동 생성합니다.
사용자가 설명한 구조:
① G2B 기본 등록 요건
② 물품/업종 요건
③ 기업규모 요건
④ 법적 결격사유 배제
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class QualificationBuilder:
    """
    입찰참가자격 블록 생성기
    
    구매계획서에서 추출한 데이터를 기반으로
    입찰참가자격 섹션을 자동 생성합니다.
    """

    def __init__(self):
        # 나라장터 업종 DB (실제로는 API 호출 필요)
        self.industry_db = {
            "4608": {
                "name": "고압가스판매업",
                "law": "고압가스안전관리법",
                "section": "제4조"
            }
            # 실제로는 나라장터 API에서 조회
        }

    def build_qualification_block(
        self,
        extracted_data: Dict[str, Any],
        classification: Dict[str, Any]
    ) -> str:
        """
        입찰참가자격 블록 전체 생성
        
        Args:
            extracted_data: 구매계획서에서 추출한 데이터
            classification: 분류 결과 (공고 유형, 중소기업 제한 등)
        
        Returns:
            입찰참가자격 블록 마크다운 텍스트
        """
        blocks = []
        
        # ① G2B 기본 등록 요건 (고정)
        blocks.append(self._build_g2b_requirement())
        
        # ② 물품/업종 요건 (분기)
        industry_block = self._build_industry_requirement(extracted_data)
        if industry_block:
            blocks.append(industry_block)
        
        # ③ 기업규모 요건 (자동 판단)
        sme_block = self._build_sme_requirement(classification)
        if sme_block:
            blocks.append(sme_block)
        
        # ④ 법적 결격사유 (고정)
        blocks.append(self._build_legal_disqualification())
        
        return "\n\n".join(blocks)

    def _build_g2b_requirement(self) -> str:
        """
        ① G2B 기본 등록 요건 (고정 문구)
        
        Returns:
            G2B 기본 요건 텍스트
        """
        return """### ① G2B 기본 등록 요건

국가종합전자조달시스템 입찰참가자격등록규정에 따라
전자입찰서 제출 마감일 전일까지
나라장터(G2B)에 입찰참가자격을 등록한 자"""

    def _build_industry_requirement(
        self,
        extracted_data: Dict[str, Any]
    ) -> Optional[str]:
        """
        ② 물품/업종 요건 생성
        
        세부품명번호 또는 업종코드가 있으면 해당 문구 생성
        
        Args:
            extracted_data: 추출된 데이터
        
        Returns:
            업종 요건 텍스트 또는 None
        """
        parts = []
        
        # 세부품명번호가 있으면
        detail_item_codes = extracted_data.get("detail_item_codes", [])
        if detail_item_codes:
            for code in detail_item_codes:
                parts.append(f"- 세부품명번호: {code}에 해당하는 물품을 공급할 수 있는 자")
        
        # 업종코드가 있으면
        industry_codes = extracted_data.get("industry_codes", [])
        if industry_codes:
            for code in industry_codes:
                industry_info = self._get_industry_info(code)
                if industry_info:
                    parts.append(
                        f"- 「{industry_info['law']}」 {industry_info['section']}에 의한 "
                        f"{industry_info['name']}(업종코드: {code})"
                    )
                else:
                    # DB에 없으면 기본 형식
                    parts.append(f"- 업종코드 {code}에 해당하는 업종을 영위하는 자")
        
        if not parts:
            return None
        
        return "### ② 물품/업종 요건\n\n" + "\n".join(parts)

    def _build_sme_requirement(
        self,
        classification: Dict[str, Any]
    ) -> Optional[str]:
        """
        ③ 기업규모 요건 생성
        
        분류 결과의 중소기업 제한 정보를 기반으로 생성
        
        Args:
            classification: 분류 결과
        
        Returns:
            기업규모 요건 텍스트 또는 None
        """
        sme_restriction = classification.get("sme_restriction", "")
        
        if not sme_restriction or sme_restriction == "없음":
            return None
        
        restriction_map = {
            "소기업_소상공인": "소기업 또는 소상공인",
            "중소기업_소상공인": "중소기업 또는 소상공인"
        }
        
        restriction_text = restriction_map.get(
            sme_restriction,
            sme_restriction
        )
        
        return f"""### ③ 기업규모 요건

{restriction_text}에 해당하는 기업만 입찰 참가 가능"""

    def _build_legal_disqualification(self) -> str:
        """
        ④ 법적 결격사유 배제 (고정 문구)
        
        Returns:
            법적 결격사유 텍스트
        """
        return """### ④ 법적 결격사유 배제

국가계약법 제27조 및 동법 시행령 제37조에 따른 입찰 참가자격이 있는 자
- 조세포탈, 부정수급 등 법령 위반으로 제재를 받은 자는 제외
- 부정당업자로 등록된 자는 제외"""

    def _get_industry_info(self, industry_code: str) -> Optional[Dict[str, str]]:
        """
        업종코드로 업종 정보 조회
        
        실제로는 나라장터 API 호출 필요
        현재는 내부 DB에서 조회
        
        Args:
            industry_code: 업종코드
        
        Returns:
            업종 정보 딕셔너리 또는 None
        """
        return self.industry_db.get(industry_code)

    def build_other_conditions_block(
        self,
        extracted_data: Dict[str, Any]
    ) -> str:
        """
        기타 조건 블록 생성
        
        공동계약, 지역제한 등
        
        Args:
            extracted_data: 추출된 데이터
        
        Returns:
            기타 조건 블록 텍스트
        """
        conditions = []
        
        # 공동계약 여부
        is_joint_contract = extracted_data.get("is_joint_contract", False)
        if is_joint_contract:
            conditions.append(
                "### 공동계약\n\n"
                "본 계약은 공동이행이 가능하며, 공동계약 체결을 원하는 경우 "
                "입찰서에 공동이행 계약서를 첨부하여 제출하여야 합니다."
            )
        else:
            conditions.append("### 공동계약\n\n해당 없음")
        
        # 지역제한 여부
        has_region_restriction = extracted_data.get("has_region_restriction", False)
        if has_region_restriction:
            region = extracted_data.get("restricted_region", "")
            conditions.append(
                f"### 지역제한\n\n"
                f"납품지가 {region}에 위치한 업체만 입찰 참가 가능합니다."
            )
        else:
            conditions.append("### 지역제한\n\n해당 없음")
        
        return "\n\n".join(conditions)


# Singleton 인스턴스
_qualification_builder = None


def get_qualification_builder() -> QualificationBuilder:
    """전역 QualificationBuilder 인스턴스 반환"""
    global _qualification_builder
    if _qualification_builder is None:
        _qualification_builder = QualificationBuilder()
    return _qualification_builder


def build_qualification_block(
    extracted_data: Dict[str, Any],
    classification: Dict[str, Any]
) -> str:
    """
    입찰참가자격 블록 생성 편의 함수
    
    Args:
        extracted_data: 추출된 데이터
        classification: 분류 결과
    
    Returns:
        입찰참가자격 블록 텍스트
    """
    builder = get_qualification_builder()
    return builder.build_qualification_block(extracted_data, classification)

