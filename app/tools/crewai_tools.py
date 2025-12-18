"""
CrewAI Tools 정의

CrewAI Agent들이 사용할 수 있는 Tool들을 정의합니다.
"""

from crewai_tools import tool
from typing import Dict, Any
import json

from app.tools.rule_engine import get_rule_engine, ProcurementRuleEngine
from app.models.schemas import ExtractedData, ClassificationResult
from app.tools.template_selector import get_template_selector
from app.tools.field_mapper import get_field_mapper
from app.tools.web_crawler import get_crawler_tools
from app.utils.notice_amount_crawler import get_latest_notice_amount


@tool("Rule Engine 분류 도구")
def rule_engine_classify(extracted_data_json: str) -> str:
    """
    국가계약법 기반 공고 유형 분류를 수행합니다.
    
    Args:
        extracted_data_json: ExtractedData 형식의 JSON 문자열
        
    Returns:
        ClassificationResult 형식의 JSON 문자열
    """
    try:
        # JSON 문자열을 딕셔너리로 변환
        data_dict = json.loads(extracted_data_json)
        
        # 데이터 타입 정규화 (ExtractedData 스키마에 맞게)
        # qualification_notes가 리스트나 dict인 경우 문자열로 변환
        if "qualification_notes" in data_dict:
            if isinstance(data_dict["qualification_notes"], list):
                data_dict["qualification_notes"] = "\n".join(str(item) for item in data_dict["qualification_notes"])
            elif isinstance(data_dict["qualification_notes"], dict):
                # dict인 경우 JSON 문자열로 변환하거나 값들을 조합
                try:
                    data_dict["qualification_notes"] = json.dumps(data_dict["qualification_notes"], ensure_ascii=False)
                except:
                    # JSON 직렬화 실패 시 키-값 쌍을 문자열로 변환
                    data_dict["qualification_notes"] = "\n".join(f"{k}: {v}" for k, v in data_dict["qualification_notes"].items())
            elif not isinstance(data_dict["qualification_notes"], str):
                # 그 외의 타입이면 문자열로 변환
                data_dict["qualification_notes"] = str(data_dict["qualification_notes"])
        
        # detail_item_codes와 industry_codes가 문자열인 경우 리스트로 변환
        if "detail_item_codes" in data_dict and isinstance(data_dict["detail_item_codes"], str):
            data_dict["detail_item_codes"] = [data_dict["detail_item_codes"]] if data_dict["detail_item_codes"] else []
        elif "detail_item_codes" in data_dict and data_dict["detail_item_codes"] is None:
            data_dict["detail_item_codes"] = []
            
        if "industry_codes" in data_dict and isinstance(data_dict["industry_codes"], str):
            data_dict["industry_codes"] = [data_dict["industry_codes"]] if data_dict["industry_codes"] else []
        elif "industry_codes" in data_dict and data_dict["industry_codes"] is None:
            data_dict["industry_codes"] = []
        
        # ExtractedData 모델로 변환
        extracted_data = ExtractedData(**data_dict)
        
        # Rule Engine으로 분류
        rule_engine = get_rule_engine()
        classification_result = rule_engine.classify(extracted_data)
        
        # 계약 성격 정보 추가
        contract_nature = rule_engine._determine_contract_nature(extracted_data)
        
        # VAT 제외 추정가격 계산
        total_budget = extracted_data.total_budget_vat or extracted_data.estimated_amount
        estimated_price_exc_vat = rule_engine._calculate_estimated_price_exc_vat(total_budget)
        
        # 결과 딕셔너리 생성
        result = {
            "recommended_type": classification_result.recommended_type,
            "confidence": classification_result.confidence,
            "reason": classification_result.reason,
            "alternative_types": classification_result.alternative_types,
            "reason_trace": classification_result.reason_trace,
            "contract_nature": contract_nature,
            "purchase_type": extracted_data.procurement_type,
            "estimated_price_exc_vat": estimated_price_exc_vat,
            "applied_annex": rule_engine._determine_annex(estimated_price_exc_vat),
            "sme_restriction": rule_engine._determine_sme_restriction(estimated_price_exc_vat)
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"분류 실패: {str(e)}",
            "recommended_type": "적격심사",
            "confidence": 0.5,
            "reason": "오류 발생으로 기본값 사용"
        }, ensure_ascii=False)


