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

        # 디버깅: Agent 원본 결과 출력
        print("\n" + "="*80)
        print("🔍 Classifier Agent 원본 결과:")
        print("="*80)
        print(str(result))
        print("="*80 + "\n")

        # JSON 코드블록 제거 (```json ... ``` 형식 처리)
        result_str = str(result).strip()
        if result_str.startswith("```json"):
            result_str = result_str[7:]  # ```json 제거
        if result_str.startswith("```"):
            result_str = result_str[3:]  # ``` 제거
        if result_str.endswith("```"):
            result_str = result_str[:-3]  # 끝 ``` 제거
        result_str = result_str.strip()

        # JSON 주석 제거 (// 주석)
        import re
        result_str = re.sub(r'//.*?(?=\n|$)', '', result_str)

        try:
            raw_classification = json.loads(result_str)

            print("✅ JSON 파싱 성공!")
            print(f"원본 구조: {json.dumps(raw_classification, ensure_ascii=False, indent=2)}")

            # Task에서 반환하는 복잡한 JSON 구조를 단순화
            classification = {
                "recommended_type": raw_classification.get("classification", {}).get("contract_method", "unknown"),
                "reason": raw_classification.get("constraints", {}).get("reason", ""),
                "purchase_type": raw_classification.get("classification", {}).get("purchase_type", ""),
                "applied_annex": raw_classification.get("constraints", {}).get("applied_annex", ""),
                "sme_restriction": raw_classification.get("constraints", {}).get("sme_restriction", ""),
                "raw": raw_classification  # 원본 데이터도 보관
            }

            print(f"\n✅ 변환된 classification:")
            print(f"  - recommended_type: {classification['recommended_type']}")
            print(f"  - reason: {classification['reason']}")

        except json.JSONDecodeError as e:
            print(f"❌ JSON 파싱 실패: {e}")
            print(f"원본 결과 (처음 500자):\n{str(result)[:500]}")
            classification = {
                "recommended_type": "적격심사",  # 기본값으로 적격심사 사용
                "reason": "JSON 파싱 실패로 기본값 사용",
                "raw_text": str(result)
            }

        # AgentState 업데이트
        self.state.classification = classification
        self.state.transition_to("generate")

        return classification

    def run_generation(
        self,
        extracted_data: Dict[str, Any],
        template_id: str = None,
        announcement_type: str = None
    ) -> str:
        """
        STEP 4: 공고문 초안 생성 (Agent가 PDF 샘플 학습 후 합성)

        1. Few-Shot PDF 샘플 로드
        2. Agent가 샘플들에서 구조 패턴 학습
        3. 추출된 키워드로 새 문서 합성

        Args:
            extracted_data: 추출된 키워드
            template_id: (사용 안 함, 호환성 유지용)
            announcement_type: 공고 유형 (샘플 선택용)

        Returns:
            생성된 공고문 문자열
        """
        from app.tools.example_loader import get_example_loader

        # 1. PDF 샘플 로드 (여러 개)
        example_loader = get_example_loader()

        # announcement_type이 없으면 기본값으로 적격심사 사용
        if not announcement_type:
            announcement_type = "적격심사"

        few_shot_examples = example_loader.load_examples(
            announcement_type,
            max_samples=3  # 3개의 샘플로 학습
        )

        if not few_shot_examples:
            raise ValueError(f"공고 유형 '{announcement_type}'에 대한 샘플을 찾을 수 없습니다")

        # 2. Agent가 샘플 학습 + 키워드로 합성
        task = create_generation_task(
            self.generator,
            extracted_data,
            few_shot_examples  # List[str] of PDF contents
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

        # STEP 3: 생성 (PDF 샘플 기반)
        announcement_type = classification.get("recommended_type")
        current_document = self.run_generation(
            extracted_data,
            announcement_type=announcement_type
        )

        # STEP 4: 검증 및 반복 (완벽해질 때까지)
        iteration = 0
        while iteration < max_iterations:
            iteration += 1

            # 검증
            validation_result = self.run_validation(
                current_document,
                law_references
            )

            issues = validation_result.get("issues", [])

            # 이슈 없음 → 완료!
            if len(issues) == 0:
                self.state.transition_to("complete")
                print(f"✅ 검증 완료! (반복: {iteration}회)")
                return current_document

            # 이슈 있음 → 수정 후 재시도
            print(f"🔄 이슈 {len(issues)}개 발견. 수정 중... (반복: {iteration}/{max_iterations})")

            current_document = self.run_revision(
                current_document,
                issues
            )

        # 최대 반복 도달 - 최선의 결과 반환
        print(f"⚠️ 최대 반복 횟수({max_iterations})에 도달했습니다. 현재 버전을 반환합니다.")
        self.state.transition_to("complete")
        return current_document
