# 📘 AI 입찰 공고문 자동 작성 API 명세서

## 기본 정보

- **Base URL**: `http://localhost:8000`
- **API Version**: `v1`
- **API Prefix**: `/api/v1`

---

## 📊 전체 워크플로우

```
1. 문서 업로드 (POST /api/v1/agent/upload)
         ↓
   session_id 받기
         ↓
2. Agent 실행 (POST /api/v1/agent/run)
         ↓
   자동으로 다음 단계 진행:
   - 정보 추출 (Extractor)
   - 공고 유형 분류 (Classifier)
   - 공고문 생성 (Generator)
   - 법령 검증 (Validator)
         ↓
3. 결과 확인 (GET /api/v1/agent/state/{session_id})
         ↓
4. 피드백 제출 (POST /api/v1/agent/feedback)
```

---

## 🔌 API 엔드포인트

### 1. 문서 업로드

**업로드한 발주계획서에서 텍스트를 추출하고 세션을 생성합니다.**

#### Request

```http
POST /api/v1/agent/upload
Content-Type: multipart/form-data
```

**Parameters:**
- `file` (required, file): 발주계획서 파일 (PDF, DOCX, HWP)
- `template_id` (optional, string): 사용할 템플릿 ID

**Example (curl):**
```bash
curl -X POST http://localhost:8000/api/v1/agent/upload \
  -F "file=@발주계획서.pdf" \
  -F "template_id=template_001"
```

**Example (Python):**
```python
import requests

url = "http://localhost:8000/api/v1/agent/upload"
files = {"file": open("발주계획서.pdf", "rb")}
response = requests.post(url, files=files)
print(response.json())
```

#### Response

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "uploaded",
  "file_name": "발주계획서.pdf",
  "text_length": 1234,
  "state": "extract",
  "created_at": "2025-01-16T10:30:00.000000"
}
```

**Response Fields:**
- `session_id`: 세션 ID (이후 모든 API 호출에 사용)
- `status`: 업로드 상태
- `file_name`: 업로드된 파일 이름
- `text_length`: 추출된 텍스트 길이
- `state`: 현재 Agent 상태 (`extract`)
- `created_at`: 세션 생성 시각

---

### 2. Agent 실행 (전체 파이프라인)

**업로드한 문서를 분석하여 공고문을 자동 생성합니다.**

#### Request

```http
POST /api/v1/agent/run
Content-Type: application/x-www-form-urlencoded
```

**Parameters:**
- `session_id` (required, string): 업로드 시 받은 세션 ID
- `template` (optional, string): 사용할 템플릿 (기본값: 내장 템플릿)
- `law_references` (optional, string): 참조할 법령 (기본값: 국가계약법)
- `user_prompt` (optional, string): 추가 요청사항 (예: "납품 기한을 강조해주세요")

**Example (curl):**
```bash
curl -X POST "http://localhost:8000/api/v1/agent/run" \
  -d "session_id=550e8400-e29b-41d4-a716-446655440000" \
  -d "user_prompt=납품 기한을 강조해주세요"
```

**Example (Python):**
```python
import requests

url = "http://localhost:8000/api/v1/agent/run"
data = {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "user_prompt": "납품 기한을 강조해주세요"
}
response = requests.post(url, data=data)
print(response.json())
```

#### Response (완료 시)

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "result": {
    "status": "complete",
    "extracted_data": {
      "project_name": "광화학유해대기물질측정망 컬럼 구매",
      "total_budget_vat": 157580500,
      "delivery_deadline_days": 60,
      "procurement_type": "물품",
      "procurement_method_raw": "일반경쟁입찰"
    },
    "classification": {
      "recommended_type": "최저가낙찰",
      "confidence": 0.85,
      "reason": "물품 157,580,500원으로 최저가 낙찰 적합 (단순 물품)",
      "alternative_types": []
    },
    "final_document": "# 입찰공고\n\n## 공고 개요\n...",
    "validation": {
      "is_valid": true,
      "issues": [],
      "checked_laws": ["국가계약법", "국가계약법 시행령"],
      "timestamp": "2025-01-16T10:35:00.000000"
    }
  },
  "state": {
    "step": "complete",
    "retry_count": 0,
    "updated_at": "2025-01-16T10:35:00.000000"
  }
}
```

