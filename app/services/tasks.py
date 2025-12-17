"""
CrewAI Tasks 정의

각 Task는 Agent에게 할당되는 구체적인 작업입니다.
CLAUDE.md의 Agent Loop를 따라 순차적으로 실행됩니다.
"""

from crewai import Task
from typing import Dict, Any, List


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
    return Task(
        description=f"""
        당신은 한국환경공단의 입찰 공고문 생성 규칙을 완벽히 학습한 AI입니다.
        제공된 [발주 데이터]를 분석하여 **공고 유형**과 **세부 조건**을 결정하세요.

        ---
        [발주 데이터]
        {extracted_data}
        ---

        [🔥 공고 분류 및 제약조건 로직 (Business Logic)]
        
        1. 💰 금액 분석 (VAT 처리):
           - 입력된 예산액에서 부가세를 제외한 **'추정가격'**을 산출하세요. 

        2. ⚖️ 낙찰자 결정방법 (추정가격 기준):
           - **1억 원 초과**: 무조건 **'적격심사'** (소액수의 절대 불가) [cite: 100, 101]
           - **1억 원 이하**: 기본 **'소액수의'** (단, 발주자 요청 시 '적격심사' 가능) [cite: 100]

        3. 📜 적격심사 세부기준 (별표 적용 - 추정가격 기준):
           - 10억 원 이상: [별표 1] [cite: 137]
           - 2.3억 원(고시금액) 이상 ~ 10억 원 미만: [별표 2] [cite: 138]
           - 2.3억 원 미만 (단, 1억 초과 또는 적격심사 선택 시): [별표 3] [cite: 139]
           - 소액수의인 경우: "해당없음"

        4. 🏢 중소기업 경쟁 제한 (추정가격 기준):
           - **1억 원 미만**: '소기업/소상공인' 제한 필수 [cite: 154]
           - **1억 원 이상 ~ 2.3억 원 미만**: '중소기업/소상공인' 제한 필수 [cite: 155]
           - **2.3억 원 이상**: 제한 없음 (일반경쟁 가능) [cite: 158]

        5. 📅 공고 기간 산정:
           - **공고 게시일**: 발주 요청일의 **다음 날**
           - **마감일(소액수의)**: 게시일로부터 **영업일(주말/공휴일 제외) 3일 후** [cite: 123]
           - **마감일(적격심사)**: 게시일로부터 **7일 후** [cite: 121]

        ---
        
        [출력 형식 (JSON Schema)]
        결과는 반드시 아래의 중첩된 JSON 구조를 따르세요:

        {{
            "financials": {{
                "total_budget_inc_vat": 0,  // 부가세 포함 총 예산
                "estimated_price_exc_vat": 0, // 부가세 제외 추정가격 (판단 기준값)
                "vat_included": true // 입력 데이터가 부가세 포함인지 여부
            }},
            "classification": {{
                "purchase_type": "물품", // 물품, 용역, 공사 중 택 1
                "contract_method": "소액수의" // 소액수의, 적격심사 중 택 1
            }},
            "constraints": {{
                "applied_annex": "별표3", // 적격심사인 경우 적용할 별표 (없으면 null)
                "sme_restriction": "소기업_소상공인", // 소기업_소상공인, 중소기업_소상공인, 없음 중 택 1
                "reason": "추정가격 9천만 원으로 소액수의 및 소기업 제한 적용"
            }},
            "schedule": {{
                "notice_start_date": "YYYY-MM-DD",
                "notice_end_date": "YYYY-MM-DD",
                "duration_desc": "영업일 3일" // 또는 "7일"
            }}
        }}
        """,
        agent=agent,
        expected_output="계층형 JSON 형식의 분류 결과"
    )


def create_generation_task(
    agent,
    extracted_data: Dict[str, Any],
    few_shot_examples: List[str]
) -> Task:
    """
    STEP 4: 공고문 초안 생성 Task (PDF 샘플 학습 방식)

    Agent가 여러 PDF 샘플을 학습해서 구조와 패턴을 파악하고,
    추출된 키워드로 공고문을 생성합니다.

    Input:
        - extracted_data: 추출된 키워드 데이터
        - few_shot_examples: 실제 공고문 샘플들 (여러 개)

    Output: 완성된 공고문
    """
    import json

    # 샘플들을 구분해서 표시
    examples_section = ""
    if few_shot_examples:
        examples_section = "## STEP 1: 실제 공고문 샘플 학습\n\n"
        examples_section += "다음은 실제 입찰 공고문 샘플들입니다.\n"
        examples_section += "이 샘플들을 분석하여 **공통 구조**와 **가변 부분**을 파악하세요:\n\n"

        for i, example in enumerate(few_shot_examples, 1):
            examples_section += f"### 📄 샘플 {i}\n\n```\n{example}\n```\n\n"

        examples_section += """
**학습 포인트:**
1. **고정 구조 파악**: 모든 샘플에 공통으로 나타나는 섹션과 순서
2. **가변 데이터 식별**: 샘플마다 다른 부분 (프로젝트명, 금액, 날짜 등)
3. **표현 패턴**: 금액, 날짜, 기간 등의 표기 방식
4. **문체와 톤**: 공식적인 표현, 법령 인용 방식 등

---

"""

    return Task(
        description=f"""
        당신은 국가계약법 기반 입찰 공고문 작성 전문가입니다.

        {examples_section}

        ## STEP 2: 추출된 데이터

        다음은 발주계획서에서 추출한 핵심 정보입니다:

        ```json
        {json.dumps(extracted_data, ensure_ascii=False, indent=2)}
        ```

        ## STEP 3: 공고문 작성

        위 샘플들의 구조를 따라 새로운 공고문을 작성하세요.

        ### 작성 방법:

        1. **구조 재현**
           - 샘플들에서 파악한 공통 구조(섹션 순서)를 그대로 사용
           - 각 섹션의 제목과 형식을 일관되게 유지

        2. **데이터 매핑**
           - 추출된 데이터를 적절한 위치에 배치
           - 샘플에서 본 표현 방식을 따름:
             * 금액: "금 OOOO원정 (₩XX,XXX,XXX)" 형식
             * 날짜: "YYYY년 MM월 DD일" 형식
             * 기간: "계약일로부터 O개월" 형식

        3. **자동 생성 필드**
           - 공고번호: "2025-XXXX" 형식
           - 공고일: 오늘 날짜
           - 입찰마감일: 공고일 + 7일
           - 개찰일: 마감일 + 1일

        4. **문체 유지**
           - 샘플과 동일한 격식있는 공공문서 톤
           - 법령 인용 시 샘플 방식 따름
           - 명확하고 간결한 표현

        5. **필수 포함 요소**
           - 공고 개요 (공고명, 번호, 일자)
           - 사업 개요 (사업명, 예산, 기간)
           - 입찰 방식 (낙찰자 결정 방법)
           - 참가 자격
           - 제출 서류
           - 입찰 일정
           - 문의처

        6. **금지 사항**
           - 샘플에 없는 임의 내용 추가 금지
           - 추출 데이터에 없는 정보 지어내기 금지
           - 법적 해석이나 판단 포함 금지

        완성된 공고문을 마크다운 형식으로 출력하세요.
        """,
        agent=agent,
        expected_output="완성된 입찰 공고문 (마크다운 형식)"
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
