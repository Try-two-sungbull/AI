"""
Agent API Endpoints

4개의 엔드포인트:
1. POST /api/v1/agent/upload - 문서 업로드만 받아서 자동 처리 (원스톱)
2. POST /api/v1/agent/run - Agent 재실행 (피드백 반영 시)
3. GET /api/v1/agent/state/{id} - 현재 상태 조회
4. POST /api/v1/agent/feedback - 사용자 피드백 반영

템플릿과 법령 참조는 시스템이 자동으로 처리합니다.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from typing import Optional, Dict, Any
import uuid
from datetime import datetime

from app.models.agent_state import AgentState
from app.models.schemas import UserFeedback
from app.services.crew_service import BiddingDocumentCrew
from app.utils.document_parser import parse_document

router = APIRouter()

# 간단한 in-memory 스토리지 (실제론 DB 사용)
agent_sessions: Dict[str, AgentState] = {}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...)
):
    """
    문서 업로드 + 즉시 Agent 실행 (통합)

    - 발주계획서 업로드 (PDF, DOCX, HWP)만 받음
    - 텍스트 추출
    - AgentState 생성
    - 즉시 Agent Loop 실행
    - 템플릿과 법령은 시스템이 자동으로 처리
    - 최종 결과 반환
    """
    # 세션 ID 생성
    session_id = str(uuid.uuid4())
    try:
        # 파일 읽기
        content = await file.read()

        # 문서 파싱 (텍스트 추출)
        raw_text = parse_document(content, file.filename)

        # AgentState 생성
        state = AgentState(
            session_id=session_id,
            step="extract",
            raw_text=raw_text
        )

        # 저장
        agent_sessions[session_id] = state

        # 즉시 Agent 실행
        crew_service = BiddingDocumentCrew(state)

        # 법령 참조는 시스템이 자동으로 선택
        law_references = get_default_law_references()

        # 전체 파이프라인 실행 - 완성된 문서 String 반환
        final_document = crew_service.run_full_pipeline(
            document_text=raw_text,
            law_references=law_references,
            max_iterations=10  # 최대 10회 반복
        )

        return {
            "session_id": session_id,
            "file_name": file.filename,
            "status": "completed",
            "document": final_document,  # 완성된 문서 String
            "state": {
                "step": state.step,
                "retry_count": state.retry_count,
                "created_at": state.created_at.isoformat(),
                "updated_at": state.updated_at.isoformat()
            }
        }

    except Exception as e:
        # 에러 발생 시에도 세션은 유지
        if session_id in agent_sessions:
            agent_sessions[session_id].add_error(str(e))
        raise HTTPException(status_code=400, detail=f"처리 실패: {str(e)}")


@router.post("/run")
async def run_agent(
    session_id: str,
    law_references: Optional[str] = None,
    user_prompt: Optional[str] = ""
):
    """
    Agent 재실행 (선택적)

    - 기존 세션을 다시 실행
    - 피드백 반영 후 재생성 시 사용
    - Observe → Decide → Act → Validate → Iterate
    """
    # 세션 조회
    if session_id not in agent_sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    state = agent_sessions[session_id]

    # 문서 텍스트 확인
    if not state.raw_text:
        raise HTTPException(status_code=400, detail="문서가 업로드되지 않았습니다")

    try:
        # Crew 생성
        crew_service = BiddingDocumentCrew(state)

        # 법령 참조 기본값
        if not law_references:
            law_references = get_default_law_references()

        # 전체 파이프라인 실행 - 완성된 문서 반환 (PDF 샘플 기반)
        final_document = crew_service.run_full_pipeline(
            document_text=state.raw_text,
            law_references=law_references,
            max_iterations=10
        )

        # 결과 반환
        return {
            "session_id": session_id,
            "status": "completed",
            "document": final_document,  # 완성된 문서 String
            "state": {
                "step": state.step,
                "retry_count": state.retry_count,
                "updated_at": state.updated_at.isoformat()
            }
        }

    except Exception as e:
        state.add_error(str(e))
        raise HTTPException(status_code=500, detail=f"Agent 실행 실패: {str(e)}")


@router.get("/state/{session_id}")
async def get_agent_state(session_id: str):
    """
    현재 상태 조회

    - AgentState 전체 정보 반환
    """
    if session_id not in agent_sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    state = agent_sessions[session_id]

    return {
        "session_id": session_id,
        "state": state.model_dump(),
        "can_retry": state.can_retry()
    }


@router.post("/feedback")
async def submit_feedback(feedback: UserFeedback):
    """
    사용자 피드백 반영

    - 사용자가 검토 후 피드백 제공
    - 피드백 반영하여 재실행 가능
    """
    if feedback.session_id not in agent_sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    state = agent_sessions[feedback.session_id]

    # 피드백 저장
    state.user_feedback = feedback.comments

    # 피드백 유형에 따른 처리
    if feedback.feedback_type == "approve":
        state.transition_to("complete")
        return {
            "session_id": feedback.session_id,
            "status": "approved",
            "message": "공고문이 승인되었습니다"
        }

    elif feedback.feedback_type == "reject":
        return {
            "session_id": feedback.session_id,
            "status": "rejected",
            "message": "공고문이 거부되었습니다"
        }

    elif feedback.feedback_type == "modify":
        if feedback.modified_content:
            state.generated_document = feedback.modified_content
            state.transition_to("complete")

        return {
            "session_id": feedback.session_id,
            "status": "modified",
            "message": "수정사항이 반영되었습니다"
        }

    else:
        raise HTTPException(status_code=400, detail="알 수 없는 피드백 유형입니다")


# 헬퍼 함수들

def get_default_law_references() -> str:
    """기본 법령 참조 반환"""
    return """
국가계약법 주요 조항:

제27조 (예정가격의 작성)
- 예정가격은 계약의 목적이 되는 물품, 용역 등의 가격을 조사하여 작성한다.
- 낙찰자는 예정가격 이하로 입찰한 자 중에서 결정한다.

제10조 (입찰 방법)
- 일반경쟁입찰을 원칙으로 한다.
- 적격심사는 일정 금액 이상의 공사 및 용역에 적용한다.

국가계약법 시행령:

제42조 (적격심사)
- 추정가격이 3억원 이상인 용역계약
- 추정가격이 100억원 이상인 공사계약
"""
