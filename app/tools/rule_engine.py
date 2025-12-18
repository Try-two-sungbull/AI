"""
Rule Engine for Procurement Classification

국가계약법 기반 공고 유형 분류 규칙 엔진
"""

from typing import Dict, Any, Tuple, Optional
from app.models.schemas import ExtractedData, ClassificationResult


class ProcurementRuleEngine:
    """
    조달 분류 규칙 엔진

    국가계약법 및 시행령에 기반한 자동 분류 로직
    """

    # 금액 기준 (원) - 사용자 요구사항 반영
    THRESHOLDS = {
        "공사": {
            "소액수의_최대": 100_000_000,  # 1억원 (소액수의 상한)
            "적격심사_최소": 100_000_001,  # 1억원 초과부터 적격심사
            "별표1_최소": 1_000_000_000,   # 10억원 이상
            "별표2_최소": 230_000_000,     # 2.3억원(고시금액) 이상
            "별표3_최소": 100_000_001,     # 1억원 초과 ~ 2.3억원 미만
        },
        "용역": {
            "소액수의_최대": 100_000_000,  # 1억원
            "적격심사_최소": 100_000_001,  # 1억원 초과부터 적격심사
            "별표1_최소": 1_000_000_000,
            "별표2_최소": 230_000_000,
            "별표3_최소": 100_000_001,
        },
        "물품": {
            "소액수의_최대": 100_000_000,  # 1억원
            "적격심사_최소": 100_000_001,  # 1억원 초과부터 적격심사
            "별표1_최소": 1_000_000_000,
            "별표2_최소": 230_000_000,
            "별표3_최소": 100_000_001,
        }
    }
    
    # 중소기업 제한 기준 (기본값, 크롤링으로 업데이트됨)
    SME_THRESHOLDS = {
        "소기업_최대": 100_000_000,        # 1억원 미만 (고정)
        "중소기업_최대": 230_000_000,      # 고시금액 미만 (동적 업데이트)
    }

    def __init__(self):
        self.rules = [
            self._rule_qualification_review,
            self._rule_lowest_price,
            self._rule_negotiation
        ]
        # 고시금액 초기화 (크롤링)
        self._update_notice_amount()

    def classify(self, extracted_data: ExtractedData) -> ClassificationResult:
        """
        추출된 데이터를 기반으로 공고 유형 분류 (2단계 분류)
        
        1차 분기: 공고 방식 (소액수의/적격심사)
        2차 분기: 계약 성격 (국가계약/단가계약, 단독/공동)

        Args:
            extracted_data: 추출된 발주 정보

        Returns:
            ClassificationResult: 분류 결과
        """
        # VAT 제외 추정가격 계산
        total_budget = extracted_data.total_budget_vat or extracted_data.estimated_amount
        estimated_price_exc_vat = self._calculate_estimated_price_exc_vat(total_budget)
        
        proc_type = extracted_data.procurement_type

        # 1차 분기: 공고 방식 결정 (Rule Engine 기반)
        contract_method = self._determine_contract_method(estimated_price_exc_vat, proc_type)
        
        # 적격심사인 경우 별표 결정
        applied_annex = None
        if contract_method == "적격심사":
            applied_annex = self._determine_annex(estimated_price_exc_vat)
        
        # 중소기업 제한 결정
        sme_restriction = self._determine_sme_restriction(estimated_price_exc_vat)
        
        # 2차 분기: 계약 성격 (추출 데이터 기반)
        contract_nature = self._determine_contract_nature(extracted_data)
        
        # 최종 공고 유형 결정
        recommended_type = self._build_announcement_type(contract_method, contract_nature)
        
        reason = (
            f"추정가격 {estimated_price_exc_vat:,.0f}원 기준 "
            f"{contract_method} 선택, {contract_nature}"
        )
        
        if applied_annex:
            reason += f", {applied_annex} 적용"
        if sme_restriction != "없음":
            reason += f", {sme_restriction} 제한"

        # Reason Trace 구조화 (실 프로젝트 필수)
        reason_trace = {
            "estimated_price_exc_vat": estimated_price_exc_vat,
            "total_budget_vat": total_budget,
            "procurement_type": proc_type,
            "threshold_used": {
                "소액수의_최대": self.THRESHOLDS.get(proc_type, {}).get("소액수의_최대"),
                "별표1_최소": self.THRESHOLDS.get(proc_type, {}).get("별표1_최소"),
                "별표2_최소": self.THRESHOLDS.get(proc_type, {}).get("별표2_최소"),
                "별표3_최소": self.THRESHOLDS.get(proc_type, {}).get("별표3_최소"),
            },
            "calculation_steps": [
                f"VAT 제외 추정가격: {total_budget:,.0f} / 1.1 = {estimated_price_exc_vat:,.0f}원",
                f"공고 방식 판단: {estimated_price_exc_vat:,.0f}원 {'<=' if estimated_price_exc_vat <= self.THRESHOLDS.get(proc_type, {}).get('소액수의_최대', 0) else '>'} {self.THRESHOLDS.get(proc_type, {}).get('소액수의_최대', 0):,}원 → {contract_method}",
            ],
            "contract_nature": contract_nature,
            "applied_annex": applied_annex,
            "sme_restriction": sme_restriction,
        }
        
        if applied_annex:
            reason_trace["calculation_steps"].append(
                f"별표 결정: {estimated_price_exc_vat:,.0f}원 기준 → {applied_annex} 적용"
            )
        
        if sme_restriction != "없음":
            reason_trace["calculation_steps"].append(
                f"중소기업 제한: {estimated_price_exc_vat:,.0f}원 기준 → {sme_restriction}"
            )

        return ClassificationResult(
            recommended_type=recommended_type,
            confidence=0.95,  # Rule Engine 기반이므로 높은 신뢰도
            reason=reason,
            alternative_types=[],
            reason_trace=reason_trace
        )
    
    def _calculate_estimated_price_exc_vat(self, total_budget: float) -> float:
        """
        VAT 제외 추정가격 계산
        
        Args:
            total_budget: 총 예산 (VAT 포함 가능)
        
        Returns:
            VAT 제외 추정가격
        """
        # VAT 10% 가정 (실제로는 데이터에서 판단 필요)
        # total_budget이 VAT 포함인지 확인하는 로직 필요
        # 현재는 단순히 10% 제외
        return total_budget / 1.1
    
    def _determine_contract_method(
        self,
        estimated_price: float,
        proc_type: str
    ) -> str:
        """
        1차 분기: 공고 방식 결정
        
        Args:
            estimated_price: VAT 제외 추정가격
            proc_type: 조달 유형
        
        Returns:
            "소액수의" 또는 "적격심사"
        """
        if proc_type not in self.THRESHOLDS:
            return "적격심사"  # 기본값
        
        threshold = self.THRESHOLDS[proc_type]["소액수의_최대"]
        
        if estimated_price <= threshold:
            return "소액수의"
        else:
            return "적격심사"
    
    def _determine_annex(self, estimated_price: float) -> Optional[str]:
        """
        적격심사인 경우 적용할 별표 결정
        
        Args:
            estimated_price: VAT 제외 추정가격
        
        Returns:
            "별표1", "별표2", "별표3" 또는 None
        """
        if estimated_price >= self.THRESHOLDS["물품"]["별표1_최소"]:
            return "별표1"
        elif estimated_price >= self.THRESHOLDS["물품"]["별표2_최소"]:
            return "별표2"
        elif estimated_price >= self.THRESHOLDS["물품"]["별표3_최소"]:
            return "별표3"
        return None
    
    def _update_notice_amount(self):
        """
        기획재정부 고시금액을 크롤링하여 업데이트
        
        공고문 생성 시마다 최신 고시금액을 확인합니다.
        """
        try:
            from app.utils.notice_amount_crawler import get_latest_notice_amount
            notice_amount = get_latest_notice_amount(force_refresh=False)
            if notice_amount:
                self.SME_THRESHOLDS["중소기업_최대"] = notice_amount
                # 별표2 최소값도 업데이트
                for proc_type in self.THRESHOLDS:
                    self.THRESHOLDS[proc_type]["별표2_최소"] = notice_amount
                print(f"✅ 고시금액 업데이트: {notice_amount:,}원")
        except Exception as e:
            print(f"⚠️ 고시금액 크롤링 실패, 기본값 사용: {str(e)}")
            # 기본값 유지
    
    def _determine_sme_restriction(self, estimated_price: float) -> str:
        """
        중소기업 제한 결정
        
        규칙:
        - 1억원 미만: 소기업 제한 (구매계획서에 없어도 무조건 적용)
        - 1억원 이상 ~ 고시금액 미만: 중소기업 제한 (구매계획서에 없어도 무조건 적용)
        - 고시금액 이상: 중소기업 제한 없음
        
        Args:
            estimated_price: VAT 제외 추정가격
        
        Returns:
            "소기업_소상공인", "중소기업_소상공인", "없음"
        """
        # 고시금액 최신화 (매번 확인)
        self._update_notice_amount()
        
        notice_amount = self.SME_THRESHOLDS["중소기업_최대"]
        
        if estimated_price < self.SME_THRESHOLDS["소기업_최대"]:
            return "소기업_소상공인"
        elif estimated_price < notice_amount:
            return "중소기업_소상공인"
        else:
            return "없음"
    
    def _determine_contract_nature(
        self,
        extracted_data: ExtractedData
    ) -> Dict[str, str]:
        """
        2차 분기: 계약 성격 결정
        
        Args:
            extracted_data: 추출된 데이터
        
        Returns:
            계약 성격 딕셔너리
            {
                "contract_type": "국가계약" 또는 "단가계약",
                "execution_type": "단독" 또는 "공동"
            }
        """
        # 계약 유형 판단 (구매계획서에 명시되어 있으면 그대로 사용)
        contract_type = "국가계약"  # 기본값
        if extracted_data.procurement_method_raw:
            if "단가" in extracted_data.procurement_method_raw:
                contract_type = "단가계약"
        
        # 공동계약 여부
        execution_type = "단독"
        if extracted_data.is_joint_contract:
            execution_type = "공동"
        
        return {
            "contract_type": contract_type,
            "execution_type": execution_type
        }
    
    def _build_announcement_type(
        self,
        contract_method: str,
        contract_nature: Dict[str, str]
    ) -> str:
        """
        공고 방식 + 계약 성격 조합으로 최종 공고 유형 결정
        
        Args:
            contract_method: 공고 방식 (소액수의/적격심사)
            contract_nature: 계약 성격
        
        Returns:
            최종 공고 유형 문자열
        """
        # 기본 공고 유형
        base_type = contract_method
        
        # 계약 성격에 따른 세부 분류 (필요시 확장)
        # 현재는 기본 유형만 반환
        return base_type

    def _rule_qualification_review(
        self,
        amount: float,
        proc_type: str,
        data: ExtractedData
    ) -> Tuple[str, float, str]:
        """
        적격심사 규칙

        국가계약법 시행령 제42조:
        - 추정가격 3억원 이상 공사
        - 추정가격 2억원 이상 용역
        - 추정가격 5억원 이상 물품
        """
        rule_type = "적격심사"

        if proc_type not in self.THRESHOLDS:
            return rule_type, 0.0, "조달 유형 불명확"

        threshold = self.THRESHOLDS[proc_type]["적격심사_최소"]

        if amount >= threshold:
            confidence = 0.9
            reason = f"{proc_type} {amount:,.0f}원으로 적격심사 기준({threshold:,.0f}원) 이상"
        elif amount >= threshold * 0.7:
            confidence = 0.6
            reason = f"적격심사 기준에 근접 ({amount:,.0f}원)"
        else:
            confidence = 0.2
            reason = "금액이 적격심사 기준 미만"

        # 기술력 중요 여부 확인
        if data.qualification and data.qualification.technical_requirements:
            confidence = min(confidence + 0.1, 1.0)
            reason += " (기술력 요건 있음)"

        return rule_type, confidence, reason

    def _rule_lowest_price(
        self,
        amount: float,
        proc_type: str,
        data: ExtractedData
    ) -> Tuple[str, float, str]:
        """
        최저가 낙찰 규칙

        일반적인 물품/공사에 적용
        """
        rule_type = "최저가낙찰"

        if proc_type not in self.THRESHOLDS:
            return rule_type, 0.0, "조달 유형 불명확"

        threshold = self.THRESHOLDS[proc_type]["최저가_최대"]

        if amount < threshold:
            if proc_type == "물품":
                confidence = 0.85
                reason = f"{proc_type} {amount:,.0f}원으로 최저가 낙찰 적합"
            else:
                confidence = 0.7
                reason = f"금액({amount:,.0f}원)이 적격심사 기준 미만"
        else:
            confidence = 0.3
            reason = "금액이 높아 적격심사 권장"

        # 단순 물품인 경우 신뢰도 증가
        if proc_type == "물품" and not (data.qualification and data.qualification.technical_requirements):
            confidence = min(confidence + 0.1, 1.0)
            reason += " (단순 물품)"

        return rule_type, confidence, reason

    def _rule_negotiation(
        self,
        amount: float,
        proc_type: str,
        data: ExtractedData
    ) -> Tuple[str, float, str]:
        """
        협상에 의한 계약 규칙

        국가계약법 제26조:
        - 특수한 기술이 필요한 경우
        - 긴급한 경우
        - 경쟁 입찰이 곤란한 경우
        """
        rule_type = "협상계약"

        confidence = 0.1  # 기본값은 낮음
        reason = "일반적인 경우 경쟁입찰 우선"

        # 특수 기술 요구
        if data.qualification and data.qualification.technical_requirements:
            if "특수" in data.qualification.technical_requirements or "전문" in data.qualification.technical_requirements:
                confidence = 0.7
                reason = "특수 기술 요구사항 있음"

        # 용역이면서 고도의 전문성 필요
        if proc_type == "용역":
            if data.qualification_notes and ("전문" in data.qualification_notes or "특수" in data.qualification_notes):
                confidence = max(confidence, 0.6)
                reason = "전문 용역으로 협상계약 고려 가능"

        # 긴급 납품
        if data.delivery_deadline_days and data.delivery_deadline_days < 30:
            confidence = max(confidence, 0.5)
            reason += " (긴급 납품)"

        return rule_type, confidence, reason


# Singleton 인스턴스
_rule_engine = None


def get_rule_engine() -> ProcurementRuleEngine:
    """전역 Rule Engine 인스턴스 반환"""
    global _rule_engine
    if _rule_engine is None:
        _rule_engine = ProcurementRuleEngine()
    return _rule_engine


def classify_procurement(extracted_data: ExtractedData) -> ClassificationResult:
    """
    조달 유형 분류 편의 함수

    Args:
        extracted_data: 추출된 데이터

    Returns:
        ClassificationResult: 분류 결과
    """
    engine = get_rule_engine()
    return engine.classify(extracted_data)
