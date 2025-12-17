from crewai import Crew, Process
from typing import Dict, Any, Optional
import json
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
    입찰 공고문 자동 작성 Crew

    Agent들을 조합하여 전체 워크플로우를 실행합니다.
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
            # JSON 파싱 실패 시 텍스트를 그대로 반환
            extracted_data = {"raw_output": str(result)}

        # AgentState 업데이트
        self.state.extracted_data = extracted_data
        self.state.transition_to("classify")

        return extracted_data

    def run_classification(self, extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        STEP 3: 공고 유형 분류

        Returns:
            ClassificationResult 형식의 딕셔너리
        """
        task = create_classification_task(self.classifier, extracted_data)

        crew = Crew(
            agents=[self.classifier],
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )

        result = crew.kickoff()

        try:
            classification = json.loads(str(result))
        except json.JSONDecodeError:
            classification = {
                "recommended_type": "unknown",
                "confidence": 0.0,
                "reason": str(result),
                "alternative_types": []
            }

        # AgentState 업데이트
        self.state.classification = classification
        self.state.transition_to("generate")

        return classification

    def run_generation(
        self,
        extracted_data: Dict[str, Any],
        template: str,
        user_prompt: str = ""
    ) -> str:
        """
        STEP 4: 공고문 초안 생성

        Returns:
            생성된 공고문 문자열
        """
        task = create_generation_task(
            self.generator,
            extracted_data,
            template,
            user_prompt
        )

        crew = Crew(
            agents=[self.generator],
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )

        result = crew.kickoff()
        generated_document = str(result)

        # AgentState 업데이트
        self.state.generated_document = generated_document
        self.state.transition_to("validate")

        return generated_document

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

        # AgentState 업데이트
        self.state.generated_document = revised_document
        self.state.increment_retry()

        return revised_document

    def run_full_pipeline(
        self,
        document_text: str,
        template: str,
        law_references: str,
        user_prompt: str = ""
    ) -> Dict[str, Any]:
        """
        전체 파이프라인 실행

        Agent Decision Policy:
        - issues.length == 0 → complete
        - retry_count < max_retry → revise
        - else → escalate to human

        Returns:
            최종 결과 딕셔너리
        """
        # STEP 2: 추출
        extracted_data = self.run_extraction(document_text)

        # STEP 3: 분류
        classification = self.run_classification(extracted_data)

        # 신뢰도 확인 (0.6 미만이면 사용자 확인 필요)
        if classification.get("confidence", 0) < 0.6:
            return {
                "status": "needs_user_confirmation",
                "message": "분류 신뢰도가 낮습니다. 사용자 확인이 필요합니다.",
                "extracted_data": extracted_data,
                "classification": classification
            }

        # STEP 4: 생성
        generated_document = self.run_generation(
            extracted_data,
            template,
            user_prompt
        )

        # STEP 5: 검증
        validation_result = self.run_validation(
            generated_document,
            law_references
        )

        # Agent Decision Policy
        if len(validation_result.get("issues", [])) == 0:
            # 이슈 없음 → 완료
            self.state.transition_to("complete")
            return {
                "status": "complete",
                "extracted_data": extracted_data,
                "classification": classification,
                "final_document": generated_document,
                "validation": validation_result
            }

        elif self.state.can_retry():
            # 재시도 가능 → 수정
            self.state.transition_to("revise")
            revised_document = self.run_revision(
                generated_document,
                validation_result.get("issues", [])
            )

            # 수정 후 재검증
            revalidation_result = self.run_validation(
                revised_document,
                law_references
            )

            if len(revalidation_result.get("issues", [])) == 0:
                self.state.transition_to("complete")
                return {
                    "status": "complete",
                    "extracted_data": extracted_data,
                    "classification": classification,
                    "final_document": revised_document,
                    "validation": revalidation_result,
                    "revision_count": self.state.retry_count
                }
            else:
                return {
                    "status": "revised_with_remaining_issues",
                    "extracted_data": extracted_data,
                    "classification": classification,
                    "final_document": revised_document,
                    "validation": revalidation_result,
                    "revision_count": self.state.retry_count
                }

        else:
            # 재시도 한계 → 사람 개입 필요
            return {
                "status": "needs_human_intervention",
                "message": f"최대 재시도 횟수({self.state.max_retry})를 초과했습니다.",
                "extracted_data": extracted_data,
                "classification": classification,
                "final_document": generated_document,
                "validation": validation_result,
                "revision_count": self.state.retry_count
            }
