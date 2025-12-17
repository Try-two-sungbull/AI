# AI Bidding Document Agent

CrewAI 기반 입찰 공고문 자동 작성 에이전트

## 프로젝트 개요

본 프로젝트는 **에이전트 해커톤 제출용** FastAPI 기반 AI 입찰 공고문 자동 작성 시스템입니다.

### 핵심 철학

이 시스템은 Claude를 **법적 판단 주체가 아닌, 문서 이해·비교·재작성·제안 역할을 수행하는 서브 에이전트**로 활용합니다.

**Agent Loop**: Observe → Decide → Act → Validate → Iterate

## 기술 스택

| 구분 | 내용 |
|------|------|
| Backend | FastAPI (Python 3.10+) |
| AI Framework | CrewAI 0.28.0 |
| LLM | Claude 3.5 Sonnet |
| Agent State | Pydantic 기반 상태 모델 |
| Parsing | pypdf, python-docx |
| RAG | 국가법령정보센터 API (선택) |

## 설치 방법

### 방법 1: Docker 사용 (권장)

#### 1. 저장소 클론

```bash
git clone <repository-url>
cd AI
```

#### 2. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 API 키 설정:

```env
ANTHROPIC_API_KEY=your_actual_claude_api_key_here
SECRET_KEY=your_secret_key_here
```

#### 3. Docker Compose로 실행

```bash
docker-compose up --build
```

서버가 `http://localhost:8000` 에서 실행됩니다.

#### 4. 종료

```bash
docker-compose down
```

---

### 방법 2: 로컬 환경 설치

#### 1. 저장소 클론

```bash
git clone <repository-url>
cd AI
```

#### 2. 가상환경 생성 및 활성화

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

#### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

#### 4. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 다음 값을 설정:

```env
ANTHROPIC_API_KEY=your_actual_claude_api_key_here
SECRET_KEY=your_secret_key_here
```

### 5. 서버 실행

```bash
uvicorn app.main:app --reload
```

또는

```bash
python -m app.main
```

서버가 `http://localhost:8000` 에서 실행됩니다.

## API 문서

서버 실행 후 다음 URL에서 API 문서를 확인할 수 있습니다:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 주요 엔드포인트

### 1. POST /api/v1/agent/upload

문서 업로드 및 세션 생성

```bash
curl -X POST "http://localhost:8000/api/v1/agent/upload" \
  -F "file=@your_document.pdf"
```

### 2. POST /api/v1/agent/run

Agent Loop 실행

```bash
curl -X POST "http://localhost:8000/api/v1/agent/run?session_id=YOUR_SESSION_ID"
```

### 3. GET /api/v1/agent/state/{session_id}

현재 상태 조회

```bash
curl -X GET "http://localhost:8000/api/v1/agent/state/YOUR_SESSION_ID"
```

### 4. POST /api/v1/agent/feedback

사용자 피드백 제출

```bash
curl -X POST "http://localhost:8000/api/v1/agent/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "YOUR_SESSION_ID",
    "feedback_type": "approve",
    "comments": "승인합니다"
  }'
```

## CrewAI 에이전트 구조

### Agents

1. **Document Extractor Agent** - 발주계획서에서 핵심 정보 추출
2. **Classification Agent** - 공고 유형 분류 및 추천
3. **Generator Agent** - 공고문 초안 생성
4. **Validator Agent** - 법령 검증 및 수정 제안

### Agent Loop 흐름

```
STEP 1: 문서 업로드 → 텍스트 추출
         ↓
STEP 2: 핵심 정보 추출 (Extractor Agent)
         ↓
STEP 3: 공고 유형 분류 (Classifier Agent)
         ↓ (신뢰도 < 0.6 → 사용자 확인)
STEP 4: 공고문 초안 생성 (Generator Agent)
         ↓
STEP 5: 법령 검증 (Validator Agent)
         ↓
STEP 6: Agent Decision Policy
         - 이슈 없음 → 완료
         - 재시도 가능 → 수정 후 재검증
         - 재시도 한계 → 사람 개입 요청
```

## Agent Decision Policy

```python
IF issues.length == 0:
    state = complete
ELSE IF retry_count < 2:
    apply suggestions
    retry_count += 1
    state = revise
ELSE:
    escalate to human
```

## 프로젝트 구조

```
AI/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 메인 앱
│   ├── config.py            # 설정
│   ├── models/
│   │   ├── __init__.py
│   │   ├── agent_state.py   # Agent 상태 모델
│   │   └── schemas.py       # Pydantic 스키마
│   ├── services/
│   │   ├── __init__.py
│   │   ├── agents.py        # CrewAI Agents 정의
│   │   ├── tasks.py         # CrewAI Tasks 정의
│   │   └── crew_service.py  # Crew 오케스트레이션
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── agent.py     # API 엔드포인트
│   └── utils/
│       ├── __init__.py
│       └── document_parser.py  # 문서 파싱
├── templates/
│   └── sample_template.json
├── requirements.txt
├── .env.example
├── .gitignore
├── CLAUDE.md               # 개발 명세서
└── README.md
```

## 해커톤 어필 포인트

1. **법적 책임 분리**: Claude를 판단 주체가 아닌 협력 에이전트로 제한
2. **Agent State 기반 반복 실행**: Pydantic 기반 상태 관리
3. **CrewAI 프레임워크 활용**: 멀티 에이전트 협업 구조
4. **공공 도메인 특화**: 입찰 공고문 자동화에 최적화
5. **투명한 의사결정**: 신뢰도 점수 및 재시도 정책 명시

## 개발 가이드

### 새로운 Agent 추가

`app/services/agents.py`에 새 함수 추가:

```python
def create_my_new_agent() -> Agent:
    return Agent(
        role="역할",
        goal="목표",
        backstory="배경",
        llm=get_llm(),
        verbose=True
    )
```

### 새로운 Task 추가

`app/services/tasks.py`에 새 함수 추가:

```python
def create_my_new_task(agent, input_data) -> Task:
    return Task(
        description="작업 설명",
        agent=agent,
        expected_output="예상 출력"
    )
```

## 라이선스

MIT License

## 기여

이슈 및 PR 환영합니다!

## 문의

프로젝트 관련 문의: [이메일 또는 이슈 페이지]
