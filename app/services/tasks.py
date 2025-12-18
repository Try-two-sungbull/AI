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
        1. project_name: 문서의 제목 (구매계획서의 제목이 공고명이 됨. 예: "실내공기질 자동측정망 가스상 측정장비 구매 계획(안)")
        2. item_name: 품목명
        3. estimated_amount: 추정 금액 (숫자로, 원 단위, VAT 제외)
        4. total_budget_vat: 총 예산 (VAT 포함)
        5. contract_period: 계약 기간
        6. delivery_deadline_days: 납품 기한 (일)
        7. procurement_type: 조달 유형 (용역/공사/물품 중 선택)
        8. procurement_method_raw: 조달 방법 원문 (예: 일반경쟁입찰)
        9. determination_method: 낙찰 방식 추천 (추천만, 확정 아님)
        10. detail_item_codes: 세부 품목 번호 목록 (있을 경우)
        11. industry_codes: 업종코드 목록 (있을 경우)
        12. is_joint_contract: 공동계약 여부 (true/false)
        13. has_region_restriction: 지역제한 여부 (true/false)
        14. restricted_region: 제한 지역 (지역제한이 있는 경우)
        15. qualification_notes: 자격 요건 및 특이사항

        JSON 형식으로 출력하세요.
        """,
        agent=agent,
        expected_output="JSON 형식의 추출된 데이터 (ExtractedData 스키마 준수)"
    )


def create_classification_task(agent, extracted_data: Dict[str, Any]) -> Task:
    """
    STEP 3: 공고 유형 분류 Task (Classifier Agent + Rule Engine Tool)
    
    Classifier Agent가 Rule Engine Tool을 사용하여 분류를 수행합니다.
    """
    import json
    
    return Task(
        description=f"""
        당신은 국가계약법 기반 공고 유형 분류 전문가입니다.
        
        ## 작업 목표
        
        제공된 발주 데이터를 분석하여 **공고 유형**과 **세부 조건**을 결정하세요.
        
        **중요**: 반드시 **Rule Engine 분류 도구(rule_engine_classify)**를 사용하여 분류를 수행하세요.
        Rule Engine은 국가계약법 기반 명시적 규칙을 적용합니다.
        
        ---
        
        ## STEP 1: 발주 데이터
        
        다음은 추출된 발주 데이터입니다:
        
        ```json
        {json.dumps(extracted_data, ensure_ascii=False, indent=2)}
        ```
        
        ---
        
        ## STEP 2: Rule Engine Tool 사용
        
        **반드시 `rule_engine_classify` Tool을 사용**하여 분류를 수행하세요.
        
        Tool 사용 방법:
        1. 위 발주 데이터를 JSON 문자열로 변환
        2. `rule_engine_classify` Tool에 JSON 문자열 전달
        3. Tool이 반환한 분류 결과를 기반으로 최종 결과 생성
        
        ---
        
        ## STEP 3: 출력 형식
        
        Rule Engine Tool의 결과를 기반으로 다음 JSON 형식으로 출력하세요:
        
        ```json
        {{
            "recommended_type": "소액수의" 또는 "적격심사",
            "confidence": 0.0 ~ 1.0,
            "reason": "분류 이유",
            "alternative_types": ["대안 유형 목록"],
            "reason_trace": {{"Rule Engine이 반환한 reason_trace 객체"}},
            "contract_nature": "계약 성격",
            "purchase_type": "물품/용역/공사",
            "estimated_price_exc_vat": 0,
            "applied_annex": "별표1/별표2/별표3 또는 null",
            "sme_restriction": "소기업_소상공인/중소기업_소상공인/없음"
        }}
        ```
        
        ---
        
        ## 중요 사항
        
        - Rule Engine Tool의 결과를 그대로 사용하되, 필요시 설명을 추가할 수 있습니다
        - 법적 판단은 Rule Engine이 수행하므로, 당신은 결과를 해석하고 설명하는 역할입니다
        - 신뢰도가 낮은 경우(<0.6) 대안을 제시하세요
        """,
        agent=agent,
        expected_output="JSON 형식의 분류 결과 (Rule Engine Tool 결과 기반)"
    )


def create_generation_task(
    agent,
    filled_template: str,
    extracted_data: Dict[str, Any],
    classification: Dict[str, Any]
) -> Task:
    """
    STEP 4: 공고문 초안 생성 Task (템플릿 + 데이터 매핑 방식)

    템플릿에 이미 데이터가 채워진 상태에서,
    LLM이 문장 다듬기만 수행합니다.

    Input:
        - filled_template: 이미 플레이스홀더가 채워진 템플릿
        - extracted_data: 추출된 키워드 데이터 (참고용)
        - classification: Rule Engine 분류 결과 (가드용)

    Output: 완성된 공고문
    """
    import json

    # 분류 결과에서 고정값 추출 (Generator가 변경하면 안 되는 값)
    fixed_values = {
        "contract_method": classification.get("recommended_type", ""),
        "applied_annex": classification.get("applied_annex"),
        "sme_restriction": classification.get("sme_restriction", ""),
    }
    
    return Task(
        description=f"""입력받은 템플릿을 100% 그대로 반환하세요. 변경, 추가, 수정 금지.

