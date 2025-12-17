"""
CrewAI Tasks 정의

각 Task는 Agent에게 할당되는 구체적인 작업입니다.
CLAUDE.md의 Agent Loop를 따라 순차적으로 실행됩니다.
"""

from crewai import Task
from typing import Dict, Any


def create_extraction_task(agent, document_text: str) -> Task:
    """
    STEP 2: 핵심 정보 추출 Task

    Input: 발주계획서 원본 텍스트
    Output: ExtractedData JSON
    """
    return Task(
        description=f"""
        다음 발주계획서에서 핵심 정보를 추출하세요.

        문서 내용:
        {document_text}

        추출해야 할 정보:
        1. project_name: 사업명
        2. estimated_amount: 추정 금액 (숫자로, 원 단위)
        3. contract_period: 계약 기간
        4. qualification_notes: 자격 요건 및 특이사항
        5. procurement_type: 조달 유형 (용역/공사/물품 중 선택)
        6. determination_method: 낙찰 방식 추천 (추천만, 확정 아님)

        JSON 형식으로 출력하세요.
        """,
        agent=agent,
        expected_output="JSON 형식의 추출된 데이터 (ExtractedData 스키마 준수)"
    )


def create_classification_task(agent, extracted_data: Dict[str, Any]) -> Task:
    """
    STEP 3: 공고 유형 분류 Task

    Input: 추출된 데이터
    Output: ClassificationResult JSON
    """
    return Task(
        description=f"""
        다음 추출된 정보를 바탕으로 가장 적합한 공고 유형을 추천하세요.

        추출된 정보:
        {extracted_data}

        분류 기준 (국가계약법 참고):
        - 적격심사: 일정 금액 이상, 기술력 중요
        - 최저가: 일반 물품, 단순 공사
        - 협상에 의한 계약: 특수 용역, 긴급 상황

        출력 형식:
        {{
            "recommended_type": "추천 유형",
            "confidence": 0.0~1.0 사이 신뢰도,
            "reason": "추천 이유",
            "alternative_types": ["대안1", "대안2"]
        }}

        중요:
        - 신뢰도가 0.6 미만이면 솔직하게 낮게 표시하세요
        - '추천'이지 '확정'이 아닙니다
        """,
        agent=agent,
        expected_output="JSON 형식의 분류 결과 (ClassificationResult 스키마 준수)"
    )


def create_generation_task(
    agent,
    extracted_data: Dict[str, Any],
    template: str,
    user_prompt: str = ""
) -> Task:
    """
    STEP 4: 공고문 초안 생성 Task

    Input: 추출 데이터, 템플릿, 사용자 커스텀 프롬프트
    Output: 완성된 공고문 초안
    """
    user_instruction = f"\n\n추가 요청사항: {user_prompt}" if user_prompt else ""

    return Task(
        description=f"""
        다음 템플릿에 추출된 정보를 채워 공고문 초안을 작성하세요.

        템플릿:
        {template}

        채워야 할 데이터:
        {extracted_data}
        {user_instruction}

        요구사항:
        1. 템플릿의 구조를 유지하세요
        2. 모든 플레이스홀더({{변수}})를 정확한 값으로 치환하세요
        3. 공공 문서 톤앤매너를 유지하세요
        4. 명확하고 간결하게 작성하세요

        완성된 공고문을 출력하세요.
        """,
        agent=agent,
        expected_output="완성된 공고문 초안 (마크다운 또는 HTML 형식)"
    )


def create_validation_task(
    agent,
    generated_document: str,
    law_references: str
) -> Task:
    """
    STEP 5: 법령 검증 Task

    Input: 생성된 공고문, 최신 법령 텍스트
    Output: ValidationResult JSON
    """
    return Task(
        description=f"""
        다음 공고문이 관련 법령과 일치하는지 검토하세요.

        생성된 공고문:
        {generated_document}

        참조 법령:
        {law_references}

        검토 항목:
        1. 법령 조항과 공고문 내용의 일치 여부
        2. 표현의 정확성 (예: "예정가격 이하" vs "예정가격 미만")
        3. 누락된 필수 항목
        4. 법령 개정으로 인한 불일치

        출력 형식:
        {{
            "is_valid": true/false,
            "issues": [
                {{
                    "law": "법령명",
                    "section": "조항",
                    "issue_type": "이슈 유형",
                    "current_text": "현재 텍스트",
                    "suggestion": "수정 제안",
                    "severity": "low/medium/high"
                }}
            ],
            "checked_laws": ["검증한 법령 목록"],
            "timestamp": "검증 시각"
        }}

        중요:
        - 이슈를 발견하면 명확하게 설명하세요
        - 수정을 '제안'할 뿐, 법적 확정 판단은 하지 마세요
        - 문제가 없으면 is_valid: true, issues: [] 로 출력하세요
        """,
        agent=agent,
        expected_output="JSON 형식의 검증 결과 (ValidationResult 스키마 준수)"
    )


def create_revision_task(
    agent,
    original_document: str,
    validation_issues: list
) -> Task:
    """
    STEP 6: 수정 Task

    Input: 원본 공고문, 검증 이슈 목록
    Output: 수정된 공고문
    """
    return Task(
        description=f"""
        다음 검증 이슈를 반영하여 공고문을 수정하세요.

        원본 공고문:
        {original_document}

        발견된 이슈:
        {validation_issues}

        수정 지침:
        1. 각 이슈의 suggestion을 반영하세요
        2. severity가 high인 항목을 우선 처리하세요
        3. 전체 문맥을 유지하면서 수정하세요
        4. 수정 사항을 명확하게 표시하세요

        수정된 공고문을 출력하세요.
        """,
        agent=agent,
        expected_output="수정된 공고문 전문"
    )
