"""
OpenAI Validation Agent

Rule Engine 결과의 일관성을 검증하는 Agent
- 금액 ↔ 별표 ↔ 중소기업 제한 일관성 체크
- 계약 성격 ↔ 템플릿 매핑 오류 탐지
- 논리적 불일치 탐지
"""

from typing import Dict, Any, List
from openai import OpenAI
from app.config import settings


class OpenAIValidationAgent:
    """
    OpenAI 기반 Rule Engine 결과 검증 Agent
    
    역할: 기계적 검증, 논리적 불일치 탐지
    """
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if hasattr(settings, 'OPENAI_API_KEY') else None
    
    def validate_rule_engine_result(
        self,
        classification_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Rule Engine 결과의 일관성 검증
        
        Args:
            classification_result: 분류 결과
            
        Returns:
            검증 결과
        """
        if not self.client:
            # OpenAI API 키가 없으면 기본 검증만 수행
            return self._basic_validation(classification_result)
        
        # OpenAI를 통한 고급 검증
        return self._openai_validation(classification_result)
    
    def _basic_validation(
        self,
        classification_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        기본 검증 (OpenAI 없이)
        
        간단한 논리적 불일치만 체크
        """
        issues = []
        
        estimated_price = classification_result.get("estimated_price_exc_vat", 0)
        applied_annex = classification_result.get("applied_annex")
        sme_restriction = classification_result.get("sme_restriction", "")
        recommended_type = classification_result.get("recommended_type", "")
        
        # 별표 일관성 검사
        if applied_annex:
            if applied_annex == "별표1" and estimated_price < 1_000_000_000:
                issues.append({
                    "type": "별표 불일치",
                    "severity": "high",
                    "message": f"추정가격 {estimated_price:,.0f}원은 별표1 대상이 아닙니다. (10억원 이상 필요)"
                })
            elif applied_annex == "별표2" and (estimated_price < 230_000_000 or estimated_price >= 1_000_000_000):
                issues.append({
                    "type": "별표 불일치",
                    "severity": "high",
                    "message": f"추정가격 {estimated_price:,.0f}원은 별표2 대상이 아닙니다. (2.3억원 이상 10억원 미만)"
                })
            elif applied_annex == "별표3" and estimated_price < 100_000_000:
                issues.append({
                    "type": "별표 불일치",
                    "severity": "high",
                    "message": f"추정가격 {estimated_price:,.0f}원은 별표3 대상이 아닙니다. (1억원 초과 필요)"
                })
        
        # 중소기업 제한 일관성 검사
        if sme_restriction == "소기업_소상공인" and estimated_price >= 100_000_000:
            issues.append({
                "type": "중소기업 제한 불일치",
                "severity": "high",
                "message": f"추정가격 {estimated_price:,.0f}원은 소기업 제한 대상이 아닙니다. (1억원 미만 필요)"
            })
        elif sme_restriction == "중소기업_소상공인" and (estimated_price < 100_000_000 or estimated_price >= 230_000_000):
            issues.append({
                "type": "중소기업 제한 불일치",
                "severity": "high",
                "message": f"추정가격 {estimated_price:,.0f}원은 중소기업 제한 대상이 아닙니다. (1억원 이상 2.3억원 미만)"
            })
        
        # 공고 방식 일관성 검사
        if recommended_type == "소액수의" and estimated_price > 100_000_000:
            issues.append({
                "type": "공고 방식 불일치",
                "severity": "high",
                "message": f"추정가격 {estimated_price:,.0f}원은 소액수의 대상이 아닙니다. (1억원 이하 필요)"
            })
        elif recommended_type == "적격심사" and estimated_price <= 100_000_000:
            issues.append({
                "type": "공고 방식 불일치",
                "severity": "medium",
                "message": f"추정가격 {estimated_price:,.0f}원은 적격심사 대상이지만, 소액수의도 가능합니다."
            })
        
        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "validation_type": "basic"
        }
    
    def _openai_validation(
        self,
        classification_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        OpenAI를 통한 고급 검증
        
        논리적 불일치, 패턴 매칭 등을 수행
        """
        prompt = f"""
당신은 국가계약법 기반 Rule Engine 결과 검증 전문가입니다.

다음 Rule Engine 결과의 일관성을 검증하세요:

```json
{{
    "recommended_type": "{classification_result.get('recommended_type', '')}",
    "estimated_price_exc_vat": {classification_result.get('estimated_price_exc_vat', 0)},
    "applied_annex": "{classification_result.get('applied_annex', '')}",
    "sme_restriction": "{classification_result.get('sme_restriction', '')}",
    "contract_nature": {classification_result.get('contract_nature', {})}
}}
```

검증 규칙:
1. 추정가격과 별표 일치 여부
   - 별표1: 10억원 이상
   - 별표2: 2.3억원 이상 ~ 10억원 미만
   - 별표3: 1억원 초과 ~ 2.3억원 미만

2. 추정가격과 중소기업 제한 일치 여부
   - 소기업: 1억원 미만
   - 중소기업: 1억원 이상 ~ 2.3억원 미만
   - 없음: 2.3억원 이상

3. 추정가격과 공고 방식 일치 여부
   - 소액수의: 1억원 이하
   - 적격심사: 1억원 초과

4. 계약 성격과 템플릿 매핑 일치 여부

다음 JSON 형식으로 응답하세요:
{{
    "is_valid": true/false,
    "issues": [
        {{
            "type": "이슈 유형",
            "severity": "low/medium/high",
            "message": "상세 메시지"
        }}
    ]
}}
"""
        
        try:
            from app.config import get_settings
            settings = get_settings()
            # 환경 변수 OPENAI_MODEL_VALIDATOR가 있으면 사용, 없으면 기본값
            validator_model = os.getenv("OPENAI_MODEL_VALIDATOR", "gpt-4o-mini")
            
            response = self.client.chat.completions.create(
                model=validator_model,
                messages=[
                    {"role": "system", "content": "당신은 국가계약법 기반 Rule Engine 결과 검증 전문가입니다. 논리적 불일치를 정확히 탐지하세요."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,  # 결정적 결과
                response_format={"type": "json_object"}
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            result["validation_type"] = "openai"
            return result
            
        except Exception as e:
            print(f"⚠️ OpenAI 검증 실패: {e}")
            # 실패 시 기본 검증으로 폴백
            return self._basic_validation(classification_result)
    
    def validate_generation_output(
        self,
        generated_document: str,
        classification_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        생성된 공고문이 분류 결정과 일치하는지 검증 (Generator Guard)
        
        Args:
            generated_document: 생성된 공고문
            classification_result: 분류 결과
            
        Returns:
            검증 결과
        """
        issues = []
        
        recommended_type = classification_result.get("recommended_type", "")
        applied_annex = classification_result.get("applied_annex")
        sme_restriction = classification_result.get("sme_restriction", "")
        
        # 공고 방식 불일치 검사
        if recommended_type == "적격심사":
            if "소액수의" in generated_document or "소액" in generated_document:
                issues.append({
                    "type": "분류 결정 불일치",
                    "severity": "high",
                    "message": f"공고 방식이 Rule Engine 결정({recommended_type})과 다릅니다. '적격심사' 표현을 사용하세요."
                })
        elif recommended_type == "소액수의":
            if "적격심사" in generated_document:
                issues.append({
                    "type": "분류 결정 불일치",
                    "severity": "high",
                    "message": f"공고 방식이 Rule Engine 결정({recommended_type})과 다릅니다. '소액수의' 표현을 사용하세요."
                })
        
        # 별표 누락 검사
        if applied_annex and applied_annex not in generated_document:
            issues.append({
                "type": "별표 누락",
                "severity": "medium",
                "message": f"적용 별표({applied_annex})가 문서에 명시되지 않았습니다."
            })
        
        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "validation_type": "generation_guard"
        }


# Singleton 인스턴스
_openai_validator = None


def get_openai_validator() -> OpenAIValidationAgent:
    """전역 OpenAI Validator 인스턴스 반환"""
    global _openai_validator
    if _openai_validator is None:
        _openai_validator = OpenAIValidationAgent()
    return _openai_validator

