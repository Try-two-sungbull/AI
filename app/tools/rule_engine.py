"""
Rule Engine for Procurement Classification

국가계약법 기반 공고 유형 분류 규칙 엔진
"""

from typing import Dict, Any, Tuple
from app.models.schemas import ExtractedData, ClassificationResult


class ProcurementRuleEngine:
    """
    조달 분류 규칙 엔진

    국가계약법 및 시행령에 기반한 자동 분류 로직
    """

    # 금액 기준 (원)
    THRESHOLDS = {
        "공사": {
            "적격심사_최소": 300_000_000,  # 3억원
            "최저가_최대": 300_000_000
        },
        "용역": {
            "적격심사_최소": 200_000_000,  # 2억원
            "최저가_최대": 200_000_000
        },
        "물품": {
            "적격심사_최소": 500_000_000,  # 5억원
            "최저가_최대": 500_000_000
        }
    }

    def __init__(self):
        self.rules = [
            self._rule_qualification_review,
            self._rule_lowest_price,
            self._rule_negotiation
        ]

    def classify(self, extracted_data: ExtractedData) -> ClassificationResult:
        """
        추출된 데이터를 기반으로 공고 유형 분류

        Args:
            extracted_data: 추출된 발주 정보

        Returns:
            ClassificationResult: 분류 결과
        """
        # 금액 결정
        amount = extracted_data.total_budget_vat or extracted_data.estimated_amount
        proc_type = extracted_data.procurement_type

        # 각 규칙 평가
        scores = {}
        for rule in self.rules:
            rule_type, confidence, reason = rule(amount, proc_type, extracted_data)
            scores[rule_type] = {
                "confidence": confidence,
                "reason": reason
            }

        # 최고 점수 선택
        best_type = max(scores.items(), key=lambda x: x[1]["confidence"])
        recommended_type = best_type[0]
        confidence = best_type[1]["confidence"]
        reason = best_type[1]["reason"]

        # 대안 유형 (신뢰도 0.3 이상)
        alternatives = [
            t for t, s in scores.items()
            if t != recommended_type and s["confidence"] >= 0.3
        ]

        return ClassificationResult(
            recommended_type=recommended_type,
            confidence=confidence,
            reason=reason,
            alternative_types=alternatives
        )

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