템플릿:
```markdown
{filled_template}
```

⚠️ 절대 변경 금지 사항:
- 템플릿의 모든 섹션을 그대로 유지하세요
- 섹션 1부터 10까지, 그리고 "이의제기 및 신고채널 안내", "위와 같이 공고합니다"까지 모두 포함하세요
- 어떤 섹션이나 문장도 삭제하지 마세요
- 어떤 내용도 추가하지 마세요
- 플레이스홀더나 변수명을 변경하지 마세요

규칙:
1. 템플릿을 처음부터 끝까지 그대로 출력만 하세요
2. 변경/추가/수정/삭제 절대 금지
3. 반드시 끝까지 모두 출력하세요 (중간에 멈추지 마세요)
4. 마지막에 "위와 같이 공고합니다"가 반드시 포함되어야 합니다

출력 형식:
- 마크다운 코드 블록 없이 템플릿 내용만 그대로 출력하세요
- 템플릿 전체를 반드시 포함하세요""",
        agent=agent,
        expected_output="템플릿을 그대로 반환한 완전한 공고문 (모든 섹션 포함, 변경 없음)"
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
        다음 공고문의 **변경 가능한 섹션만** 검토하세요.

        검증 대상 섹션 (이 섹션만 확인):
        - ## 2. 견적(입찰) 및 계약방식 (contract_method_detail, qualification_review_target)
        - ## 5. 예정가격 및 낙찰자 결정방법 (estimated_price_method, 낙찰자 선정 문구)

        생성된 공고문:
        {generated_document}

        참조 법령:
        {law_references}

        검토 항목 (위 섹션만):
        1. 법령 조항과 공고문 내용의 일치 여부
        2. 표현의 정확성 (예: "예정가격 이하" vs "예정가격 미만")
        3. Rule Engine 결정값과 일치 여부

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
    STEP 6: 수정 Task (문제 구간만 전달하여 토큰 절감)

    Input: 원본 공고문, 검증 이슈 목록
    Output: 수정된 공고문
    """
    import json
    
    # 문제 구간만 추출 (토큰 절감)
    issue_contexts = []
    for issue in validation_issues:
        current_text = issue.get("current_text", "")
        suggestion = issue.get("suggestion", "")
        location = issue.get("location", "위치 미상")
        
        # 해당 문장 주변만 추출 (전체 문서 대신)
        issue_contexts.append(f"""
위치: {location}
현재: {current_text}
수정: {suggestion}
""")
    
    # 원본 문서 전체 전달 (1000자 제한 제거)
    # Revision Agent가 전체 문서를 받아야 모든 섹션을 유지할 수 있음
    return Task(
        description=f"""
⚠️ 중요: 원본 문서를 처음부터 끝까지 그대로 유지하세요. 어떤 섹션이나 문장도 삭제하지 마세요.

수정할 이슈 (이 부분만 수정):
{chr(10).join(issue_contexts)}

원본 문서 (전체, 절대 변경 금지):
```markdown
{original_document}
```

⚠️ 절대 변경 금지 사항:
- 원본 문서의 모든 섹션을 그대로 유지하세요
- 섹션 1부터 10까지, 그리고 "이의제기 및 신고채널 안내", "위와 같이 공고합니다"까지 모두 포함하세요
- 어떤 섹션이나 문장도 삭제하지 마세요
- 어떤 내용도 추가하지 마세요 (제시된 이슈 수정 제외)

수정 규칙:
1. 제시된 이슈의 suggestion만 반영하세요
2. 나머지 텍스트는 절대 변경 금지
3. 수정 사항 표시([수정됨] 등) 추가 금지
4. 전체 문서를 처음부터 끝까지 다시 출력하되, 제시된 부분만 수정
5. 반드시 "위와 같이 공고합니다"까지 포함하세요

출력 형식:
- 마크다운 코드 블록 없이 문서 내용만 그대로 출력하세요
- 원본 문서 전체를 반드시 포함하세요 (중간에 멈추지 마세요)
""",
        agent=agent,
        expected_output="수정된 공고문 (제시된 이슈만 반영, 나머지 전체 유지, 모든 섹션 포함)"
    )