#### Response (사용자 확인 필요 시)

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "result": {
    "status": "needs_user_confirmation",
    "message": "분류 신뢰도가 낮습니다. 사용자 확인이 필요합니다.",
    "extracted_data": { ... },
    "classification": {
      "recommended_type": "적격심사",
      "confidence": 0.55,
      "reason": "금액이 적격심사 기준에 근접",
      "alternative_types": ["최저가낙찰"]
    }
  },
  "state": {
    "step": "classify",
    "retry_count": 0,
    "updated_at": "2025-01-16T10:35:00.000000"
  }
}
```

#### Response (검증 이슈 발견 시)

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "result": {
    "status": "revised_with_remaining_issues",
    "extracted_data": { ... },
    "classification": { ... },
    "final_document": "# 입찰공고 (수정본)\n...",
    "validation": {
      "is_valid": false,
      "issues": [
        {
          "law": "국가계약법",
          "section": "제27조",
          "issue_type": "표현 수정",
          "current_text": "예정가격 미만",
          "suggestion": "표현을 '예정가격 이하'로 수정 권장",
          "severity": "medium"
        }
      ],
      "checked_laws": ["국가계약법"],
      "timestamp": "2025-01-16T10:35:00.000000"
    },
    "revision_count": 1
  }
}
```

**Result Status 종류:**
- `complete`: 검증 통과, 공고문 완성
- `needs_user_confirmation`: 분류 신뢰도 낮음, 사용자 확인 필요
- `needs_human_intervention`: 재시도 한계 초과, 사람 개입 필요
- `revised_with_remaining_issues`: 수정 후에도 이슈 남음

---

### 3. 상태 조회

**현재 Agent 세션의 상태를 조회합니다.**

#### Request

```http
GET /api/v1/agent/state/{session_id}
```

**Example (curl):**
```bash
curl http://localhost:8000/api/v1/agent/state/550e8400-e29b-41d4-a716-446655440000
```

**Example (Python):**
```python
import requests

session_id = "550e8400-e29b-41d4-a716-446655440000"
url = f"http://localhost:8000/api/v1/agent/state/{session_id}"
response = requests.get(url)
print(response.json())
```

#### Response

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "state": {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "step": "complete",
    "retry_count": 0,
    "max_retry": 2,
    "last_error": null,
    "selected_template_id": null,
    "raw_text": "발주계획서 내용...",
    "extracted_data": { ... },
    "classification": { ... },
    "generated_document": "# 입찰공고\n...",
    "validation_issues": [],
    "user_feedback": null,
    "created_at": "2025-01-16T10:30:00.000000",
    "updated_at": "2025-01-16T10:35:00.000000"
  },
  "can_retry": true
}
```

**State Steps:**
- `upload`: 문서 업로드됨
- `extract`: 정보 추출 중
- `classify`: 공고 유형 분류 중
- `generate`: 공고문 생성 중
- `validate`: 법령 검증 중
- `revise`: 수정 중
- `complete`: 완료

---

### 4. 사용자 피드백

**생성된 공고문에 대한 사용자 피드백을 제출합니다.**

#### Request

```http
POST /api/v1/agent/feedback
Content-Type: application/json
```

**Body:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "feedback_type": "approve",
  "comments": "공고문이 잘 작성되었습니다",
  "modified_content": null
}
```

**Fields:**
- `session_id` (required): 세션 ID
- `feedback_type` (required): 피드백 유형
  - `approve`: 승인
  - `reject`: 거부
  - `modify`: 수정
- `comments` (optional): 피드백 내용
- `modified_content` (optional): 수정된 공고문 (feedback_type이 `modify`인 경우)

**Example (curl - 승인):**
```bash
curl -X POST http://localhost:8000/api/v1/agent/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "feedback_type": "approve",
    "comments": "공고문이 잘 작성되었습니다"
  }'
```

**Example (curl - 수정):**
```bash
curl -X POST http://localhost:8000/api/v1/agent/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "feedback_type": "modify",
    "comments": "납품 기한을 90일로 수정",
    "modified_content": "# 입찰공고 (수정)\n..."
  }'
```

**Example (Python):**
```python
import requests

url = "http://localhost:8000/api/v1/agent/feedback"
data = {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "feedback_type": "approve",
    "comments": "공고문이 잘 작성되었습니다"
}
response = requests.post(url, json=data)
print(response.json())
```

#### Response (승인)

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "approved",
  "message": "공고문이 승인되었습니다"
}
```

#### Response (거부)

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "rejected",
  "message": "공고문이 거부되었습니다"
}
```

#### Response (수정)

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "modified",
  "message": "수정사항이 반영되었습니다"
}
```

---

## 🔍 헬스 체크 엔드포인트

### Root

```http
GET /
```

**Response:**
```json
{
  "message": "AI Bidding Document Agent API",
  "version": "1.0.0",
  "docs": "/docs",
  "health": "/health"
}
```

### Health Check

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "app_name": "AI Bidding Document Agent",
  "version": "1.0.0"
}
```

