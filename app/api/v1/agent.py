"""
Agent API Endpoints

4개의 엔드포인트:
1. POST /api/v1/agent/upload - 문서 업로드만 받아서 자동 처리 (원스톱)
2. POST /api/v1/agent/run - Agent 재실행 (피드백 반영 시)
3. GET /api/v1/agent/state/{id} - 현재 상태 조회
4. POST /api/v1/agent/feedback - 사용자 피드백 반영

템플릿과 법령 참조는 시스템이 자동으로 처리합니다.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
import json
import io
from typing import Optional, Dict, Any
import uuid
from datetime import datetime
import tempfile
import os

from app.infra.db.database import get_db, engine, Base
from app.models.agent_state import AgentState
from app.models.schemas import UserFeedback
from app.services.crew_service import BiddingDocumentCrew
from app.services.nara_bid_service import get_latest_bid_notice
from app.utils.document_parser import parse_document
from app.utils.document_converter import convert_document
from app.config import get_settings

from sqlalchemy.orm import Session
from app.infra.db.models import NoticeTemplate

# 애플리케이션 시작 시 테이블이 없다면 생성
Base.metadata.create_all(bind=engine)

settings = get_settings()

router = APIRouter()

# 간단한 in-memory 스토리지 (실제론 DB 사용)
agent_sessions: Dict[str, AgentState] = {}


def detect_file_type(content: bytes) -> str:
    """
    파일 바이트 시그니처로 파일 타입 감지

    Args:
        content: 파일 바이트

    Returns:
        파일 타입 ('pdf', 'hwp', 'docx', 'txt')
    """
    if not content or len(content) < 4:
        return 'txt'

    # PDF: %PDF (0x25 0x50 0x44 0x46)
    if content[:4] == b'%PDF':
        return 'pdf'

    # HWP 5.0 이상 (ZIP based): PK (0x50 0x4B)
    if content[:2] == b'PK':
        # DOCX도 ZIP이므로 추가 확인 필요
        if b'HWP Document File' in content[:1024] or b'hwp' in content[:512].lower():
            return 'hwp'
        elif b'word/' in content[:1024]:
            return 'docx'
        # 기본적으로 ZIP 시그니처면 HWP로 가정 (나라장터에서는 주로 HWP)
        return 'hwp'

    # HWP 3.0 이하 (OLE based): D0 CF 11 E0
    if content[:4] == b'\xd0\xcf\x11\xe0':
        return 'hwp'

    # DOCX (ZIP): PK로 시작하지만 위에서 처리됨

    # 기본값
    return 'txt'


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    format: Optional[str] = Query("markdown", description="출력 형식: markdown, pdf, docx")
):
    """
    문서 업로드 + 즉시 Agent 실행 (통합)

    - 발주계획서 업로드 (PDF, DOCX, HWP)만 받음
    - 텍스트 추출
    - AgentState 생성
    - 즉시 Agent Loop 실행
    - 템플릿과 법령은 시스템이 자동으로 처리
    - 최종 결과 반환 (마크다운, PDF, DOCX)

    Args:
        file: 구매계획서 파일
        format: 출력 형식 (markdown, pdf, docx)
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

        # 형식에 따라 반환
        if format.lower() == "markdown":
            # JSON 직렬화 문제 방지: JSONResponse를 명시적으로 사용
            response_data = {
                "session_id": session_id,
                "file_name": file.filename,
                "status": "completed",
                "format": "markdown",
                "document": final_document,  # 마크다운 텍스트
                "state": {
                    "step": state.step,
                    "retry_count": state.retry_count,
                    "created_at": state.created_at.isoformat(),
                    "updated_at": state.updated_at.isoformat()
                }
            }
            
            # JSON 직렬화 전 문서 길이 확인
            try:
                # JSON 직렬화 테스트 (실제 직렬화 전에 문제 확인)
                json_str = json.dumps(response_data, ensure_ascii=False, indent=None)
                json_length = len(json_str)
                print(f"📦 JSON 직렬화 후 길이: {json_length}자 (원본 문서: {document_length}자)")
                
                # JSONResponse를 명시적으로 사용하여 직렬화 제어
                return JSONResponse(
                    content=response_data,
                    media_type="application/json"
                )
            except Exception as json_error:
                print(f"❌ JSON 직렬화 오류: {json_error}")
                # JSON 직렬화 실패 시 에러 반환
                raise HTTPException(
                    status_code=500,
                    detail=f"JSON 직렬화 실패: {str(json_error)}. 문서 길이: {document_length}자"
                )
        else:
            # PDF 또는 DOCX로 변환
            try:
                file_bytes = convert_document(final_document, format.lower())
                
                # 파일 확장자 결정
                extension = "pdf" if format.lower() == "pdf" else "docx"
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
                # 변환 실패 시 마크다운 반환
                return {
                    "session_id": session_id,
                    "file_name": file.filename,
                    "status": "completed",
                    "format": "markdown",
                    "document": final_document,
                    "error": f"파일 변환 실패: {str(e)}. 마크다운 형식으로 반환합니다.",
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
    template_type: str,
    markdown_text: str,
    db: Session = Depends(get_db),
):
    """마크다운 문자열을 그대로 DB에 저장"""
    new_template = NoticeTemplate(
        template_type=template_type,
        content=markdown_text,
        summary="에이전트에 의해 자동 생성됨",
    )
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    return {"message": "템플릿이 저장되었습니다."}


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
        # 1. 최신 공고문 URL 여러 개 조회
        num_samples = 3  # 비교할 샘플 개수
        print(f"📥 최신 공고문 {num_samples}개 조회 중... (유형: {cntrctCnclsMthdNm}, 기간: {days_ago}일)")
        doc_urls = get_latest_bid_notice(days_ago=days_ago, cntrctCnclsMthdNm=cntrctCnclsMthdNm, limit=num_samples)

        # 단일 URL이면 리스트로 변환
        if isinstance(doc_urls, str):
            doc_urls = [doc_urls]

        # 2. 모든 공고문 다운로드 및 파싱
        import requests
        latest_docs = []
        for idx, doc_url in enumerate(doc_urls, 1):
            print(f"📄 공고문 {idx}/{len(doc_urls)} 다운로드 중: {doc_url}")
            try:
                response = requests.get(doc_url, timeout=30)
                response.raise_for_status()

                # 파일 타입 감지
                file_content = response.content
                file_type = detect_file_type(file_content)

                # 파싱
                doc_content = parse_document(file_content, f"latest_notice_{idx}.{file_type}")
                latest_docs.append({
                    "url": doc_url,
                    "content": doc_content,
                    "index": idx
                })
                print(f"✅ 공고문 {idx} 파싱 완료 (형식: {file_type}, 길이: {len(doc_content)}자)")
            except Exception as e:
                print(f"⚠️ 공고문 {idx} 다운로드 실패: {str(e)}")
                continue

        if not latest_docs:
            raise HTTPException(status_code=500, detail="모든 공고문 다운로드 실패")

        print(f"✅ 총 {len(latest_docs)}개 공고문 파싱 완료")

        # 3. 우리 템플릿 로드
        from app.tools.template_selector import get_template_selector
        from app.models.schemas import ClassificationResult

        template_selector = get_template_selector()

        # 공고 유형을 ClassificationResult로 변환
        classification_result = ClassificationResult(
            recommended_type=cntrctCnclsMthdNm,
            confidence=1.0,
            reason="템플릿 검증용",
            alternative_types=[]
        )

        template = template_selector.select_template(classification_result, preferred_format="md")
        our_template_content = template.content
        print(f"✅ 템플릿 로드 완료: {template.template_id}")

        # 4. Agent로 여러 공고문 비교
        from app.services.agents import create_template_comparator_agent
        from app.services.tasks import create_multi_template_comparison_task
        from crewai import Crew, Process

        comparator = create_template_comparator_agent()
        comparison_task = create_multi_template_comparison_task(
            comparator,
            latest_docs,  # 여러 공고문 전달
            our_template_content
        )

        crew = Crew(
            agents=[comparator],
            tasks=[comparison_task],
            process=Process.sequential,
            verbose=True
        )

        print("🔍 템플릿 비교 중...")
        result = crew.kickoff()

        # 5. 결과 파싱
        result_str = str(result)
        print(f"🔍 Agent 응답 길이: {len(result_str)}자")

        try:
            comparison_result = json.loads(result_str)
            print("✅ 직접 JSON 파싱 성공")
        except json.JSONDecodeError as e:
            print(f"⚠️ 직접 JSON 파싱 실패: {str(e)}")
            # JSON 파싱 실패 시 텍스트에서 JSON 추출 시도
            import re

            # 여러 패턴 시도 (전체 텍스트에서)
            patterns = [
                r'```json\s*(\{[\s\S]*\})\s*```',  # ```json {...} ``` (전체)
                r'```\s*(\{[\s\S]*\})\s*```',      # ``` {...} ``` (전체)
                r'(\{[\s\S]*\})',                   # { ... } (가장 큰 JSON)
            ]

            for pattern in patterns:
                json_match = re.search(pattern, result_str)
                if json_match:
                    try:
                        json_text = json_match.group(1)
                        print(f"📝 패턴 매칭, JSON 길이: {len(json_text)}자")

                        # JSON 안의 줄바꿈 문제 해결: Python의 literal_eval 시도
                        # 또는 수동으로 파싱
                        try:
                            comparison_result = json.loads(json_text)
                        except json.JSONDecodeError:
                            # JSON5 스타일로 재시도 (따옴표 없는 줄바꿈 처리)
                            # updated_template 필드를 별도로 추출
                            template_match = re.search(r'"updated_template":\s*"([\s\S]*?)"(?=\s*[,}])', json_text)
                            if template_match:
                                # updated_template 제거하고 나머지만 파싱
                                json_without_template = re.sub(
                                    r'"updated_template":\s*"[\s\S]*?"(?=\s*[,}])',
                                    '"updated_template": "PLACEHOLDER"',
                                    json_text
                                )
                                comparison_result = json.loads(json_without_template)
                                # 실제 템플릿 내용을 다시 넣기
                                comparison_result["updated_template"] = template_match.group(1)
                            else:
                                raise

                        print("✅ JSON 추출 및 파싱 성공")
                        break
                    except json.JSONDecodeError as parse_error:
                        print(f"⚠️ 패턴 매칭 후 파싱 실패: {str(parse_error)}")
                        continue
            else:
                # 모든 패턴 실패
                print(f"❌ 모든 JSON 추출 패턴 실패")
                print(f"🔍 응답 앞 500자: {result_str[:500]}")
                comparison_result = {
                    "error": "JSON 파싱 실패",
                    "raw_output": result_str[:2000],
                    "has_changes": False
                }

        # 6. 업데이트된 템플릿을 DB에 저장 (변경사항이 있을 때만)
        new_template_row = None
        if comparison_result.get("has_changes"):
            updated_template = comparison_result.get("updated_template", "")
            if updated_template:
                # JSON 이스케이프 문자 해제 (\\n → 실제 줄바꿈)
                updated_template = updated_template.replace("\\n", "\n")
                updated_template = updated_template.replace("\\t", "\t")
                updated_template = updated_template.replace('\\"', '"')

                # 이전 버전 조회 (있으면 버전 넘버 증가용)
                latest_existing = (
                    db.query(NoticeTemplate)
                    .filter(NoticeTemplate.template_type == cntrctCnclsMthdNm)
                    .order_by(NoticeTemplate.created_at.desc())
                    .first()
                )

                # 간단한 버전 증가 로직: "1.0.0" → "1.0.1" 식으로 patch만 +1
                new_version = "1.0.0"
                if latest_existing and latest_existing.version:
                    parts = latest_existing.version.split(".")
                    if len(parts) == 3 and parts[2].isdigit():
                        parts[2] = str(int(parts[2]) + 1)
                        new_version = ".".join(parts)
                    else:
                        # 형식이 다르면 그대로 사용
                        new_version = latest_existing.version

                summary = comparison_result.get("summary", "자동 검증 결과에 따른 업데이트 템플릿")

                new_template_row = NoticeTemplate(
                    template_type=cntrctCnclsMthdNm,
                    version=new_version,
                    content=updated_template,
                    summary=summary[:255] if summary else None,
                )
                db.add(new_template_row)
                db.commit()
                db.refresh(new_template_row)

                print(
                    f"✅ 업데이트된 템플릿을 DB에 저장: id={new_template_row.id}, "
                    f"type={new_template_row.template_type}, version={new_template_row.version}"
                )

        # 7. 응답 생성 (변경점 및 저장 결과 반환)
        response_data = {
            "status": "unchanged" if not comparison_result.get("has_changes") else "changed",
            "template_type": cntrctCnclsMthdNm,
            "changes_detected": comparison_result.get("has_changes", False),
            "summary": comparison_result.get("summary", ""),
            "changes": comparison_result.get("changes", []),
            "saved_template": {
                "id": new_template_row.id,
                "version": new_template_row.version,
                "created_at": new_template_row.created_at.isoformat() if new_template_row and new_template_row.created_at else None,
            } if new_template_row else None,
        }

        return response_data

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
        
        # Extractor + Classifier 실행
        crew_service = BiddingDocumentCrew(state)
        extracted_data = crew_service.run_extraction(raw_text)
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
        if session_id in agent_sessions:
            agent_sessions[session_id].add_error(str(e))
        raise HTTPException(status_code=400, detail=f"분류 실패: {str(e)}")


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
