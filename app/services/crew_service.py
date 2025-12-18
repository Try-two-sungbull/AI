from crewai import Crew, Process
from typing import Dict, Any, Optional, List
import json
import os
from datetime import datetime

from .agents import (
    create_extractor_agent,
    create_classifier_agent,
    create_generator_agent,
    create_validator_agent
)
from .tasks import (
    create_extraction_task,
    create_classification_task,
    create_generation_task,
    create_validation_task,
    create_revision_task
)
from app.models.agent_state import AgentState


class BiddingDocumentCrew:
    """
    입찰 공고문 자동 작성 Crew (멀티 에이전트 구조)
    
    현재 구조: 순차적 멀티 에이전트
    - 각 단계마다 별도의 Crew 생성 (Extractor → Classifier → Generator → Validator)
    - Agent들이 순차적으로 협업하여 전체 워크플로우를 실행합니다.
    
    향후 개선 가능: 협업적 멀티 에이전트
    - 여러 Agent가 한 Crew에 함께 있어서 동시에 협업
    - Task 간 의존성 설정으로 더 유연한 협업 가능
    """

    def __init__(self, state: AgentState):
        self.state = state
        self.extractor = create_extractor_agent()
        self.classifier = create_classifier_agent()
        self.generator = create_generator_agent()
        self.validator = create_validator_agent()

    def run_extraction(self, document_text: str) -> Dict[str, Any]:
        """
        STEP 2: 문서에서 정보 추출

        Returns:
            ExtractedData 형식의 딕셔너리
        """
        task = create_extraction_task(self.extractor, document_text)

        crew = Crew(
            agents=[self.extractor],
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )

        result = crew.kickoff()

        # 결과를 JSON으로 파싱
        try:
            extracted_data = json.loads(str(result))
        except json.JSONDecodeError:
            # JSON 파싱 실패 시 raw_output에서 JSON 추출 시도
            import re
            result_str = str(result)
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', result_str, re.DOTALL)
            if json_match:
                try:
                    extracted_data = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    extracted_data = {"raw_output": result_str}
            else:
                extracted_data = {"raw_output": result_str}

        # AgentState 업데이트
        self.state.extracted_data = extracted_data
        self.state.transition_to("classify")

        return extracted_data

    def run_classification(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        STEP 3: 공고 유형 분류 (Classifier Agent + Rule Engine Tool)
        
        Classifier Agent가 Rule Engine Tool을 사용하여 분류를 수행합니다.
        
        1차 분기: 공고 방식 (소액수의/적격심사)
        2차 분기: 계약 성격 (국가계약/단가계약, 단독/공동)

        Returns:
            ClassificationResult 형식의 딕셔너리
        """
        import json
        
        # Classifier Agent가 Rule Engine Tool을 사용하도록 Task 생성
        task = create_classification_task(
            self.classifier,
            extracted_data
        )
        
        # Classifier Agent만 사용 (Rule Engine은 Tool로 제공)
        crew = Crew(
            agents=[self.classifier],
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )
        
        result = crew.kickoff()
        
        # 결과를 JSON으로 파싱
        try:
            classification = json.loads(str(result))
            
            # Agent 결과 검증: 금액이 0이면 fallback 사용
            if classification.get("estimated_price_exc_vat") == 0 or classification.get("total_budget_vat") == 0:
                print("⚠️ Classifier Agent 결과에 금액 정보가 없습니다. Rule Engine 직접 호출...")
                raise ValueError("Invalid classification result")
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # JSON 파싱 실패 또는 유효하지 않은 결과 시 Rule Engine 직접 호출 (fallback)
            print(f"⚠️ Classifier Agent 결과 파싱 실패 또는 유효하지 않음: {e}. Rule Engine 직접 호출...")
            from app.tools.rule_engine import get_rule_engine
            from app.models.schemas import ExtractedData
            
            # extracted_data에서 raw_output 파싱 시도
            parsed_data = extracted_data.copy()
            if "raw_output" in extracted_data and isinstance(extracted_data["raw_output"], str):
                try:
                    # raw_output에서 JSON 추출 시도
                    import re
                    json_match = re.search(r'```json\s*(\{.*?\})\s*```', extracted_data["raw_output"], re.DOTALL)
                    if json_match:
                        raw_json = json.loads(json_match.group(1))
                        # raw_json의 값으로 parsed_data 업데이트 (기존 값이 없을 때만)
                        for key, value in raw_json.items():
                            if key not in parsed_data or not parsed_data[key]:
                                parsed_data[key] = value
                except Exception as parse_error:
                    print(f"⚠️ raw_output 파싱 실패: {parse_error}")
            
            # 데이터 타입 정규화 (ExtractedData 스키마에 맞게)
            # qualification_notes가 리스트인 경우 문자열로 변환
            if "qualification_notes" in parsed_data and isinstance(parsed_data["qualification_notes"], list):
                parsed_data["qualification_notes"] = "\n".join(str(item) for item in parsed_data["qualification_notes"])
            
            # detail_item_codes와 industry_codes가 문자열인 경우 리스트로 변환
            if "detail_item_codes" in parsed_data:
                if isinstance(parsed_data["detail_item_codes"], str):
                    parsed_data["detail_item_codes"] = [parsed_data["detail_item_codes"]] if parsed_data["detail_item_codes"] else []
                elif parsed_data["detail_item_codes"] is None:
                    parsed_data["detail_item_codes"] = []
                    
            if "industry_codes" in parsed_data:
                if isinstance(parsed_data["industry_codes"], str):
                    parsed_data["industry_codes"] = [parsed_data["industry_codes"]] if parsed_data["industry_codes"] else []
                elif parsed_data["industry_codes"] is None:
                    parsed_data["industry_codes"] = []
            
            try:
                extracted_model = ExtractedData(**parsed_data)
            except Exception as e:
                print(f"⚠️ ExtractedData 변환 실패: {e}")
                # 최소한의 필드로 ExtractedData 생성
                extracted_model = ExtractedData(
                    procurement_type=parsed_data.get("procurement_type", "물품"),
                    total_budget_vat=parsed_data.get("total_budget_vat") or parsed_data.get("estimated_amount", 0),
                    estimated_amount=parsed_data.get("estimated_amount", 0),
                    item_name=parsed_data.get("item_name", ""),
                    project_name=parsed_data.get("project_name", ""),
                    delivery_deadline_days=parsed_data.get("delivery_deadline_days"),
                    procurement_method_raw=parsed_data.get("procurement_method_raw", ""),
                    detail_item_codes=parsed_data.get("detail_item_codes", []),
                    industry_codes=parsed_data.get("industry_codes", []),
                    is_joint_contract=parsed_data.get("is_joint_contract", False),
                    has_region_restriction=parsed_data.get("has_region_restriction", False),
                    qualification_notes=parsed_data.get("qualification_notes", "")
                )
            
            rule_engine = get_rule_engine()
            classification_result = rule_engine.classify(extracted_model)
            contract_nature = rule_engine._determine_contract_nature(extracted_model)
            total_budget = extracted_model.total_budget_vat or extracted_model.estimated_amount
            estimated_price_exc_vat = rule_engine._calculate_estimated_price_exc_vat(total_budget)
            
            classification = {
                "recommended_type": classification_result.recommended_type,
                "confidence": classification_result.confidence,
                "reason": classification_result.reason,
                "alternative_types": classification_result.alternative_types,
                "reason_trace": classification_result.reason_trace,
                "contract_nature": contract_nature,
                "purchase_type": extracted_model.procurement_type,
                "estimated_price_exc_vat": estimated_price_exc_vat,
                "applied_annex": rule_engine._determine_annex(estimated_price_exc_vat),
                "sme_restriction": rule_engine._determine_sme_restriction(estimated_price_exc_vat)
            }
        
        print(f"\n✅ 분류 결과:")
        print(f"  - 공고 방식: {classification.get('recommended_type', 'N/A')}")
        print(f"  - 계약 성격: {classification.get('contract_nature', 'N/A')}")
        print(f"  - 추정가격(VAT 제외): {classification.get('estimated_price_exc_vat', 0):,.0f}원")
        print(f"  - 적용 별표: {classification.get('applied_annex', 'N/A')}")
        print(f"  - 중소기업 제한: {classification.get('sme_restriction', 'N/A')}")

        # AgentState 업데이트
        self.state.classification = classification
        self.state.transition_to("generate")

        return classification

    def run_generation(
        self,
        extracted_data: Dict[str, Any],
        template_id: str = None,
        announcement_type: str = None,
        law_references: str = ""
    ) -> str:
        """
        STEP 4: Document Assembly (Non-LLM Pipeline 단계)
        
        핵심 원칙: "LLM은 판단만, 문서 생성은 코드가 한다"
        
        이 메서드는 LLM Task가 아니라 Pipeline 단계입니다:
        1. 템플릿 파일 직접 로드
        2. field_mapper로 플레이스홀더 치환 (Document Assembly)
        3. (선택) Generator Agent로 검증/다듬기 (USE_GENERATOR_AGENT=true인 경우만)
        
        Generator Agent의 역할:
        - ❌ 문서 생성 (이미 field_mapper가 완료)
        - ✅ 선택적 검증: 필수 슬롯 누락 여부, 문맥 검증
        - ✅ 선택적 다듬기: 문장 흐름 개선 (위험: 템플릿 수정 가능)
        
        Args:
            extracted_data: 추출된 키워드
            template_id: (사용 안 함, 호환성 유지용)
            announcement_type: 공고 유형 (템플릿 선택용)

        Returns:
            생성된 공고문 문자열 (field_mapper 결과 또는 Generator Agent 결과)
        """
        from app.tools.template_selector import get_template_selector
        from app.tools.field_mapper import get_field_mapper
        from app.models.schemas import ClassificationResult

        # 1. 템플릿 선택 (분류 결과 기반)
        classification = self.state.classification or {}
        if not announcement_type:
            announcement_type = classification.get("recommended_type", "적격심사")

        template_selector = get_template_selector()
        
        # ClassificationResult 객체 생성 (템플릿 선택용)
        classification_result = ClassificationResult(
            recommended_type=announcement_type,
            confidence=classification.get("confidence", 1.0),
            reason=classification.get("reason", ""),
            alternative_types=classification.get("alternative_types", [])
        )
        
        # 도커 환경에서는 hwpx 사용 불가 (Windows 전용), 마크다운 템플릿 사용
        # 로컬 Windows 환경에서는 hwpx 사용 가능
        import sys
        preferred_format = "md" if sys.platform != "win32" else "hwpx"
        template = template_selector.select_template(classification_result, preferred_format=preferred_format)
        print(f"✅ 템플릿 선택: {template.template_type} ({template.template_id}, 형식: {template.template_format})")

        # 분류 결과를 extracted_data에 포함 (Generator Guard용)
        extracted_data_with_classification = extracted_data.copy()
        extracted_data_with_classification["classification"] = classification
        
        # 템플릿 형식에 따라 다른 처리
        template_format = template.template_format or "md"
        
        if template_format == "hwpx":
            # HWPX 템플릿 처리 (Windows 전용, 도커에서는 사용 불가)
            try:
                from pathlib import Path
                from app.utils.hwpx_template_handler import fill_hwpx_template
                from app.tools.field_mapper import get_field_mapper
                
                field_mapper = get_field_mapper()
                mapped_data = field_mapper.map_extracted_to_template(
                    extracted_data_with_classification,
                    []  # HWPX는 파란색 텍스트에서 필드 추출
                )
                
                # HWPX 템플릿에 데이터 채우기
                template_path = Path(template.template_path)
                hwpx_bytes = fill_hwpx_template(template_path, mapped_data)
                
                # 바이트를 base64로 인코딩하여 문자열로 반환 (임시)
                import base64
                generated_document = base64.b64encode(hwpx_bytes).decode('utf-8')
            except (ImportError, ModuleNotFoundError):
                # pyhwpx가 설치되지 않은 경우 (도커 환경) 마크다운 템플릿으로 폴백
                print("⚠️ HWPX 템플릿 사용 불가 (pyhwpx 미설치). 마크다운 템플릿으로 폴백합니다.")
                template_format = "md"
                # 아래 마크다운 처리 로직으로 진행
            
        elif template_format == "pdf":
            # PDF 템플릿 처리
            from pathlib import Path
            from app.utils.pdf_template_handler import fill_pdf_template
            from app.tools.field_mapper import get_field_mapper
            
            field_mapper = get_field_mapper()
            mapped_data = field_mapper.map_extracted_to_template(
                extracted_data_with_classification,
                []  # PDF는 파란색 텍스트에서 필드 추출
            )
            
            # PDF 템플릿에 데이터 채우기
            template_path = Path(template.template_path)
            pdf_bytes = fill_pdf_template(template_path, mapped_data)
            
            # 바이트를 base64로 인코딩하여 문자열로 반환 (임시)
            import base64
            generated_document = base64.b64encode(pdf_bytes).decode('utf-8')
            
        else:
            # ============================================================
            # STEP 4: Document Assembly (Non-LLM Pipeline 단계)
            # ============================================================
            # 핵심 원칙: "LLM은 판단만, 문서 생성은 코드가 한다"
            #
            # 이 단계는 LLM Task가 아니라 Pipeline 단계입니다:
            # - 템플릿 렌더링: field_mapper가 모든 플레이스홀더를 채움
            # - 데이터 변환: extracted_data → 템플릿 필드 매핑
            # - 파생 필드 생성: 날짜 계산, 법령 문구 생성 등
            #
            # Generator Agent는 선택적 검증/다듬기 용도로만 사용 가능
            # (기본값: false - 사용 안 함)
            # ============================================================
            
            field_mapper = get_field_mapper()
            
            # 템플릿에 데이터 채우기 (Document Assembly)
            print("📝 Document Assembly 시작: 템플릿 렌더링 중...")
            filled_template = field_mapper.fill_template(
                template.content,
                extracted_data_with_classification
            )
            
            # 플레이스홀더 검증: 남은 플레이스홀더 확인
            import re
            remaining_placeholders = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', filled_template)
            if remaining_placeholders:
                print(f"⚠️ 경고: 다음 플레이스홀더가 채워지지 않았습니다: {set(remaining_placeholders)}")
                # 기본값으로 채우기 시도
                default_values = {
                    "qualification_review_target": "적격심사 제외대상입니다.",
                    "integrity_pledge_target": "청렴계약이행 서약제 대상입니다.",
                    "contract_method_detail": "일반경쟁(총액), 전자입찰대상 물품입니다.",
                }
                for placeholder in set(remaining_placeholders):
                    if placeholder in default_values:
                        filled_template = filled_template.replace(
                            f"{{{placeholder}}}",
                            default_values[placeholder]
                        )
                        print(f"✅ 플레이스홀더 {placeholder}에 기본값 적용")
                # 남은 플레이스홀더 재확인
                remaining_placeholders = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', filled_template)
                if remaining_placeholders:
                    print(f"⚠️ 여전히 채워지지 않은 플레이스홀더: {set(remaining_placeholders)}")
            else:
                print("✅ 모든 플레이스홀더가 채워졌습니다.")

            # ============================================================
            # 선택적: Generator Agent (LLM 기반 검증/다듬기)
            # ============================================================
            # 기본값: false (사용 안 함)
            #
            # Generator Agent의 역할:
            # - ❌ 문서 생성 (이미 field_mapper가 완료)
            # - ✅ 선택적 검증: 필수 슬롯 누락 여부, 문맥 검증
            # - ✅ 선택적 다듬기: 문장 흐름 개선 (위험: 템플릿 수정 가능)
            #
            # 사용 조건:
            # - 템플릿에 비어 있는 문장 구조가 있는 경우
            # - {}로 표현되지 않은 부분을 LLM이 문맥상 만들어야 하는 경우
            # - 현재 템플릿은 모든 가변 정보가 {}로 명시되어 있으므로 불필요
            #
            # 활성화 방법:
            # 1. 환경 변수: USE_GENERATOR_AGENT=true
            # 2. docker-compose.yml: - USE_GENERATOR_AGENT=true
            #
            # 주의: Generator Agent 사용 시 템플릿이 잘리거나 수정될 수 있으므로
            #       잘림 감지 로직이 자동으로 filled_template를 fallback으로 사용합니다.
            # ============================================================
            use_generator_agent = os.getenv("USE_GENERATOR_AGENT", "false").lower() == "true"
            
            if use_generator_agent:
                print("⚠️ Generator Agent 사용 중 (선택적 검증/다듬기 모드)")
                # Generator가 문서 검증/다듬기 (문장 다듬기 포함)
                generation_task = create_generation_task(
                    self.generator,
                    filled_template,  # 이미 채워진 템플릿
                    extracted_data_with_classification,
                    classification  # Rule Engine 결정값 (가드용)
                )

                # Generator만 먼저 실행하여 문서 검증/다듬기
                generation_crew = Crew(
                    agents=[self.generator],
                    tasks=[generation_task],
                    process=Process.sequential,
                    verbose=True
                )
                
                generation_result = generation_crew.kickoff()
                generated_document = str(generation_result)
            else:
                # Generator Agent 건너뛰기: field_mapper 결과를 바로 사용 (기본 동작)
                # field_mapper가 이미 모든 플레이스홀더를 채웠으므로 추가 LLM 호출 불필요
                print("✅ Document Assembly 완료: field_mapper 결과를 바로 사용합니다.")
                print("   (Generator Agent는 사용하지 않음 - USE_GENERATOR_AGENT=false)")
                generated_document = filled_template
            
            # 응답이 잘렸는지 확인 (템플릿의 주요 섹션 포함 여부)
            template_sections = [
                "견적(입찰)에 부치는 사항", "견적(입찰) 및 계약방식", "입찰참가자격", 
                "공동계약", "예정가격", "청렴계약이행", "입찰보증금", 
                "입찰무효", "하도급", "기타사항", "위와 같이 공고합니다"
            ]
            missing_sections = []
            for section in template_sections:
                if section not in generated_document:
                    missing_sections.append(section)
            
            # 섹션 번호 확인 (1~10까지 모두 있어야 함)
            section_numbers = []
            for i in range(1, 11):
                if f"## {i}." in generated_document or f"## {i}." in filled_template:
                    section_numbers.append(i)
            
            # 템플릿 길이 대비 생성 문서 길이 확인 (80% 미만이면 잘림으로 간주)
            template_length = len(filled_template)
            generated_length = len(generated_document)
            length_ratio = generated_length / template_length if template_length > 0 else 0
            
            # 문서가 잘렸는지 확인
            is_truncated = False
            if missing_sections:
                print(f"⚠️ 경고: 생성된 문서에서 다음 섹션이 누락되었습니다: {missing_sections}")
                is_truncated = True
            
            if length_ratio < 0.8:
                print(f"⚠️ 경고: 문서가 너무 짧습니다 (템플릿: {template_length}자, 생성: {generated_length}자, 비율: {length_ratio:.2%}). LLM 응답이 잘렸을 가능성이 있습니다.")
                is_truncated = True
            
            # "위와 같이 공고합니다"가 없으면 잘림으로 간주
            if "위와 같이 공고합니다" not in generated_document:
                print("⚠️ 경고: 문서 끝부분이 누락되었습니다 ('위와 같이 공고합니다' 없음).")
                is_truncated = True
            
            # 잘렸으면 filled_template를 fallback으로 사용
            if is_truncated and use_generator_agent:
                print("⚠️ Generator 응답이 불완전합니다. field_mapper 결과를 fallback으로 사용합니다.")
                generated_document = filled_template
            
            # Validator Agent 사용 여부 확인 (환경 변수로 제어, 기본값: true - 멀티 에이전트 사용)
            use_validator_agent = os.getenv("USE_VALIDATOR_AGENT", "true").lower() == "true"
            
            if use_validator_agent:
                # Generator 결과를 Validator가 검토 (멀티 에이전트 협업)
                # 법령 참조는 파라미터로 전달받음
                
                validation_task = create_validation_task(
                    self.validator,
                    generated_document,  # Generator가 생성한 문서
                    law_references
                )
                
                # Validator가 Generator 결과를 검토
                validation_crew = Crew(
                    agents=[self.validator],
                    tasks=[validation_task],
                    process=Process.sequential,
                    verbose=True
                )
                
                validation_result = validation_crew.kickoff()
                
                # 검증 결과 확인
                try:
                    validation_data = json.loads(str(validation_result))
                    issues = validation_data.get("issues", [])
                    
                    if issues:
                        print(f"⚠️ Validator가 {len(issues)}개 이슈 발견:")
                        for issue in issues[:3]:  # 최대 3개만 출력
                            print(f"  - {issue.get('issue_type', 'N/A')}: {issue.get('suggestion', 'N/A')}")
                    else:
                        print("✅ Validator 검증 통과")
                        
                except json.JSONDecodeError:
                    print("⚠️ Validator 결과 파싱 실패 (문서는 생성됨)")
            else:
                print("✅ Validator Agent 건너뛰기: 검증 단계를 생략합니다.")
            
            # 최종 문서는 Generator 결과 사용
            generated_document = generated_document

        # Generator 결과 검증 (Rule Guard)
        validation_issues = self._validate_generation_result(
            generated_document,
            classification
        )
        
        if validation_issues:
            print(f"⚠️ Generator 결과 검증 이슈 발견: {len(validation_issues)}개")
            for issue in validation_issues:
                print(f"  - {issue.get('issue_type')}: {issue.get('suggestion')}")

        # AgentState 업데이트
        self.state.generated_document = generated_document
        self.state.transition_to("validate")

        return generated_document
    
    def _validate_generation_result(
        self,
        generated_document: str,
        classification: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        생성된 문서가 분류 결정과 일치하는지 검증 (Rule Guard)
        
        Args:
            generated_document: 생성된 공고문
            classification: 분류 결과
            
        Returns:
            검증 이슈 목록
        """
        issues = []
        recommended_type = classification.get("recommended_type", "")
        applied_annex = classification.get("applied_annex")
        sme_restriction = classification.get("sme_restriction", "")
        
        # 공고 방식 불일치 검사
        if recommended_type == "적격심사":
            if "소액수의" in generated_document or "소액" in generated_document:
                issues.append({
                    "issue_type": "분류 결정 불일치",
                    "severity": "high",
                    "current_text": "소액수의 관련 표현 발견",
                    "suggestion": f"공고 방식이 Rule Engine 결정({recommended_type})과 다릅니다. '적격심사' 표현을 사용하세요."
                })
        elif recommended_type == "소액수의":
            if "적격심사" in generated_document:
                issues.append({
                    "issue_type": "분류 결정 불일치",
                    "severity": "high",
                    "current_text": "적격심사 관련 표현 발견",
                    "suggestion": f"공고 방식이 Rule Engine 결정({recommended_type})과 다릅니다. '소액수의' 표현을 사용하세요."
                })
        
        # 별표 불일치 검사
        if applied_annex:
            if applied_annex not in generated_document:
                issues.append({
                    "issue_type": "별표 누락",
                    "severity": "medium",
                    "suggestion": f"적용 별표({applied_annex})가 문서에 명시되지 않았습니다."
                })
        
        return issues

    def run_validation(
        self,
        generated_document: str,
        law_references: str
    ) -> Dict[str, Any]:
        """
        STEP 5: 법령 검증

        Returns:
            ValidationResult 형식의 딕셔너리
        """
        task = create_validation_task(
            self.validator,
            generated_document,
            law_references
        )

        crew = Crew(
            agents=[self.validator],
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )

        result = crew.kickoff()

        try:
            validation_result = json.loads(str(result))
        except json.JSONDecodeError:
            validation_result = {
                "is_valid": False,
                "issues": [],
                "checked_laws": [],
                "timestamp": datetime.now().isoformat(),
                "raw_output": str(result)
            }

        # AgentState 업데이트
        self.state.validation_issues = validation_result.get("issues", [])

        return validation_result

    def run_revision(
        self,
        original_document: str,
        validation_issues: list
    ) -> str:
        """
        STEP 6: 검증 이슈 반영하여 수정

        Returns:
            수정된 공고문 문자열
        """
        task = create_revision_task(
            self.generator,  # 수정도 generator가 담당
            original_document,
            validation_issues
        )

        crew = Crew(
            agents=[self.generator],
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )

        result = crew.kickoff()
        revised_document = str(result)
        
        # Revision 결과 검증: 원본 문서 길이 대비 확인
        original_length = len(original_document)
        revised_length = len(revised_document)
        length_ratio = revised_length / original_length if original_length > 0 else 0
        
        # 필수 섹션 확인
        required_sections = [
            "위와 같이 공고합니다",
            "기타사항",
            "입찰무효",
            "입찰보증금",
            "청렴계약이행",
            "예정가격",
            "공동계약",
            "입찰참가자격"
        ]
        missing_sections = [s for s in required_sections if s not in revised_document]
        
        # Revision이 문서를 잘랐는지 확인
        if length_ratio < 0.8 or missing_sections:
            print(f"⚠️ 경고: Revision 결과가 불완전합니다 (원본: {original_length}자, 수정: {revised_length}자, 비율: {length_ratio:.2%})")
            if missing_sections:
                print(f"⚠️ 누락된 섹션: {missing_sections}")
            print("⚠️ 원본 문서를 그대로 반환합니다.")
            return original_document
        
        print(f"✅ Revision 완료 (원본: {original_length}자, 수정: {revised_length}자, 비율: {length_ratio:.2%})")

        # AgentState 업데이트
        self.state.generated_document = revised_document
        self.state.increment_retry()

        return revised_document

    def run_full_pipeline(
        self,
        document_text: str,
        law_references: str = "",
        max_iterations: int = 10
    ) -> str:
        """
        전체 파이프라인 실행 - 완벽한 문서가 나올 때까지 반복

        Args:
            document_text: 원본 문서 텍스트
            law_references: 법령 참조 텍스트
            max_iterations: 최대 반복 횟수 (무한 루프 방지)

        Returns:
            완성된 공고문 문자열 (String)
        """
        # STEP 1: 추출
        extracted_data = self.run_extraction(document_text)

        # STEP 2: 분류
        classification = self.run_classification(extracted_data)

        # 분류 결과 출력
        print(f"📋 분류 결과: {classification.get('recommended_type')}")

        # STEP 3: 생성 (템플릿 + 데이터 매핑 방식)
        # 공고 방식으로 템플릿 선택
        announcement_type = classification.get("recommended_type")
        
        # 소액수의는 "최저가낙찰" 템플릿 사용
        if announcement_type == "소액수의":
            announcement_type = "최저가낙찰"
        
        current_document = self.run_generation(
            extracted_data,
            announcement_type=announcement_type,
            law_references=law_references
        )

        # ============================================================
        # STEP 4: 검증 및 수정 (멀티 에이전트 협업)
        # ============================================================
        # Validator Agent와 Generator Agent가 협업하여 문서를 검증하고 수정합니다.
        # - Validator: 법령 검증 및 이슈 발견
        # - Generator: 발견된 이슈 반영하여 문서 수정
        # ============================================================
        use_validator_agent = os.getenv("USE_VALIDATOR_AGENT", "true").lower() == "true"
        
        if use_validator_agent:
            # 검증 수행 (Validator Agent)
            validation_result = self.run_validation(
                current_document,
                law_references
            )
            
            issues = validation_result.get("issues", [])
            
            # High severity 이슈만 필터링
            high_severity_issues = [issue for issue in issues if issue.get("severity") == "high"]
            
            if high_severity_issues:
                print(f"⚠️ High severity 이슈 {len(high_severity_issues)}개 발견 (전체 {len(issues)}개)")
                print("🔄 Generator Agent가 Validator의 이슈를 반영하여 문서 수정 중... (멀티 에이전트 협업)")
                # High severity 이슈만 수정 (Generator Agent가 Validator 결과를 받아서 수정)
                current_document = self.run_revision(
                    current_document,
                    high_severity_issues  # High severity만 전달
                )
            elif issues:
                print(f"ℹ️ Medium/Low severity 이슈 {len(issues)}개 발견 (무시하고 진행)")
            else:
                print("✅ 검증 완료: 이슈 없음")
        else:
            print("✅ Validator Agent 건너뛰기: 검증 단계를 생략합니다.")

        # 최대 반복 도달 - 최선의 결과 반환
        print(f"⚠️ 최대 반복 횟수({max_iterations})에 도달했습니다. 현재 버전을 반환합니다.")
        self.state.transition_to("complete")
        return current_document
