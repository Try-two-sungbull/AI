# 템플릿 플레이스홀더 규칙

> **목적**: 템플릿 작성자와 개발자 간의 계약(contract) 정의
> 
> 이 문서는 템플릿에 사용되는 모든 플레이스홀더의 의미, 데이터 소스, 필수/선택 여부를 명확히 정의합니다.

---

## 📋 목차

1. [공통 플레이스홀더](#공통-플레이스홀더)
2. [템플릿별 특수 플레이스홀더](#템플릿별-특수-플레이스홀더)
3. [데이터 소스 매핑](#데이터-소스-매핑)
4. [Rule Engine 결정값 (가드 필수)](#rule-engine-결정값-가드-필수)
5. [파생 필드 생성 규칙](#파생-필드-생성-규칙)

---

## 공통 플레이스홀더

모든 템플릿에서 공통으로 사용되는 플레이스홀더입니다.

### 기본 정보

| 플레이스홀더 | 필수 | 데이터 소스 | 설명 | 기본값 |
|------------|------|------------|------|--------|
| `{project_name}` | ✅ | `ExtractedData.project_name` | 사업명/공고명 | 없음 (필수) |
| `{item_name}` | ✅ | `ExtractedData.item_name` 또는 `ExtractedData.project_name` | 품목명/사업 내용 | `project_name`과 동일 |
| `{announcement_number}` | ✅ | 파생 필드 | 공고번호 (자동 생성) | `공고 제YYYY-MM-DD호` |
| `{announcement_date}` | ✅ | 파생 필드 | 공고일자 (자동 생성) | 오늘 날짜 (`YYYY년 MM월 DD일`) |

### 예산 정보

| 플레이스홀더 | 필수 | 데이터 소스 | 설명 | 포맷 |
|------------|------|------------|------|------|
| `{total_budget_vat}` | ✅ | `ExtractedData.total_budget_vat` 또는 `ExtractedData.estimated_amount` | 추정가격 (VAT 포함) | 숫자 (천단위 콤마) |

### 조달 정보

| 플레이스홀더 | 필수 | 데이터 소스 | 설명 | 기본값 |
|------------|------|------------|------|--------|
| `{procurement_type}` | ✅ | `ExtractedData.procurement_type` | 조달 유형 (물품/용역/공사) | 없음 (필수) |

### 자격 요건

| 플레이스홀더 | 필수 | 데이터 소스 | 설명 | 기본값 |
|------------|------|------------|------|--------|
| `{qualification_notes}` | ⚠️ | `ExtractedData.qualification_notes` | 자격 요건 및 특이사항 | 빈 문자열 (없으면 제거) |
| `{qualification_detail}` | ⚠️ | 파생 필드 (세부품명번호/업종코드 기반) | 세부 자격 요건 | `"별도 공고 참조"` |

### 계약 조건

| 플레이스홀더 | 필수 | 데이터 소스 | 설명 | 기본값 |
|------------|------|------------|------|--------|
| `{contract_period}` | ✅ | `ExtractedData.contract_period` | 계약 기간 | 없음 (필수) |
| `{delivery_deadline_days}` | ✅ | `ExtractedData.delivery_deadline_days` 또는 `contract_period` 파싱 | 납품 기한 (일) | `90` |

### 입찰 일정

| 플레이스홀더 | 필수 | 데이터 소스 | 설명 | 계산 규칙 |
|------------|------|------------|------|----------|
| `{bid_deadline}` | ✅ | 파생 필드 | 입찰서 제출 마감일 | 소액수의: 공고일 + 3일<br>적격심사: 공고일 + 7일 |
| `{opening_date}` | ✅ | 파생 필드 | 개찰 일시 | 입찰 마감일 + 1일 |
| `{award_date}` | ✅ | 파생 필드 | 낙찰자 결정 예정일 | 개찰일 + 7일 |

### 제출 서류

| 플레이스홀더 | 필수 | 데이터 소스 | 설명 | 기본값 |
|------------|------|------------|------|--------|
| `{required_documents}` | ⚠️ | 파생 필드 (세부품명번호/업종코드 기반) | 자격 증빙 서류 | `"입찰공고문 참조"` |

### 문의처

| 플레이스홀더 | 필수 | 데이터 소스 | 설명 | 기본값 |
|------------|------|------------|------|--------|
| `{contact_department}` | ⚠️ | 사용자 입력 또는 기본값 | 담당 부서 | `"발주기관명"` |
| `{contact_person}` | ⚠️ | 사용자 입력 또는 기본값 | 담당자명 | `"담당자명"` |
| `{contact_phone}` | ⚠️ | 사용자 입력 또는 기본값 | 전화번호 | `"02-1234-5678"` |
| `{contact_email}` | ⚠️ | 사용자 입력 또는 기본값 | 이메일 | `"contact@example.go.kr"` |
| `{organization}` | ⚠️ | 사용자 입력 또는 기본값 | 공고기관명 | `"발주기관명"` |

---

## 템플릿별 특수 플레이스홀더

### `negotiation.md` 전용

| 플레이스홀더 | 필수 | 데이터 소스 | 설명 | 기본값 |
|------------|------|------------|------|--------|
| `{question_deadline}` | ✅ | 파생 필드 | 질의 접수 마감일 | 공고일 + 5일 |
| `{answer_date}` | ✅ | 파생 필드 | 질의 응답 공고일 | 질의 마감일 + 2일 |
| `{proposal_deadline}` | ✅ | 파생 필드 | 제안서 제출 마감일 | 질의 응답일 + 7일 |
| `{evaluation_period}` | ✅ | 파생 필드 | 제안서 평가 기간 | 제안서 마감일 + 7일 |
| `{negotiation_date}` | ✅ | 파생 필드 | 협상 대상자 선정일 | 평가 완료 후 3일 |
| `{contract_date}` | ✅ | 파생 필드 | 계약 체결 예정일 | 협상 완료 후 7일 |
| `{project_scope}` | ⚠️ | `ExtractedData` 또는 기본값 | 사업 범위 | `"별도 과업지시서 참조"` |
| `{requirements}` | ⚠️ | `ExtractedData` 또는 기본값 | 요구 사항 | `"별도 과업지시서 참조"` |
| `{deliverables}` | ⚠️ | `ExtractedData` 또는 기본값 | 납품물 | `"별도 과업지시서 참조"` |
| `{technical_spec}` | ⚠️ | `ExtractedData` 또는 기본값 | 기술 스펙 | `"별도 과업지시서 참조"` |
| `{contact_address}` | ⚠️ | 사용자 입력 또는 기본값 | 주소 | `"서울특별시..."` |

---

## 데이터 소스 매핑

### ExtractedData → 템플릿 필드

```python
# 직접 매핑
project_name → {project_name}
item_name → {item_name}
procurement_type → {procurement_type}
contract_period → {contract_period}
qualification_notes → {qualification_notes}
total_budget_vat → {total_budget_vat}
estimated_amount → {total_budget_vat} (fallback)
delivery_deadline_days → {delivery_deadline_days}

# 파생 필드
contract_period → {delivery_deadline_days} (파싱)
```

### ClassificationResult → 템플릿 필드

```python
# Rule Engine 결정값 (가드 필수)
recommended_type → {contract_method} (직접 사용 안 함, 템플릿에 하드코딩)
applied_annex → {applied_annex} (템플릿에 하드코딩)
sme_restriction → {sme_restriction} (템플릿에 하드코딩)

# 날짜 계산 기준
recommended_type → {bid_deadline} 계산 기준
  - "소액수의": 공고일 + 3일
  - "적격심사": 공고일 + 7일
```

---

## Rule Engine 결정값 (가드 필수)

다음 값들은 **Rule Engine이 결정한 결과**이므로, LLM이 절대 변경하면 안 됩니다.

### 가드 대상 필드

| 필드 | 소스 | 설명 | 변경 금지 이유 |
|------|------|------|---------------|
| `contract_method` | `ClassificationResult.recommended_type` | 공고 방식 (소액수의/적격심사) | 법령 기반 결정 |
| `applied_annex` | `ClassificationResult.applied_annex` | 적용 별표 (별표1/별표2/별표3) | 법령 기반 결정 |
| `sme_restriction` | `ClassificationResult.sme_restriction` | 중소기업 제한 (소기업/중소기업/없음) | 법령 기반 결정 |

### 가드 규칙

1. **템플릿에 하드코딩**: 이 값들은 템플릿 파일 자체에 이미 적절한 문구로 하드코딩되어 있습니다.
   - 예: `qualification_review.md`에는 "적격심사에 의한 낙찰자 결정" 문구가 이미 있음
   - 예: `lowest_price.md`에는 "최저가 낙찰제" 문구가 이미 있음

2. **LLM 프롬프트 가드**: `create_generation_task()`에서 명시적으로 금지 사항으로 지정
   ```python
   ## ⚠️ 절대 변경 금지 사항 (Rule Engine 결정값)
   - 공고 방식: {contract_method} (변경 불가)
   - 적용 별표: {applied_annex} (변경 불가)
   - 중소기업 제한: {sme_restriction} (변경 불가)
   ```

3. **검증 단계**: `_validate_generation_result()`에서 불일치 감지

---

## 파생 필드 생성 규칙

### 날짜 필드

```python
# 기준: 오늘 날짜 (datetime.now())
announcement_date = today.strftime("%Y년 %m월 %d일")

# 공고 방식에 따른 입찰 마감일
if contract_method == "소액수의":
    bid_deadline = today + timedelta(days=3)  # 영업일 기준 (단순화: 3일)
else:  # 적격심사
    bid_deadline = today + timedelta(days=7)

opening_date = bid_deadline + timedelta(days=1)
award_date = opening_date + timedelta(days=7)
```

### 협상계약 전용 날짜 필드

```python
question_deadline = announcement_date + timedelta(days=5)
answer_date = question_deadline + timedelta(days=2)
proposal_deadline = answer_date + timedelta(days=7)
evaluation_period = f"{proposal_deadline} ~ {proposal_deadline + timedelta(days=7)}"
negotiation_date = proposal_deadline + timedelta(days=10)
contract_date = negotiation_date + timedelta(days=7)
```

### 공고번호 생성

```python
announcement_number = f"공고 제{today.year}-{today.month:02d}-{today.day:02d}호"
```

### 금액 포맷팅

```python
# 천단위 콤마 추가
if isinstance(amount, (int, float)):
    total_budget_vat = f"{amount:,}"
else:
    total_budget_vat = str(amount)
```

### 계약 기간 파싱

```python
# "6개월" → 180일
# "90일" → 90
def _parse_period_to_days(period_str: str) -> int:
    month_match = re.search(r'(\d+)\s*개월', str(period_str))
    if month_match:
        return int(month_match.group(1)) * 30
    
    day_match = re.search(r'(\d+)\s*일', str(period_str))
    if day_match:
        return int(day_match.group(1))
    
    return 90  # 기본값
```

---

## 필수/선택 여부 가이드

### 필수 필드 (✅)

다음 필드가 누락되면 템플릿이 불완전합니다:
- `{project_name}`
- `{item_name}`
- `{announcement_number}`
- `{announcement_date}`
- `{total_budget_vat}`
- `{procurement_type}`
- `{contract_period}`
- `{delivery_deadline_days}`
- `{bid_deadline}`
- `{opening_date}`
- `{award_date}`

### 선택 필드 (⚠️)

다음 필드가 없어도 템플릿은 완성되지만, 기본값이 사용됩니다:
- `{qualification_notes}`: 빈 문자열이면 해당 섹션 제거
- `{qualification_detail}`: 기본값 `"별도 공고 참조"`
- `{required_documents}`: 기본값 `"입찰공고문 참조"`
- 문의처 관련 필드: 기본값 사용

---

## 템플릿별 플레이스홀더 목록

### `qualification_review.md`

**사용 플레이스홀더 (17개)**:
- `{project_name}`, `{item_name}`, `{announcement_number}`, `{announcement_date}`
- `{total_budget_vat}`
- `{procurement_type}`, `{qualification_notes}`, `{qualification_detail}`
- `{contract_period}`, `{delivery_deadline_days}`
- `{bid_deadline}`, `{opening_date}`, `{award_date}`
- `{required_documents}`
- `{contact_department}`, `{contact_person}`, `{contact_phone}`, `{contact_email}`
- `{organization}`

### `lowest_price.md`

**사용 플레이스홀더 (17개)**:
- `qualification_review.md`와 동일

### `negotiation.md`

**사용 플레이스홀더 (28개)**:
- `qualification_review.md`의 모든 플레이스홀더
- 추가: `{question_deadline}`, `{answer_date}`, `{proposal_deadline}`, `{evaluation_period}`, `{negotiation_date}`, `{contract_date}`
- 추가: `{project_scope}`, `{requirements}`, `{deliverables}`, `{technical_spec}`
- 추가: `{contact_address}`

---

## 에러 처리 규칙

### 누락된 필수 필드

```python
# 필수 필드가 없으면 ValueError 발생
if not project_name:
    raise ValueError("필수 필드 'project_name'이 누락되었습니다.")
```

### 누락된 선택 필드

```python
# 선택 필드가 없으면 기본값 사용
qualification_detail = extracted_data.get("qualification_detail") or "별도 공고 참조"
```

### 잘못된 데이터 타입

```python
# 금액 필드는 숫자여야 함
if not isinstance(total_budget_vat, (int, float)):
    raise TypeError(f"total_budget_vat는 숫자여야 합니다. 현재 타입: {type(total_budget_vat)}")
```

---

## 업데이트 이력

- **2025-01-XX**: 초안 작성
  - 공통 플레이스홀더 정의
  - 템플릿별 특수 플레이스홀더 정의
  - Rule Engine 결정값 가드 규칙 추가
  - 파생 필드 생성 규칙 정의

---

## 참고

- 템플릿 파일 위치: `templates/`
- Field Mapper 구현: `app/tools/field_mapper.py`
- Rule Engine 구현: `app/tools/rule_engine.py`
- 템플릿 선택기: `app/tools/template_selector.py`

