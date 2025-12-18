"""
Agent API Endpoints

4개의 엔드포인트:
1. POST /api/v1/agent/upload - 문서 업로드만 받아서 자동 처리 (원스톱)
2. POST /api/v1/agent/run - Agent 재실행 (피드백 반영 시)
3. GET /api/v1/agent/state/{id} - 현재 상태 조회
4. POST /api/v1/agent/feedback - 사용자 피드백 반영

템플릿과 법령 참조는 시스템이 자동으로 처리합니다.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query, Response, Request, Body
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, PlainTextResponse
import json
import io
from typing import Optional, Dict, Any
import uuid
from datetime import datetime
import tempfile
import os
from pathlib import Path

from app.infra.db.database import get_db, engine, Base
from app.models.agent_state import AgentState
from app.models.schemas import UserFeedback, SaveTemplateRequest, ExtractedData, ClassificationResult, UploadDocumentRequest
from app.services.crew_service import BiddingDocumentCrew
from app.services.nara_bid_service import get_latest_bid_notice
from app.services.template_validation_service import validate_template_workflow
from app.utils.document_parser import parse_document
from app.utils.document_converter import convert_document, convert_html_document
from app.config import get_settings

from sqlalchemy.orm import Session
from app.infra.db.models import NoticeTemplate

# 애플리케이션 시작 시 테이블이 없다면 생성
Base.metadata.create_all(bind=engine)

settings = get_settings()

router = APIRouter()

# 간단한 in-memory 스토리지 (실제론 DB 사용)
agent_sessions: Dict[str, AgentState] = {}


@router.post("/upload")
async def upload_document(
    request: UploadDocumentRequest = Body(..., description="추출된 데이터와 분류 결과"),
    template_id: int = Query(..., description="템플릿 ID (필수, validate-template에서 생성된 템플릿)"),
    format: Optional[str] = Query("markdown", description="출력 형식: markdown, pdf, docx")
):
    """
    추출된 데이터와 분류 결과로 문서 생성

    - classify에서 받은 extracted_data와 classification을 사용
    - 지정된 템플릿 ID로 문서 생성
    - 최종 결과 반환 (마크다운, PDF, DOCX)

    Args:
        request: UploadDocumentRequest (extracted_data + classification 포함)
        template_id: 템플릿 ID (필수, validate-template에서 생성된 템플릿)
        format: 출력 형식 (markdown, pdf, docx)
    """
    # classify에서 받은 session_id 사용 (또는 새로 생성)
    session_id = request.session_id if request.session_id else str(uuid.uuid4())
    try:
        # 요청에서 데이터 추출
        extracted_data = request.extracted_data
        classification = request.classification
        
        # AgentState 생성 (추출/분류는 이미 완료된 것으로 간주)
        state = AgentState(
            session_id=session_id,
            step="generate",
            raw_text=""  # 파일이 없으므로 빈 텍스트
        )
        
        # 분류 결과를 state에 저장
        state.classification = classification
        state.extracted_data = extracted_data.model_dump() if hasattr(extracted_data, 'model_dump') else extracted_data.dict()
        
        # 세션 저장
        agent_sessions[session_id] = state
        
        # 추출된 데이터를 딕셔너리로 변환
        extracted_dict = extracted_data.model_dump() if hasattr(extracted_data, 'model_dump') else extracted_data.dict()
        
        # Agent 실행
        crew_service = BiddingDocumentCrew(state)
        
        # 법령 참조는 시스템이 자동으로 선택
        law_references = get_default_law_references()
        
        # 템플릿 정보 전달
        template_info = {"template_id": template_id}
        print(f"📋 템플릿 ID 지정: {template_id}")
        
        # 문서 생성만 실행 (추출/분류는 이미 완료)
        announcement_type = classification.get("recommended_type", "적격심사")
        
        # 소액수의는 "최저가낙찰" 템플릿 사용
        if announcement_type == "소액수의":
            announcement_type = "최저가낙찰"
        
        final_document = crew_service.run_generation(
            extracted_dict,
            announcement_type=announcement_type,
            law_references=law_references,
            template_info=template_info
        )

        # 문서 길이 확인 (JSON 직렬화 문제 진단용)
        document_length = len(final_document) if final_document else 0
        print(f"📄 생성된 문서 길이: {document_length}자")
        
        # 템플릿 필수 섹션 확인
        required_sections = [
            "위와 같이 공고합니다",
            "기타사항",
            "입찰무효",
            "입찰보증금",
            "청렴계약이행",
            "예정가격",
            "공동계약",
            "입찰참가자격"
        ]
        missing_sections = [s for s in required_sections if s not in final_document]
        if missing_sections:
            print(f"⚠️ 경고: 생성된 문서에서 다음 섹션이 누락되었습니다: {missing_sections}")

        # 문서 길이 확인
        document_length = len(final_document) if final_document else 0
        print(f"📄 생성된 문서 길이: {document_length}자")
        
        # 형식에 따라 반환
        if format.lower() == "markdown":
            response_data = {
                "session_id": session_id,
                "file_name": request.file_name,
                "status": "completed",
                "format": "markdown",
                "document": final_document,
                "state": {
                    "step": state.step,
                    "retry_count": state.retry_count,
                    "created_at": state.created_at.isoformat(),
                    "updated_at": state.updated_at.isoformat()
                }
            }
            
            try:
                return JSONResponse(
                    content=response_data,
                    media_type="application/json"
                )
            except Exception as json_error:
                print(f"❌ JSON 직렬화 오류: {json_error}")
                raise HTTPException(
                    status_code=500,
                    detail=f"JSON 직렬화 실패: {str(json_error)}. 문서 길이: {document_length}자"
                )
        else:
            # PDF 또는 DOCX로 변환
            try:
                file_bytes = convert_document(final_document, format.lower())
                extension = "pdf" if format.lower() == "pdf" else "docx"
                filename = f"공고문_{session_id[:8]}.{extension}"
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}") as tmp_file:
                    tmp_file.write(file_bytes)
                    tmp_path = tmp_file.name
                
                return FileResponse(
                    tmp_path,
                    media_type=f"application/{extension}",
                    filename=filename,
                    headers={
                        "Content-Disposition": f"attachment; filename={filename}"
                    }
                )
            except Exception as e:
                return {
                    "session_id": session_id,
                    "status": "completed",
                    "format": "markdown",
                    "document": final_document,
                    "error": f"파일 변환 실패: {str(e)}. 마크다운 형식으로 반환합니다.",
                    "classification": classification
                }

    except Exception as e:
        # 에러 발생 시에도 세션은 유지
        if session_id in agent_sessions:
            agent_sessions[session_id].add_error(str(e))
        raise HTTPException(status_code=400, detail=f"처리 실패: {str(e)}")


@router.post("/generate")
async def generate_from_extracted(
    extracted_data: ExtractedData = Body(..., description="추출된 데이터 (classify에서 받은 데이터)"),
    template_id: int = Query(..., description="템플릿 ID (validate-template에서 생성된 템플릿)"),
    format: Optional[str] = Query("markdown", description="출력 형식: markdown, pdf, docx")
):
    """
    추출된 데이터로 문서 생성 (파일 업로드 없이)
    
    - classify에서 추출된 데이터를 재사용
    - 지정된 템플릿 ID로 문서 생성
    - 최종 결과 반환 (마크다운, PDF, DOCX)
    
    Args:
        extracted_data: 추출된 데이터 (ExtractedData 형식)
        template_id: 템플릿 ID (필수, validate-template에서 생성된 템플릿)
        format: 출력 형식 (markdown, pdf, docx)
    """
    session_id = str(uuid.uuid4())
    try:
        # AgentState 생성 (추출 단계는 이미 완료된 것으로 간주)
        state = AgentState(
            session_id=session_id,
            step="generate",
            raw_text=""  # 파일이 없으므로 빈 텍스트
        )
        
        # 추출된 데이터를 딕셔너리로 변환
        extracted_dict = extracted_data.model_dump() if hasattr(extracted_data, 'model_dump') else extracted_data.dict()
        
        # 분류 실행 (추출된 데이터 기반)
        crew_service = BiddingDocumentCrew(state)
        classification = crew_service.run_classification(extracted_dict)
        
        # 법령 참조는 시스템이 자동으로 선택
        law_references = get_default_law_references()
        
        # 템플릿 정보 전달
        template_info = {"template_id": template_id}
        print(f"📋 템플릿 ID 지정: {template_id}")
        
        # 문서 생성만 실행 (추출/분류는 이미 완료)
        announcement_type = classification.get("recommended_type", "적격심사")
        
        # 소액수의는 "최저가낙찰" 템플릿 사용
        if announcement_type == "소액수의":
            announcement_type = "최저가낙찰"
        
        final_document = crew_service.run_generation(
            extracted_dict,
            announcement_type=announcement_type,
            law_references=law_references,
            template_info=template_info
        )
        
        # 형식에 따라 반환
        if format.lower() == "markdown":
            return {
                "session_id": session_id,
                "status": "completed",
                "format": "markdown",
                "document": final_document,
                "classification": classification
            }
        else:
            # PDF 또는 DOCX로 변환
            try:
                file_bytes = convert_document(final_document, format.lower())
                extension = "pdf" if format.lower() == "pdf" else "docx"
                filename = f"공고문_{session_id[:8]}.{extension}"
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}") as tmp_file:
                    tmp_file.write(file_bytes)
                    tmp_path = tmp_file.name
                
                return FileResponse(
                    tmp_path,
                    media_type=f"application/{extension}",
                    filename=filename,
                    headers={
                        "Content-Disposition": f"attachment; filename={filename}"
                    }
                )
            except Exception as e:
                return {
                    "session_id": session_id,
                    "status": "completed",
                    "format": "markdown",
                    "document": final_document,
                    "error": f"파일 변환 실패: {str(e)}. 마크다운 형식으로 반환합니다.",
                    "classification": classification
                }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문서 생성 실패: {str(e)}")


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

        # 전체 파이프라인 실행 - 완성된 문서 반환
        final_document = crew_service.run_full_pipeline(
            document_text=state.raw_text,
            law_references=law_references,
            max_iterations=10
        )

        # 문서 길이 확인 (JSON 직렬화 문제 진단용)
        document_length = len(final_document) if final_document else 0
        print(f"📄 생성된 문서 길이: {document_length}자")

        # 결과 반환 (JSONResponse 사용)
        response_data = {
            "session_id": session_id,
            "status": "completed",
            "document": final_document,  # 완성된 문서 String
            "state": {
                "step": state.step,
                "retry_count": state.retry_count,
                "updated_at": state.updated_at.isoformat()
            }
        }
        
        try:
            # JSON 직렬화 테스트
            json_str = json.dumps(response_data, ensure_ascii=False)
            json_length = len(json_str)
            print(f"📦 JSON 직렬화 후 길이: {json_length}자 (원본 문서: {document_length}자)")
            return JSONResponse(content=response_data, media_type="application/json")
        except Exception as json_error:
            print(f"❌ JSON 직렬화 오류: {json_error}")
            raise HTTPException(
                status_code=500,
                detail=f"JSON 직렬화 실패: {str(json_error)}. 문서 길이: {document_length}자"
            )

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


@router.get("/export/{session_id}")
async def export_document(
    session_id: str,
    format: str = Query("pdf", description="출력 형식: pdf, docx")
):
    """
    생성된 공고문을 파일로 내보내기

    - 세션의 생성된 문서를 PDF 또는 DOCX로 변환하여 다운로드

    Args:
        session_id: 세션 ID
        format: 출력 형식 (pdf, docx)
    """
    if session_id not in agent_sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    state = agent_sessions[session_id]

    if not state.generated_document:
        raise HTTPException(status_code=400, detail="생성된 문서가 없습니다")

    try:
        # 문서 변환
        file_bytes = convert_document(state.generated_document, format.lower())
        
        # 파일 확장자 결정
        extension = format.lower()
        filename = f"공고문_{session_id[:8]}.{extension}"
        
        # 임시 파일 생성
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}") as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name
        
        # 파일 응답 반환
        return FileResponse(
            tmp_path,
            media_type=f"application/{extension}",
            filename=filename,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 변환 실패: {str(e)}")


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

@router.post("/templates/")
async def save_template(
    template_type: str = Query(..., description="템플릿 유형 (예: 적격심사, 소액수의)"),
    markdown_text: str = Body(..., media_type="text/plain", description="마크다운 템플릿 내용"),
    db: Session = Depends(get_db),
):
    """
    템플릿을 DB에 저장하고 저장된 템플릿 내용을 text/plain으로 반환
    
    요청: Content-Type: text/plain (마크다운 텍스트 직접 전송)
    응답: text/plain (저장된 마크다운 템플릿 내용)
    
    Args:
        template_type: 템플릿 유형 (쿼리 파라미터)
        markdown_text: 마크다운 템플릿 내용 (text/plain body)
        db: 데이터베이스 세션
    
    Returns:
        PlainTextResponse: 저장된 마크다운 템플릿 내용
    """
    try:
        if not markdown_text.strip():
            raise HTTPException(status_code=400, detail="마크다운 텍스트가 비어있습니다.")
        
        new_template = NoticeTemplate(
            template_type=template_type,
            content=markdown_text,
            summary="에이전트에 의해 자동 생성됨",
        )
        db.add(new_template)
        db.commit()
        db.refresh(new_template)
        
        # 저장된 템플릿 내용을 text/plain으로 반환
        return PlainTextResponse(
            content=markdown_text,
            media_type="text/plain; charset=utf-8"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"템플릿 저장 실패: {str(e)}")


@router.get("/templates/latest")
async def get_latest_template(
    template_type: str,
    db: Session = Depends(get_db),
):
    """
    템플릿 유형(예: '적격심사')을 받아 최신 버전 템플릿을 반환하는 API

    - 같은 template_type 중에서 created_at 기준으로 가장 최근 레코드 1건 조회
    """
    latest = (
        db.query(NoticeTemplate)
        .filter(NoticeTemplate.template_type == template_type)
        .order_by(NoticeTemplate.created_at.desc())
        .first()
    )

    if not latest:
        raise HTTPException(
            status_code=404,
            detail=f"해당 유형의 템플릿이 없습니다: {template_type}",
        )

    return {
        "id": latest.id,
        "template_type": latest.template_type,
        "version": latest.version,
        "summary": latest.summary,
        "created_at": latest.created_at.isoformat() if latest.created_at else None,
        "content": latest.content,
    }


@router.get("/templates/retrieve")
async def retrieve_template(
    template_type: str = Query(..., description="템플릿 유형 (소액수의, 적격심사)"),
    limit: int = Query(10, ge=1, le=50, description="조회할 템플릿 개수 (기본 10개, 최대 50개)"),
    db: Session = Depends(get_db),
):
    """
    템플릿 목록 조회 API (Template Retrieval - List)

    - template_type 파라미터로 저장된 템플릿 최신 N개를 조회합니다.
    - DB의 template_type 컬럼과 정확히 일치하는 템플릿을 조회합니다.
    - created_at 기준 내림차순 정렬 (최신순)
    - 목록에서는 내용(content)이 아닌 메타 정보(id, 버전, 요약, 생성일 등)만 반환합니다.

    예)
    - GET /templates/retrieve?template_type=소액수의&limit=10
    - GET /templates/retrieve?template_type=적격심사&limit=5
    """
    # template_type으로 정확히 일치하는 템플릿 조회 (최신순 N개)
    templates = (
        db.query(NoticeTemplate)
        .filter(NoticeTemplate.template_type == template_type)
        .order_by(NoticeTemplate.created_at.desc())
        .limit(limit)
        .all()
    )

    if not templates:
        raise HTTPException(
            status_code=404,
            detail=f"해당 template_type의 템플릿이 없습니다: {template_type}",
        )

    # 목록 응답 (content 제외)
    return {
        "total": len(templates),
        "template_type": template_type,
        "templates": [
            {
                "id": t.id,
                "template_type": t.template_type,
                "version": t.version,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in templates
        ]
    }


@router.get("/templates/{template_id}")
async def get_template_detail(
    template_id: int,
    db: Session = Depends(get_db),
):
    """
    템플릿 상세 조회 API (Template Detail)

    - 템플릿 ID로 단일 템플릿의 전체 내용을 조회합니다.
    - 목록 API(`/templates/retrieve`)에서 받은 id를 사용하여 호출합니다.
    """
    template = db.query(NoticeTemplate).filter(NoticeTemplate.id == template_id).first()

    if not template:
        raise HTTPException(
            status_code=404,
            detail=f"해당 ID의 템플릿이 없습니다: {template_id}",
        )

    # category, method는 template_type 패턴(예: '물품-소액수의')에서 유추 가능하지만,
    # 저장 규칙이 고정되지 않았을 수 있으므로 그대로 반환만 합니다.
    return {
        "id": template.id,
        "template_type": template.template_type,
        "version": template.version,
        "summary": template.summary,
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "content": template.content,
    }


@router.post("/templates/load-qualification")
async def load_qualification_template(db: Session = Depends(get_db)):
    """
    `templates/qualification_review.md` 파일을 읽어서 DB에 저장하는 테스트용 API

    - PostgreSQL 연결이 정상인지
    - 템플릿이 실제로 `notice_templates` 테이블에 들어가는지
    를 확인하기 위한 엔드포인트입니다.
    """
    from pathlib import Path

    # 프로젝트 루트 기준으로 템플릿 파일 경로 계산
    project_root = Path(__file__).resolve().parents[3]
    template_path = project_root / "templates" / "qualification_review.md"

    if not template_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"템플릿 파일을 찾을 수 없습니다: {template_path}",
        )

    markdown_text = template_path.read_text(encoding="utf-8")

    new_template = NoticeTemplate(
        template_type="적격심사",
        content=markdown_text,
        summary="파일에서 로드된 적격심사 기본 템플릿",
    )
    db.add(new_template)
    db.commit()
    db.refresh(new_template)

    return {
        "message": "qualification_review.md 템플릿이 저장되었습니다.",
        "id": new_template.id,
        "length": len(markdown_text),
    }


@router.get("/trend")
async def get_latest_notice(
    days_ago: int = Query(3, description="며칠 전부터 조회할지"),
    cntrctCnclsMthdNm: Optional[str] = Query(None, description="계약체결방법명 (예: 적격심사)")
):
    """
    최신 나라장터 공고문 URL 조회

    Args:
        days_ago: 며칠 전부터 조회할지 (기본 3일)
        cntrctCnclsMthdNm: 계약체결방법명 필터 (선택)

    Returns:
        공고문 URL (ntceSpecDocUrl1)
    """
    try:
        # 최신 공고의 공고문 URL 조회
        doc_url = get_latest_bid_notice(days_ago=days_ago, cntrctCnclsMthdNm=cntrctCnclsMthdNm)

        return {
            "status": "success",
            "doc_url": doc_url,
            "message": "최신 공고문 URL 조회 완료"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"공고문 조회 실패: {str(e)}")


@router.post("/validate-template")
async def validate_template(
    cntrctCnclsMthdNm: str = Query(..., description="공고 유형 (예: 적격심사, 소액수의)"),
    days_ago: int = Query(7, description="며칠 전부터 조회할지 (기본 7일)"),
    db: Session = Depends(get_db),
):
    """
    템플릿 검증 API

    1. 나라장터에서 해당 유형의 최신 공고문 조회
    2. 우리 템플릿 로드
    3. 비교 Agent로 차이점 분석
    4. 변경사항 있으면 신버전 템플릿 반환

    Args:
        cntrctCnclsMthdNm: 공고 유형 (적격심사, 소액수의 등)
        days_ago: 조회 기간 (기본 7일)
    """
    try:
        return validate_template_workflow(cntrctCnclsMthdNm, days_ago, db)

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"템플릿 검증 실패: {str(e)}")

# 헬퍼 함수들

@router.post("/extract")
async def extract_only(
    file: UploadFile = File(...)
):
    """
    추출 단계만 실행 (디버깅용)
    
    - 문서 업로드
    - Extractor Agent만 실행
    - 추출된 데이터 반환
    
    Args:
        file: 구매계획서 파일
    """
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
        
        # Extractor만 실행
        crew_service = BiddingDocumentCrew(state)
        extracted_data = crew_service.run_extraction(raw_text)
        
        return {
            "session_id": session_id,
            "file_name": file.filename,
            "status": "extracted",
            "raw_text_length": len(raw_text),
            "raw_text_preview": raw_text[:500] + "..." if len(raw_text) > 500 else raw_text,
            "extracted_data": extracted_data,
            "state": {
                "step": state.step,
                "created_at": state.created_at.isoformat(),
                "updated_at": state.updated_at.isoformat()
            }
        }
    except Exception as e:
        if session_id in agent_sessions:
            agent_sessions[session_id].add_error(str(e))
        raise HTTPException(status_code=400, detail=f"추출 실패: {str(e)}")


@router.post("/classify")
async def classify_only(
    file: UploadFile = File(...)
):
    """
    추출 + 분류 단계까지 실행 (디버깅용)
    
    - 문서 업로드
    - Extractor Agent 실행
    - Classifier Agent + Rule Engine 실행
    - 분류 결과 반환
    
    Args:
        file: 구매계획서 파일
    """
    session_id = str(uuid.uuid4())
    try:
        # 파일 읽기
        content = await file.read()
        file_extension = file.filename.lower().split('.')[-1]
        
        # HWP 파일인 경우 CrewAI 도구를 사용하도록 설정
        if file_extension == 'hwp':
            import base64
            # HWP 파일은 Base64로 인코딩해서 Extractor Agent가 도구를 사용하도록 함
            file_content_base64 = base64.b64encode(content).decode('utf-8')
            
            # AgentState 생성 (파일 정보 포함)
            state = AgentState(
                session_id=session_id,
                step="extract",
                raw_text=""  # HWP는 도구로 파싱하므로 빈 텍스트
            )
            # 파일 정보를 state에 저장 (도구에서 사용)
            state.file_content_base64 = file_content_base64
            state.file_name = file.filename
            
            # 저장
            agent_sessions[session_id] = state
            
            # Extractor + Classifier 실행 (HWP 파일 정보 전달)
            crew_service = BiddingDocumentCrew(state)
            extracted_data = crew_service.run_extraction_with_file(
                file_content_base64=file_content_base64,
                filename=file.filename,
                use_reflection=True
            )
        else:
            # 일반 파일은 기존 방식대로 파싱
            raw_text = parse_document(content, file.filename)
            
            # AgentState 생성
            state = AgentState(
                session_id=session_id,
                step="extract",
                raw_text=raw_text
            )
            
            # 저장
            agent_sessions[session_id] = state
            
            # Extractor + Classifier 실행
            crew_service = BiddingDocumentCrew(state)
            extracted_data = crew_service.run_extraction(raw_text, use_reflection=True)  # classify에서 리플렉션 활성화
        
        classification = crew_service.run_classification(extracted_data)
        
        return {
            "session_id": session_id,
            "file_name": file.filename,
            "status": "classified",
            "extracted_data": extracted_data,
            "classification": classification,
            "state": {
                "step": state.step,
                "created_at": state.created_at.isoformat(),
                "updated_at": state.updated_at.isoformat()
            }
        }
    except Exception as e:
        import traceback
        error_detail = str(e)
        error_traceback = traceback.format_exc()
        
        print(f"\n❌ /classify 엔드포인트 에러 발생:")
        print(f"   에러 메시지: {error_detail}")
        print(f"   상세 스택 트레이스:")
        print(error_traceback)
        
        if session_id in agent_sessions:
            agent_sessions[session_id].add_error(error_detail)
        
        # 더 자세한 에러 정보 제공
        raise HTTPException(
            status_code=400, 
            detail=f"분류 실패: {error_detail}\n\n스택 트레이스:\n{error_traceback}"
        )


@router.post("/convert-html")
async def convert_html(
    request: Request,
    format: str = Query("pdf", description="출력 형식: pdf, docx, hwp")
):
    """
    HTML 완성본을 PDF/DOCX/HWP로 변환 (다운로드 가능)
    
    - HTML에서 수정/추출된 부분은 파란색으로 표시됨
    - PDF: weasyprint 사용 (스타일 완벽 유지)
    - DOCX: LibreOffice 사용 (스타일 대부분 유지)
    - HWP: LibreOffice 사용 (스타일 일부 유지)
    
    Args:
        request: Request 객체 (body에 HTML 텍스트)
        format: 출력 형식 (pdf, docx, hwp)
    
    Returns:
        변환된 파일 (FileResponse) - 브라우저에서 자동 다운로드
    
    Example (JavaScript/Fetch):
        ```javascript
        const html = '<!DOCTYPE html><html><body><p>테스트</p></body></html>';
        
        const response = await fetch('http://localhost:8000/api/v1/agent/convert-html?format=pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'text/html' },
            body: html
        });
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = '문서.pdf';
        a.click();
        ```
    
    Example (Python):
        ```python
        import requests
        
        html = '<!DOCTYPE html><html><body><p>테스트</p></body></html>'
        
        response = requests.post(
            "http://localhost:8000/api/v1/agent/convert-html?format=pdf",
            data=html,
            headers={"Content-Type": "text/html"}
        )
        
        with open("output.pdf", "wb") as f:
            f.write(response.content)
        ```
    """
    try:
        # Request body에서 HTML 읽기
        html_content = await request.body()
        html_content = html_content.decode("utf-8")
        
        if not html_content or not html_content.strip():
            raise HTTPException(status_code=400, detail="HTML 내용이 비어있습니다.")
        
        # HTML을 지정된 형식으로 변환
        file_bytes = convert_html_document(html_content, format.lower())
        
        # 파일 확장자 및 MIME 타입 설정
        format_map = {
            "pdf": ("pdf", "application/pdf"),
            "docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            "hwp": ("hwp", "application/x-hwp")
        }
        
        if format.lower() not in format_map:
            raise ValueError(f"지원하지 않는 형식: {format}. 'pdf', 'docx', 또는 'hwp'를 사용하세요.")
        
        extension, media_type = format_map[format.lower()]
        filename = f"문서_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{extension}"
        
        # 임시 파일 생성
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}") as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name
        
        # FileResponse로 반환 (브라우저에서 자동 다운로드)
        return FileResponse(
            tmp_path,
            media_type=media_type,
            filename=filename,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"HTML 변환 실패: {str(e)}"
        )


@router.get("/debug/{session_id}")
async def debug_session(session_id: str):
    """
    세션의 모든 중간 결과 조회 (디버깅용)
    
    - 추출된 데이터
    - 분류 결과
    - 생성된 문서
    - 에러 로그
    
    Args:
        session_id: 세션 ID
    """
    if session_id not in agent_sessions:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    
    state = agent_sessions[session_id]
    
    return {
        "session_id": session_id,
        "state": {
            "step": state.step,
            "retry_count": state.retry_count,
            "created_at": state.created_at.isoformat(),
            "updated_at": state.updated_at.isoformat(),
            "errors": state.errors
        },
        "raw_text_length": len(state.raw_text) if state.raw_text else 0,
        "raw_text_preview": (state.raw_text[:500] + "...") if state.raw_text and len(state.raw_text) > 500 else (state.raw_text or ""),
        "extracted_data": state.extracted_data,
        "classification": state.classification,
        "generated_document_length": len(state.generated_document) if state.generated_document else 0,
        "generated_document_preview": (state.generated_document[:1000] + "...") if state.generated_document and len(state.generated_document) > 1000 else (state.generated_document or ""),
        "user_feedback": state.user_feedback
    }


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