---

## 📝 실제 사용 예제

### 전체 플로우 예제 (Python)

```python
import requests
import time

BASE_URL = "http://localhost:8000/api/v1/agent"

# 1. 문서 업로드
print("1. 문서 업로드...")
upload_response = requests.post(
    f"{BASE_URL}/upload",
    files={"file": open("발주계획서.pdf", "rb")}
)
session_id = upload_response.json()["session_id"]
print(f"✓ 세션 ID: {session_id}")

# 2. Agent 실행
print("\n2. Agent 실행...")
run_response = requests.post(
    f"{BASE_URL}/run",
    data={
        "session_id": session_id,
        "user_prompt": "납품 기한과 품질 기준을 강조해주세요"
    }
)
result = run_response.json()
print(f"✓ 상태: {result['result']['status']}")

# 3. 결과 확인
if result['result']['status'] == 'complete':
    print("\n3. 공고문 생성 완료!")
    print(f"- 공고 유형: {result['result']['classification']['recommended_type']}")
    print(f"- 신뢰도: {result['result']['classification']['confidence']}")
    print(f"\n생성된 공고문:\n{result['result']['final_document'][:500]}...")

    # 4. 피드백 제출
    print("\n4. 피드백 제출...")
    feedback_response = requests.post(
        f"{BASE_URL}/feedback",
        json={
            "session_id": session_id,
            "feedback_type": "approve",
            "comments": "완벽합니다!"
        }
    )
    print(f"✓ {feedback_response.json()['message']}")

elif result['result']['status'] == 'needs_user_confirmation':
    print("\n⚠️ 사용자 확인 필요!")
    print(f"- 추천 유형: {result['result']['classification']['recommended_type']}")
    print(f"- 신뢰도: {result['result']['classification']['confidence']}")
    print(f"- 대안: {result['result']['classification']['alternative_types']}")

else:
    print(f"\n⚠️ 상태: {result['result']['status']}")
    print(f"메시지: {result['result'].get('message', '')}")
```

### 전체 플로우 예제 (Bash)

```bash
#!/bin/bash

BASE_URL="http://localhost:8000/api/v1/agent"

# 1. 문서 업로드
echo "1. 문서 업로드..."
UPLOAD_RESPONSE=$(curl -s -X POST "$BASE_URL/upload" \
  -F "file=@발주계획서.pdf")

SESSION_ID=$(echo $UPLOAD_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['session_id'])")
echo "✓ 세션 ID: $SESSION_ID"

# 2. Agent 실행
echo -e "\n2. Agent 실행..."
RUN_RESPONSE=$(curl -s -X POST "$BASE_URL/run" \
  -d "session_id=$SESSION_ID" \
  -d "user_prompt=납품 기한과 품질 기준을 강조해주세요")

echo $RUN_RESPONSE | python3 -m json.tool

# 3. 상태 조회
echo -e "\n3. 상태 조회..."
curl -s "$BASE_URL/state/$SESSION_ID" | python3 -m json.tool

# 4. 피드백 제출
echo -e "\n4. 피드백 제출..."
curl -s -X POST "$BASE_URL/feedback" \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"feedback_type\": \"approve\",
    \"comments\": \"완벽합니다!\"
  }" | python3 -m json.tool
```

---

## ⚠️ 에러 코드

| Status Code | 설명 |
|------------|------|
| 200 | 성공 |
| 400 | 잘못된 요청 (파일 형식 오류, 파라미터 오류 등) |
| 404 | 세션을 찾을 수 없음 |
| 500 | 서버 내부 오류 (Agent 실행 실패 등) |

**Error Response 예시:**
```json
{
  "detail": "세션을 찾을 수 없습니다"
}
```

---

## 🎯 주요 특징

1. **비동기 처리**: 모든 엔드포인트는 FastAPI의 async를 사용하여 빠른 응답 제공
2. **세션 기반**: session_id로 상태 관리, 여러 작업 동시 처리 가능
3. **에러 핸들링**: 명확한 에러 메시지와 HTTP 상태 코드 제공
4. **검증**: Pydantic 모델로 요청/응답 자동 검증

---

## 📚 추가 문서

- **Swagger UI**: http://localhost:8000/docs (대화형 API 문서)
- **ReDoc**: http://localhost:8000/redoc (읽기 편한 API 문서)
- **CLAUDE.md**: 프로젝트 설계 철학 및 Agent 구조

---

**문의**: 개발팀
**버전**: v1.0.0
**마지막 업데이트**: 2025-01-16
