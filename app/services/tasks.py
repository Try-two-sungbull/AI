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


def create_self_reflection_task(
    agent,
    generated_document: str,
    extracted_data: Dict[str, Any],
    classification: Dict[str, Any]
) -> Task:
    """
    Generator 셀프 리플렉션 Task (제한적 사전 점검)
    
    Generator가 자신의 출력을 제한적으로 검토합니다.
    - 필수 섹션 누락 여부
    - 플레이스홀더 남아있음 여부
    - 분류 결과와 일치 여부
    - 기본 구조 정확성
    
    ⚠️ 중요: 법령 해석이나 법적 판단은 하지 않습니다 (Validator가 담당)
    
    Input:
        - generated_document: Generator가 생성한 문서
        - extracted_data: 추출된 데이터 (참고용)
        - classification: 분류 결과 (일치 여부 확인용)
    
    Output: SelfReflectionResult JSON
    """
    import json
    
    recommended_type = classification.get("recommended_type", "")
    
    return Task(
        description=f"""
당신이 방금 생성한 다음 문서를 **제한적으로만** 검토하세요.

⚠️ 중요: 이것은 "검증"이 아니라 "사전 점검(precheck)"입니다.
법령 해석이나 법적 판단은 하지 마세요. 기계적 오류만 확인하세요.

생성된 문서:
```markdown
{generated_document}
```

참고 정보:
- 분류 결과: {recommended_type}
- 추출된 데이터: {json.dumps(extracted_data, ensure_ascii=False, indent=2)[:500]}

검토 항목 (이것만 확인):
1. **필수 섹션 존재 여부**
   - "위와 같이 공고합니다" 포함 여부
   - "기타사항", "입찰무효", "입찰보증금", "청렴계약이행", "예정가격", "공동계약", "입찰참가자격" 등 필수 섹션

2. **플레이스홀더 남아있음 여부**
   - {{project_name}}, {{estimated_amount}} 같은 플레이스홀더가 남아있는지
   - 빈 값이나 불완전한 데이터가 있는지

3. **분류 결과와 일치 여부**
   - 분류 결과가 "{recommended_type}"인데, 문서에 다른 방식(예: "최저가", "적격심사")이 잘못 언급되었는지
   - 예: "적격심사"로 분류되었는데 문서에 "최저가 낙찰" 문구가 있는지

4. **기본 구조 정확성**
   - 섹션 번호가 연속적인지
   - 테이블 형식이 올바른지

⚠️ 하지 말아야 할 것:
- 법령 해석
- 법적 적합성 판단
- 복잡한 법적 판단
- severity 판단 (이건 Validator가 담당)

출력 형식 (JSON):
{{
    "self_check_passed": true/false,
    "issues": [
        {{
            "type": "missing_section" | "placeholder_remaining" | "inconsistency" | "structure_error",
            "confidence": "high" | "low",
            "fix_type": "mechanical" | "content_related",
            "location": "섹션 위치 또는 라인 번호",
            "description": "문제 설명",
            "patch": {{
                "action": "replace" | "add" | "remove",
                "target": "수정할 텍스트 또는 위치",
                "value": "수정할 값 (action이 replace인 경우)"
            }}
        }}
    ],
    "auto_fixable": {{
        "allowed": true/false,
        "fix_scope": "placeholder_only" | "section_header_only" | "none"
    }}
}}

중요 규칙:
1. 문제가 없으면 self_check_passed: true, issues: [] 로 출력
2. patch는 구조적이고 명확하게 제시 (자유 텍스트 수정 제안 ❌)
3. auto_fixable.allowed는 안전한 수정만 true (placeholder, 섹션 헤더 등)
4. 법령 관련 문제는 issues에 포함하지 마세요 (Validator가 담당)
""",
        agent=agent,
        expected_output="JSON 형식의 셀프 리플렉션 결과 (SelfReflectionResult 스키마 준수)"
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


def create_change_validation_task(
    agent,
    comparison_result: dict,
    current_template: str
) -> Task:
    """
    변경사항 검증 Task

    Input:
        - comparison_result: 비교 Agent의 결과 (changes 포함)
        - current_template: 현재 DB에 저장된 최신 템플릿

    Output: 검증된 변경사항 (실제로 필요한 것만)
    """
    changes_text = ""
    for idx, change in enumerate(comparison_result.get("changes", []), 1):
        changes_text += f"\n{idx}. **{change.get('section', 'N/A')}**\n"
        changes_text += f"   - 유형: {change.get('type', 'N/A')}\n"
        changes_text += f"   - 구버전: {change.get('old_text', 'N/A')[:100]}\n"
        changes_text += f"   - 신버전: {change.get('new_text', 'N/A')[:100]}\n"
        changes_text += f"   - 이유: {change.get('reason', 'N/A')}\n"

    has_changes = comparison_result.get("has_changes", False)
    num_changes = len(comparison_result.get("changes", []))

    return Task(
        description=f"""
        비교 Agent가 보고한 변경사항을 검증하세요.

        ## 현재 템플릿 (DB에 저장된 최신 버전)
        ```
        {current_template[:3000]}
        ```

        ## 보고된 변경사항
        - has_changes: {has_changes}
        - 변경사항 개수: {num_changes}

        {changes_text}

        ---

        ## 🔄 CRITICAL - Reflection 프로토콜

        **모순 감지**:
        - 만약 `has_changes = False`인데 `changes` 배열에 {num_changes}개 항목이 있다면, 이는 **명백한 모순**입니다.
        - 이 경우 **즉시 재검사**를 수행해야 합니다.

        **재검사 절차**:
        1. 각 변경사항을 현재 템플릿과 **하나씩 다시 대조**
        2. `new_text`가 정말로 템플릿에 없는지 확인
        3. 띄어쓰기/표현 차이만 있고 실질적으로 같은 내용인지 판단
        4. 재검사 결과를 최종 결과로 채택
        5. summary에 "(재검사 완료)" 명시

        ---

        ## 검증 절차

        1. **이미 반영 확인**
           - 각 변경사항의 `new_text`가 현재 템플릿에 이미 있는지 확인
           - 있으면 → "이미 반영됨" (제외)

        2. **실질적 차이 확인**
           - 띄어쓰기, 줄바꿈만 다른가? → 제외
           - 동의어 표현만 다른가? (예: "입찰자" vs "입찰참가자") → 제외
           - 순서만 다른가? → 제외

        3. **유의미한 변경만 승인**
           - 새로운 섹션 추가
           - 법령 표현 실질적 변경
           - 필수 조건 변경

        ---

        ## 출력 형식 (JSON)

        ```json
        {{
            "has_real_changes": true,  // 실질적 변경이 있으면 true
            "approved_changes": [
                {{
                    "section": "## 6. 청렴계약이행 서약서 제출",
                    "type": "added",
                    "reason": "현재 템플릿에 없는 새로운 섹션"
                }}
            ],
            "rejected_changes": [
                {{
                    "section": "## 5. 예정가격 및 낙찰자 결정방법",
                    "reason": "이미 반영됨. 현재 템플릿에 '예정가격 범위 내' 표현 존재"
                }}
            ],
            "summary": "1개 승인, 1개 거부 (이미 반영됨)"  // 재검사 수행했으면 "(재검사 완료)" 추가
        }}
        ```

        ⚠️ **중요**:
        - `approved_changes`가 비어있으면 `has_real_changes: false`로 반환하세요!
        - 모순을 발견하면 반드시 재검사를 수행하세요!
        """,
        agent=agent,
        expected_output="JSON 형식의 검증 결과 (approved_changes, rejected_changes, 재검사 여부 포함)"
    )


def create_multi_template_comparison_task(
    agent,
    latest_docs: list,
    our_template_content: str,
    template_version: str = None,
    recheck_guideline: dict = None
) -> Task:
    """
    여러 최신 공고문과 우리 템플릿 비교 Task

    Input:
        - latest_docs: [{"url": "...", "content": "...", "index": 1}, ...]
        - our_template_content: 우리 템플릿 내용
        - template_version: 현재 템플릿 버전 (예: "1.0.1")
        - recheck_guideline: 재검사 지침 (Validator가 제공)

    Output: 변경사항 JSON
    """
    # 공고문들을 텍스트로 결합
    docs_text = ""
    for doc in latest_docs:
        docs_text += f"\n\n### 공고문 #{doc['index']}\n```\n{doc['content'][:3000]}\n```\n"  # 각 문서 3000자 제한

    version_info = f" (현재 버전: {template_version})" if template_version else ""

    # 재검사 지침 추가
    recheck_info = ""
    if recheck_guideline:
        ignore_list = recheck_guideline.get("ignore", [])
        focus_list = recheck_guideline.get("focus", [])
        recheck_info = f"""

🔄 **재검사 모드 활성화**

다음 기준에 따라 재검사를 수행하세요:

**무시할 차이**:
{chr(10).join([f"- {item}" for item in ignore_list])}

**집중할 차이**:
{chr(10).join([f"- {item}" for item in focus_list])}
"""

    return Task(
        description=f"""
        최신 나라장터 공고문 **{len(latest_docs)}개**와 우리 템플릿{version_info}을 비교하여 변경사항을 분석하세요.

        ⚠️ **중요**: 우리 템플릿은 이미 이전 검증에서 업데이트되었을 수 있습니다.
        따라서 **의미 있는 실질적인 차이만** 변경사항으로 보고하세요.
        {recheck_info}

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

        ⚠️ **CRITICAL**:
        1. 변경사항이 없으면 `has_changes: false`, `changes: []` (빈 배열), `summary: "변경사항 없음"`
        2. 변경사항이 있으면 `has_changes: true`, `changes` 배열에 항목 추가, `updated_template` 전체 포함

        ### 변경사항이 있는 경우:
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

        ### 변경사항이 없는 경우:
        ```json
        {{
            "has_changes": false,
            "summary": "변경사항 없음. 우리 템플릿이 이미 최신 상태입니다.",
            "changes": [],
            "new_version_recommended": false
        }}
        ```

        ⚠️ **중요**: `has_changes: false`일 때는 반드시 `changes: []` (빈 배열)을 반환하세요!

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

        ### 🚫 무시해야 할 차이 (변경사항으로 보고하지 마세요)
        1. **띄어쓰기, 줄바꿈, 들여쓰기** 차이
        2. **구두점** (쉼표, 마침표 위치) 차이
        3. **동의어 표현** (예: "입찰참가자" vs "입찰자", "제출하여야" vs "제출해야")
        4. **순서만 다른 경우** (내용은 동일)
        5. **플레이스홀더 변수명** 차이 ({{project_name}} vs {{사업명}})
        6. **예시 데이터** 차이 (실제 템플릿 구조는 동일)

        ### ✅ 보고해야 할 차이 (실질적 변경)
        1. **필수 섹션 추가/삭제** (예: 새로운 "청렴계약" 섹션 추가)
        2. **법령 표현 변경** (예: "예정가격 이하" → "예정가격 범위 내")
        3. **필수 조건 변경** (예: 입찰보증금 비율 변경)
        4. **구조 변경** (섹션 번호 재배치, 대분류 변경)
        5. **실질적 내용 변경** (요구사항, 절차, 기한 등)
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
