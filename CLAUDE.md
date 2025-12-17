# 🤖 Agentic CLAUDE.md

## 프로젝트 개요

본 문서는 **에이전트 해커톤 제출을 위한 FastAPI 기반 AI 입찰 공고문 자동 작성 에이전트**의 Claude 전용 개발 명세서이다.

본 시스템에서 Claude는 **법적 판단 주체가 아닌, 문서 이해·비교·재작성·제안 역할을 수행하는 서브 에이전트**로 동작한다.

---

## 1. 에이전트 철학 (중요)

이 시스템은 단순 LLM 호출이 아닌, 다음 **Agent Loop**를 따른다.

> **Observe → Decide → Act → Validate → Iterate**

Claude는 `Decide`와 `Act` 일부만 담당하며, **최종 흐름 제어는 백엔드 에이전트가 수행**한다.

---

## 2. 기술 스택

| 구분          | 내용                              |
| ----------- | ------------------------------- |
| Backend     | FastAPI (Python 3.10+)          |
| LLM         | Claude 3.5 Sonnet               |
| Agent State | Pydantic 기반 상태 모델               |
| Parsing     | pypdf, python-docx, (HWP 변환 우회) |
| RAG         | 국가법령정보센터 API                    |
| Auth        | JWT / OAuth2                    |

---

## 3. 에이전트 상태 모델 (Agent State)

```python
class AgentState(BaseModel):
    step: Literal[
        "upload",
        "extract",
        "classify",
        "generate",
        "validate",
        "revise",
        "complete"
    ]
    retry_count: int = 0
    last_error: Optional[str] = None
    selected_template_id: Optional[str] = None
```

> 모든 Claude 호출에는 **현재 AgentState를 반드시 포함**한다.

---

## 4. 에이전트 역할 분리

### 4.1 Claude의 책임 (허용)

* 문서 요약
* 필드 추출 (JSON Schema 기반)
* 공고 유형 **추천**
* 법령 개정 차이 설명
* 템플릿 수정 제안

### 4.2 Claude의 금지 행위

* 법적 적합성 단정
* 낙찰 방식 확정 판단
* 법령 해석에 대한 최종 결론

---

## 5. 핵심 에이전트 플로우

### STEP 1. 문서 업로드 → 텍스트 추출

* Backend: 파일 파싱
* Output: Raw Text

### STEP 2. 핵심 정보 추출 (Claude)

Claude Input:

* 발주계획서 텍스트
* JSON Schema (ExtractedData)
* AgentState(step="extract")

Claude Output:

```json
{
  "project_name": "",
  "estimated_amount": 0,
  "contract_period": "",
  "qualification_notes": "",
  "procurement_type": "",
  "determination_method": "추천: 적격심사"
}
```

---

### STEP 3. 공고 유형 분류 (Claude 제안)

Claude Input:

* 추출 데이터
* 분류 기준 요약 (국가계약법)

Claude Output:

```json
{
  "recommended_type": "적격심사",
  "confidence": 0.78,
  "reason": "금액 기준 및 용역 유형에 부합"
}
```

> confidence < 0.6 → 사용자 질의 생성

---

### STEP 4. 공고문 초안 생성

* Backend: 템플릿 선택
* Claude: 템플릿 채움 + 사용자 커스텀 프롬프트 반영

---

### STEP 5. 법령 검증 (RAG)

Claude Input:

* 생성된 공고문
* 최신 법령 텍스트

Claude Output:

```json
{
  "issues": [
    {
      "law": "국가계약법",
      "section": "제27조",
      "suggestion": "표현을 '예정가격 이하'로 수정 권장"
    }
  ]
}
```

---

### STEP 6. Agent Decision Policy

```text
IF issues.length == 0:
    state = complete
ELSE IF retry_count < 2:
    apply suggestions
    retry_count += 1
    state = revise
ELSE:
    escalate to human
```

---

## 6. FastAPI 엔드포인트

| Endpoint                     | 설명             |
| ---------------------------- | -------------- |
| POST /api/v1/agent/upload    | 문서 업로드 + 상태 생성 |
| POST /api/v1/agent/run       | Agent Loop 실행  |
| GET /api/v1/agent/state/{id} | 현재 상태 조회       |
| POST /api/v1/agent/feedback  | 사용자 피드백 반영     |

---

## 7. 해커톤 어필 포인트

* Claude를 **판단 주체가 아닌 협력 에이전트로 제한**
* Agent State 기반 반복 실행
* 법적 책임 분리 구조
* 공공 도메인 특화 Agent

---

## 8. 결론

이 시스템은 LLM을 통제 불가능한 블랙박스가 아닌,
**정책·상태·루프에 종속된 도구형 에이전트**로 설계한다.

Claude는 잘 읽고, 잘 설명하고, 조심스럽게 제안한다.
결정은 언제나 시스템과 사람이 한다.