def create_multi_template_comparison_task(
    agent,
    latest_docs: list,
    our_template_content: str
) -> Task:
    """
    여러 최신 공고문과 우리 템플릿 비교 Task

    Input:
        - latest_docs: [{"url": "...", "content": "...", "index": 1}, ...]
        - our_template_content: 우리 템플릿 내용

    Output: 변경사항 JSON
    """
    # 공고문들을 텍스트로 결합
    docs_text = ""
    for doc in latest_docs:
        docs_text += f"\n\n### 공고문 #{doc['index']}\n```\n{doc['content'][:3000]}\n```\n"  # 각 문서 3000자 제한

    return Task(
        description=f"""
        최신 나라장터 공고문 **{len(latest_docs)}개**와 우리 템플릿을 비교하여 변경사항을 분석하세요.

        ## 최신 공고문들 (나라장터)
        {docs_text}

        ## 우리 템플릿
        ```
        {our_template_content[:5000]}
        ```

        ---

        ## 분석 지침

        1. **공통 패턴 찾기**
           - {len(latest_docs)}개 공고문에서 **공통적으로 나타나는** 섹션과 내용 식별
           - 2개 이상의 공고문에 있으면 "표준"으로 간주

        2. **구조 비교**
           - 섹션 구성이 같은지 확인
           - 섹션 번호가 바뀌었는지 확인

        3. **내용 비교**
           - 각 섹션의 텍스트가 달라진 부분 찾기
           - **여러 공고문에 공통적으로 있는데 우리 템플릿에 없는 것** → `added`
           - **우리 템플릿에만 있고 공고문들에 없는 것** → `removed`
           - **둘 다 있지만 표현이 다른 것** → `modified`

        4. **중요도 평가**
           - `high`: 필수 섹션 추가/삭제, 법령 관련 변경
           - `medium`: 표현 방식 변경, 순서 변경
           - `low`: 띄어쓰기, 구두점 등 사소한 변경

        ---

        ## 출력 형식 (JSON)

        ⚠️ **CRITICAL**: `updated_template` 필드는 **절대 축약하지 말고 전체 템플릿을 완전히 작성**하세요!

        ```json
        {{
            "has_changes": true,
            "summary": "섹션 2개 추가, 1개 변경됨",
            "changes": [
                {{
                    "section": "## 5. 예정가격 및 낙찰자 결정방법",
                    "type": "modified",
                    "severity": "high",
                    "old_text": "예정가격 이하로 입찰한 자",
                    "new_text": "예정가격 범위 내에서 입찰한 자",
                    "reason": "법령 표현 변경 (공고문 {len(latest_docs)}개 모두 동일)",
                    "frequency": "{len(latest_docs)}/{len(latest_docs)}"
                }},
                {{
                    "section": "## 11. 청렴계약 이행 서약",
                    "type": "added",
                    "severity": "high",
                    "new_text": "청렴계약 이행 서약서를 제출해야 합니다.",
                    "reason": "신규 섹션 추가 (공고문 {len(latest_docs)}개 중 {len(latest_docs)}개에 존재)",
                    "frequency": "{len(latest_docs)}/{len(latest_docs)}"
                }}
            ],
            "new_version_recommended": true,
            "updated_template": "(여기에 우리 템플릿 전체를 복사하고 changes만 적용한 완전한 마크다운 - 절대 축약 금지!)"
        }}
        ```

        **필수 요구사항**:
        - `frequency` 필드에 "몇 개 공고문 중 몇 개에 나타났는지" 표시
        - 최소 2개 이상의 공고문에 나타난 변경사항만 포함
        - **`updated_template` 필드는 반드시 완전한 마크다운 템플릿 전체를 포함**
          - ❌ "...", "(생략)", "(계속...)" 같은 축약 **절대 금지**
          - ✅ 모든 섹션 (## 1. ~ ## 마지막 섹션)을 전부 포함
          - ✅ 우리 템플릿을 기반으로 changes만 적용한 완전한 문서
        - {{변수명}} 플레이스홀더는 그대로 유지

        ---

        ## 중요 사항

        - 변경사항이 없으면 `has_changes: false`로 반환
        - 사소한 띄어쓰기 차이는 무시
        - {{변수명}} 같은 플레이스홀더는 무시
        - **여러 공고문에서 일관되게 나타나는 변경**에만 집중
        - 법령 관련 표현 변경은 severity를 high로 설정
        """,
        agent=agent,
        expected_output="JSON 형식의 변경사항 분석 결과 (여러 공고문 기준)"
    )


