# 한국환경공단 입찰공고문 자동생성 서비스

## 1. 프로젝트 소개

`한국환경공단 입찰공고문 자동생성 서비스`는 입찰 관련 문서를 다루는 FastAPI 기반 프로젝트입니다.

현재 저장소에는 문서 추출, 공고 유형 분류, 템플릿 검증, 문서 생성, 문서 변환 관련 API와 서비스 코드가 포함되어 있습니다.

## 2. 기획 배경

입찰 공고문 작성 과정에는 반복적인 문서 확인과 템플릿 수정 작업이 포함됩니다.  
이 프로젝트는 그 과정 중 일부를 AI와 규칙 기반 로직으로 처리하는 구조로 작성되어 있습니다.

코드상으로도 발주 문서 파싱, 추출 결과 구조화, 분류, 템플릿 비교, 초안 생성 흐름이 각각 분리되어 있습니다.

## 3. 해결하고자 한 문제

- PDF, DOCX, HWP 문서에서 필요한 정보를 추출하는 반복 작업
- 추출된 정보를 바탕으로 공고 유형을 분류하는 작업
- 최신 공고문과 기존 템플릿의 차이를 비교하는 작업
- 템플릿과 추출 데이터를 결합해 초안을 만드는 작업
- 생성 결과를 PDF, DOCX, HWP로 변환하는 후처리 작업

## 4. 서비스 목표

- 입력 문서에서 핵심 정보를 추출한다.
- 추출 결과를 기반으로 공고 유형을 분류한다.
- 템플릿 검증과 문서 생성 흐름을 구성한다.
- 생성 결과를 다른 문서 형식으로 변환하는 경로를 둔다.

## 5. 주요 기능

- `POST /api/v1/agent/extract`
  - 업로드 파일을 받아 추출 단계를 실행합니다.
- `POST /api/v1/agent/classify`
  - 추출과 분류 단계를 실행합니다.
- `POST /api/v1/agent/validate-template`
  - 템플릿 검증 흐름을 실행합니다.
- `POST /api/v1/agent/upload`
  - 추출 데이터와 분류 결과를 받아 문서를 생성합니다.
- `POST /api/v1/agent/generate`
  - 추출 데이터를 받아 문서를 생성합니다.
- `POST /api/v1/agent/convert-html`
  - HTML 변환을 수행합니다.
- 템플릿 관련 엔드포인트
  - `/api/v1/agent/templates/`, `/latest`, `/retrieve`, `/{template_id}` 라우트가 있습니다.

## 6. 서비스 흐름

현재 코드 기준 핵심 흐름은 아래와 같습니다.

1. 문서를 업로드해 추출 단계를 실행합니다.
2. 추출 결과를 바탕으로 분류 단계를 실행합니다.
3. 템플릿 검증 흐름을 별도로 실행할 수 있습니다.
4. 분류 결과와 템플릿 ID를 사용해 문서를 생성합니다.
5. HTML 또는 생성 결과를 다른 형식으로 변환하는 경로가 있습니다.

세션 상태 조회, 재실행, 피드백 반영용 엔드포인트도 별도로 구현되어 있습니다.

## 7. 기술 스택

| 구분 | 사용 기술 |
|------|-----------|
| Backend | FastAPI, Uvicorn |
| Language | Python 3.10 |
| AI Orchestration | CrewAI, crewai-tools |
| LLM 연동 | OpenAI, Anthropic, langchain-openai, langchain-anthropic |
| 데이터 모델 | Pydantic, pydantic-settings |
| DB | SQLAlchemy, PostgreSQL |
| 문서 파싱 | pypdf, pdfplumber, python-docx, olefile, PyMuPDF |
| 문서 변환 | WeasyPrint, htmldocx, LibreOffice |
| 배포/실행 | Docker, Docker Compose |

## 8. AI 활용 방식

코드 기준 AI 활용 방식은 다음과 같습니다.

- `Extractor Agent`
  - 문서에서 핵심 정보를 추출합니다.
- `Classifier Agent`
  - 추출 결과를 바탕으로 공고 유형 분류를 수행합니다.
- `Generator Agent`
  - 템플릿 기반 문서 생성을 담당합니다.
- `Validator Agent`
  - 검토 및 보조 판단 역할로 사용됩니다.

`crew_service.py`에서는 추출, 분류, 생성, 검증 단계를 순차적으로 실행하는 구조를 사용합니다.  
추출 단계에서는 Claude 기반 추출을 먼저 수행하고, 누락 필드가 있으면 OpenAI 기반 추출을 추가로 수행한 뒤 결과를 통합하도록 구현되어 있습니다.