@tool("템플릿 선택 도구")
def template_selector_tool(classification_result_json: str) -> str:
    """
    공고 유형에 맞는 템플릿을 선택합니다.
    
    Args:
        classification_result_json: ClassificationResult 형식의 JSON 문자열
        
    Returns:
        선택된 템플릿 정보 (JSON 문자열)
    """
    try:
        from app.models.schemas import ClassificationResult
        
        # JSON 문자열을 딕셔너리로 변환
        data_dict = json.loads(classification_result_json)
        
        # ClassificationResult 객체 생성
        classification_result = ClassificationResult(**data_dict)
        
        # 템플릿 선택
        template_selector = get_template_selector()
        template = template_selector.select_template(classification_result, preferred_format="md")
        
        # 결과 반환
        result = {
            "template_id": template.template_id,
            "template_type": template.template_type,
            "template_format": template.template_format,
            "template_path": str(template.template_path) if template.template_path else None,
            "placeholders": template.placeholders
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"템플릿 선택 실패: {str(e)}"
        }, ensure_ascii=False)


@tool("필드 매핑 도구")
def field_mapper_tool(template_content: str, extracted_data_json: str) -> str:
    """
    템플릿의 플레이스홀더를 추출된 데이터로 채웁니다.
    
    Args:
        template_content: 템플릿 내용 (마크다운)
        extracted_data_json: 추출된 데이터 (JSON 문자열)
        
    Returns:
        채워진 템플릿 (마크다운)
    """
    try:
        # JSON 문자열을 딕셔너리로 변환
        data_dict = json.loads(extracted_data_json)
        
        # Field Mapper로 템플릿 채우기
        field_mapper = get_field_mapper()
        filled_template = field_mapper.fill_template(template_content, data_dict)
        
        return filled_template
        
    except Exception as e:
        return f"필드 매핑 실패: {str(e)}\n\n원본 템플릿:\n{template_content}"


@tool("고시금액 조회 도구")
def notice_amount_tool(force_refresh: str = "false") -> str:
    """
    기획재정부 고시금액을 크롤링하여 조회합니다.
    
    고시금액은 2년마다 변경되며, 중소기업 제한 기준으로 사용됩니다.
    - 1억원 미만: 소기업 제한
    - 1억원 이상 ~ 고시금액 미만: 중소기업 제한
    - 고시금액 이상: 중소기업 제한 없음
    
    Args:
        force_refresh: "true"면 캐시 무시하고 강제 새로고침 (기본값: "false")
    
    Returns:
        고시금액 정보 (JSON 문자열)
        {
            "notice_amount": 230000000,
            "formatted": "2억 3천만 원",
            "source": "기획재정부 고시",
            "effective_date": "2025. 1. 1."
        }
    """
    try:
        import json
        from app.utils.notice_amount_crawler import get_notice_amount_crawler
        
        force = force_refresh.lower() == "true"
        crawler = get_notice_amount_crawler()
        amount = crawler.get_notice_amount(force_refresh=force)
        formatted = crawler.format_amount(amount)
        
        result = {
            "notice_amount": amount,
            "formatted": formatted,
            "source": "기획재정부 고시 (국가법령정보센터)",
            "description": "세계무역기구의 정부조달협정상 개방대상금액"
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": f"고시금액 조회 실패: {str(e)}",
            "default_amount": 230000000,
            "formatted": "2억 3천만 원"
        }, ensure_ascii=False)


def get_classifier_tools():
    """Classifier Agent가 사용할 Tool 목록"""
    return [rule_engine_classify, template_selector_tool]


def get_generator_tools():
    """Generator Agent가 사용할 Tool 목록"""
    return [field_mapper_tool]


def get_validator_tools():
    """Validator Agent가 사용할 Tool 목록"""
    # Validator는 웹 검색 및 크롤링 도구를 사용할 수 있음
    from app.tools.web_search import get_web_search, get_law_search
    crawler_tools = get_crawler_tools()
    return crawler_tools + [notice_amount_tool]  # 크롤링 도구 + 고시금액 조회 도구 추가


def get_extractor_tools():
    """Extractor Agent가 사용할 Tool 목록"""
    # Extractor도 필요시 크롤링 도구 사용 가능
    return []


def get_classifier_tools_with_notice():
    """Classifier Agent가 사용할 Tool 목록 (고시금액 조회 포함)"""
    return get_classifier_tools() + [notice_amount_tool]