def create_template_comparison_task(
    agent,
    latest_doc_content: str,
    our_template_content: str
) -> Task:
    """
    템플릿 비교 Task

    최신 공고문과 우리 템플릿을 비교하여 변경사항 추출

    Input:
        - latest_doc_content: 최신 나라장터 공고문 내용
        - our_template_content: 우리 템플릿 내용

    Output: 변경사항 JSON
    """
    import json

    return Task(
        description=f"""
        최신 나라장터 공고문과 우리 템플릿을 비교하여 변경사항을 분석하세요.

        ## 최신 공고문 (나라장터)
        ```
        {latest_doc_content[:5000]}  # 너무 길면 5000자로 제한
        ```

        ## 우리 템플릿
        ```
        {our_template_content[:5000]}  # 너무 길면 5000자로 제한
        ```

        ---

        ## 분석 지침

        1. **구조 비교**
           - 섹션 구성이 같은지 확인 (예: "## 1. 사업명", "## 2. 견적방식" 등)
           - 섹션 번호가 바뀌었는지 확인

        2. **내용 비교**
           - 각 섹션의 텍스트가 달라진 부분 찾기
           - 추가된 문장, 삭제된 문장, 변경된 문장 식별

        3. **변경 유형 분류**
           - `added`: 최신 공고문에만 있는 내용
           - `removed`: 우리 템플릿에만 있는 내용
           - `modified`: 둘 다 있지만 내용이 다른 부분

        4. **중요도 평가**
           - `high`: 필수 섹션 추가/삭제, 법령 관련 변경
           - `medium`: 표현 방식 변경, 순서 변경
           - `low`: 띄어쓰기, 구두점 등 사소한 변경

        ---

        ## 출력 형식 (JSON)

        ```json
        {{
            "has_changes": true,
            "summary": "섹션 2개 추가, 1개 변경됨",
            "changes": [
                {{
                    "section": "## 5. 예정가격 및 낙찰자 결정방법",
                    "type": "modified",
                    "severity": "high",
                    "old_text": "예정가격 이하로 입찰한 자",
                    "new_text": "예정가격 범위 내에서 입찰한 자",
                    "reason": "법령 표현 변경"
                }},
                {{
                    "section": "## 11. 청렴계약 이행 서약",
                    "type": "added",
                    "severity": "high",
                    "new_text": "청렴계약 이행 서약서를 제출해야 합니다.",
                    "reason": "신규 섹션 추가"
                }}
            ],
            "new_version_recommended": true,
            "updated_template": "# 입찰공고\\n\\n## 1. 입찰에 부치는 사항\\n...\\n\\n## 11. 청렴계약 이행 서약\\n\\n청렴계약 이행 서약서를 제출해야 합니다.\\n..."
        }}
        ```

        **중요**: `updated_template` 필드에 변경사항을 반영한 완전한 마크다운 템플릿을 포함하세요.
        - 우리 템플릿을 기반으로 함
        - `added` 항목은 해당 섹션에 추가
        - `modified` 항목은 해당 부분을 new_text로 교체
        - `removed` 항목은 해당 섹션 삭제
        - {{변수명}} 플레이스홀더는 그대로 유지
        ```

        ---

        ## 중요 사항

        - 변경사항이 없으면 `has_changes: false`로 반환
        - 사소한 띄어쓰기 차이는 무시
        - {{변수명}} 같은 플레이스홀더는 무시
        - 법령 관련 표현 변경은 severity를 high로 설정
        """,
        agent=agent,
        expected_output="JSON 형식의 변경사항 분석 결과"
    )
