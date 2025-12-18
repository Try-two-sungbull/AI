"""
문서 변환 전용 API 엔드포인트

Spring Boot로부터 HTML을 받아 PDF/DOCX/HWP로 변환하여 스트리밍 응답
CrewAI Agent를 통해 변환 작업을 수행합니다.
"""
from fastapi import APIRouter, HTTPException, Request, Body
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request as StarletteRequest
from pydantic import BaseModel, Field, ValidationError
from typing import Literal, Optional
import io
import logging
import json
import base64
import re
from urllib.parse import quote

from crewai import Agent, Task, Crew, Process
from app.services.agents import get_llm
from app.tools.crewai_tools import get_converter_tools

logger = logging.getLogger(__name__)

router = APIRouter()


class ConvertRequest(BaseModel):
    """문서 변환 요청 모델"""
    html: Optional[str] = Field(default=None, description="HTML 원문 (줄바꿈은 \\n으로 이스케이프)")
    format: Literal["pdf", "docx", "hwp"] = Field(..., description="변환할 포맷 (pdf/docx/hwp)")
    filename: str = Field(..., description="파일명 (확장자 제외)")
    html_base64: Optional[str] = Field(default=None, description="HTML 원문 (Base64 인코딩, html 필드 대신 사용 가능)")


def escape_control_chars_in_strings(text: str) -> str:
    """JSON 문자열 리터럴 내의 제어 문자만 이스케이프 (개선된 버전)"""
    # JSON 문자열 값 내의 제어 문자를 이스케이프
    # 패턴: "..." 형태의 문자열 내부만 처리
    def escape_in_string(match):
        content = match.group(1)
        # 제어 문자 이스케이프
        escaped = content
        # 이미 이스케이프된 문자는 건드리지 않음
        # 제어 문자만 처리
        result = []
        i = 0
        while i < len(escaped):
            if escaped[i] == '\\' and i + 1 < len(escaped):
                # 이미 이스케이프된 문자는 그대로 유지
                result.append(escaped[i])
                result.append(escaped[i + 1])
                i += 2
            else:
                char = escaped[i]
                char_code = ord(char)
                # 제어 문자 (0x00-0x1F, 0x7F-0x9F) 처리
                if char_code < 32 or (0x7F <= char_code <= 0x9F):
                    if char == '\n':
                        result.append('\\n')
                    elif char == '\r':
                        result.append('\\r')
                    elif char == '\t':
                        result.append('\\t')
                    elif char == '\b':
                        result.append('\\b')
                    elif char == '\f':
                        result.append('\\f')
                    elif char_code == 0:
                        result.append('\\u0000')
                    else:
                        result.append(f'\\u{char_code:04x}')
                else:
                    result.append(char)
                i += 1
        return '"' + ''.join(result) + '"'
    
    # JSON 문자열 패턴 매칭: "..." 형태 (이스케이프된 따옴표 고려)
    # 더 정확한 패턴: 따옴표로 시작하고, 이스케이프되지 않은 따옴표로 끝나는 문자열
    pattern = r'"((?:[^"\\]|\\.)*)"'
    
    try:
        return re.sub(pattern, escape_in_string, text)
    except Exception as e:
        logger.warning(f"정규식 처리 실패, 기본 방법 사용: {e}")
        # Fallback: 간단한 방법
        result = []
        for char in text:
            char_code = ord(char)
            if char_code < 32 or (0x7F <= char_code <= 0x9F):
                if char == '\n':
                    result.append('\\n')
                elif char == '\r':
                    result.append('\\r')
                elif char == '\t':
                    result.append('\\t')
                elif char == '\b':
                    result.append('\\b')
                elif char == '\f':
                    result.append('\\f')
                elif char_code == 0:
                    result.append('\\u0000')
                else:
                    result.append(f'\\u{char_code:04x}')
            else:
                result.append(char)
        return ''.join(result)


@router.post(
    "/convert",
    response_model=None,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": ConvertRequest.model_json_schema()
                }
            }
        }
    }
)
async def convert_document(request: Request):
    """
    HTML을 PDF/DOCX/HWP로 변환 (Spring Boot용 내부 API)
    
    **Swagger UI에서 테스트 가능합니다!** 
    - http://localhost:8000/docs 에서 "convert" 엔드포인트를 찾아서 테스트하세요.
    
    **동작 방식:**
    1. Spring Boot로부터 HTML + format + filename 수신
    2. 요청된 단일 포맷만 생성
    3. 스트리밍 응답으로 반환
    4. 임시 파일 즉시 삭제
    
    **지원 포맷:**
    - `pdf`: WeasyPrint 사용
    - `docx`: LibreOffice 사용
    - `hwp`: LibreOffice 사용
    
    **예시 요청:**
    ```json
    {
        "html": "<!DOCTYPE html>...</html>",
        "format": "hwp",
        "filename": "입찰공고"
    }
    ```
    
    **응답:**
    - Content-Type: application/pdf, application/vnd.openxmlformats-officedocument.wordprocessingml.document, application/x-hwp
    - Content-Disposition: attachment; filename="입찰공고.hwp"
    - 스트리밍 바이너리 데이터
    """
    try:
        # Request 본문 직접 파싱 (제어 문자 처리 포함)
        raw_body = await request.body()
        body_str = raw_body.decode('utf-8')
        
        # JSON 파싱 시도
        body = None
        try:
            body = json.loads(body_str)
        except json.JSONDecodeError:
            # 실제 줄바꿈이 포함된 JSON을 처리하기 위해
            # 문자열 값 내의 실제 줄바꿈을 \n으로 변환 시도
            try:
                # "html": "..." 패턴을 찾아서 실제 줄바꿈을 \n으로 변환
                def fix_newlines_in_html_field(match):
                    field_name = match.group(1)
                    # 문자열 값 시작 위치 찾기
                    value_start = match.end()
                    # 다음 따옴표나 필드 끝까지 찾기
                    i = value_start
                    in_string = False
                    escape_next = False
                    result = [match.group(0)]  # 원본 필드명 부분
                    
                    while i < len(body_str):
                        char = body_str[i]
                        
                        if escape_next:
                            result.append(char)
                            escape_next = False
                            i += 1
                            continue
                        
                        if char == '\\':
                            result.append(char)
                            escape_next = True
                            i += 1
                            continue
                        
                        if char == '"':
                            if in_string:
                                # 문자열 끝
                                result.append(char)
                                # 나머지 부분 추가
                                result.append(body_str[i+1:])
                                break
                            else:
                                # 문자열 시작
                                in_string = True
                                result.append(char)
                                i += 1
                                continue
                        
                        if in_string:
                            # 문자열 내부에서 실제 줄바꿈을 \n으로 변환
                            if char == '\n':
                                result.append('\\n')
                            elif char == '\r':
                                result.append('\\r')
                            elif char == '\t':
                                result.append('\\t')
                            else:
                                result.append(char)
                        else:
                            result.append(char)
                        
                        i += 1
                    
                    return ''.join(result)
                
                # "html": " 패턴 찾기
                html_field_pattern = r'"html"\s*:\s*"'
                if re.search(html_field_pattern, body_str):
                    # 간단한 방법: 문자열 값 내의 실제 줄바꿈을 \n으로 변환
                    # JSON 구조를 유지하면서 문자열 값만 수정
                    lines = body_str.split('\n')
                    fixed_lines = []
                    in_html_string = False
                    quote_count = 0
                    
                    for line in lines:
                        # "html": " 이후인지 확인
                        if '"html"' in line and ':' in line:
                            # html 필드 시작
                            fixed_lines.append(line)
                            # 따옴표 개수 확인
                            quote_count += line.count('"') - line.count('\\"')
                            if quote_count % 2 == 1:
                                in_html_string = True
                        elif in_html_string:
                            # HTML 문자열 내부
                            # 실제 줄바꿈을 \n으로 변환
                            fixed_lines.append('\\n' + line)
                            # 따옴표로 문자열이 끝나는지 확인
                            quote_count += line.count('"') - line.count('\\"')
                            if quote_count % 2 == 0:
                                in_html_string = False
                        else:
                            fixed_lines.append(line)
                    
                    fixed_body = '\n'.join(fixed_lines)
                    # 실제 줄바꿈을 제거하고 \n으로만 구성
                    fixed_body = fixed_body.replace('\n', '\\n').replace('\\n\\n', '\\n')
                    # 다시 실제 줄바꿈으로 변환 (JSON 구조용)
                    fixed_body = fixed_body.replace('\\n', '\n')
                    # 하지만 문자열 값 내의 \n은 유지
                    # 이건 복잡하니 다른 방법 사용
                    
                    # 더 간단한 방법: 정규식으로 문자열 값 내의 실제 줄바꿈만 변환
                    def replace_newlines_in_strings(text):
                        result = []
                        i = 0
                        in_string = False
                        escape_next = False
                        
                        while i < len(text):
                            char = text[i]
                            
                            if escape_next:
                                result.append(char)
                                escape_next = False
                                i += 1
                                continue
                            
                            if char == '\\':
                                result.append(char)
                                escape_next = True
                                i += 1
                                continue
                            
                            if char == '"':
                                in_string = not in_string
                                result.append(char)
                                i += 1
                                continue
                            
                            if in_string:
                                if char == '\n':
                                    result.append('\\n')
                                elif char == '\r':
                                    result.append('\\r')
                                elif char == '\t':
                                    result.append('\\t')
                                else:
                                    result.append(char)
                            else:
                                result.append(char)
                            
                            i += 1
                        
                        return ''.join(result)
                    
                    fixed_body = replace_newlines_in_strings(body_str)
                    body = json.loads(fixed_body)
                    logger.info("✅ 실제 줄바꿈을 \\n으로 변환 후 JSON 파싱 성공")
                else:
                    raise json.JSONDecodeError("No html field found", body_str, 0)
            except Exception as e:
                logger.warning(f"줄바꿈 변환 실패: {e}")
                # 기존 로직 계속 진행
                pass
        
        # 기존 JSON 파싱 로직 (실패 시)
        if body is None:
            try:
                body = json.loads(body_str)
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ JSON 파싱 실패, HTML 필드 추출 후 재구성 시도: {str(e)}")
                
                # 방법 1: 정규식으로 HTML 필드 추출 후 base64로 변환
                try:
                    # "html": "..." 패턴 찾기 - 더 정확한 패턴 사용
                    # JSON 문자열 내의 따옴표를 올바르게 처리
                    html_pattern = r'"html"\s*:\s*"((?:[^"\\]|\\.)*)"'
                    html_match = re.search(html_pattern, body_str, re.DOTALL)
                    
                    if not html_match:
                        # 멀티라인 HTML을 위한 더 관대한 패턴 시도
                        # "html": " 부터 다음 필드나 } 까지
                        html_pattern2 = r'"html"\s*:\s*"(.*?)"(?=\s*[,}])'
                        html_match = re.search(html_pattern2, body_str, re.DOTALL)
                    
                    if html_match:
                        html_content = html_match.group(1)
                        # 이스케이프 문자 처리 (JSON 이스케이프 해제)
                        # 순서 중요: \\ 먼저 처리해야 함
                        html_content = html_content.replace('\\\\', '\\PLACEHOLDER_BACKSLASH\\')
                        html_content = html_content.replace('\\n', '\n').replace('\\r', '\r').replace('\\t', '\t')
                        html_content = html_content.replace('\\"', '"').replace('\\/', '/')
                        html_content = html_content.replace('\\PLACEHOLDER_BACKSLASH\\', '\\')
                        
                        # HTML을 base64로 인코딩
                        html_base64_encoded = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
                        
                        # 원본 JSON에서 html 필드를 html_base64로 교체
                        # 정확한 위치 찾기
                        html_start = html_match.start()
                        html_end = html_match.end()
                        
                        # html 필드 부분을 html_base64로 교체
                        modified_body = body_str[:html_start] + f'"html_base64": "{html_base64_encoded}"' + body_str[html_end:]
                        
                        # 다시 JSON 파싱 시도
                        try:
                            body = json.loads(modified_body)
                            logger.info("✅ HTML 필드를 base64로 변환 후 JSON 파싱 성공")
                        except json.JSONDecodeError as e4:
                            logger.warning(f"base64 변환 후에도 파싱 실패: {e4}")
                            # 방법 2: HTML 필드를 제거하고 나머지만 파싱
                            body_without_html = body_str[:html_start] + body_str[html_end:]
                            body_without_html = re.sub(r',\s*,', ',', body_without_html)  # 연속된 쉼표 제거
                            body_without_html = re.sub(r',\s*}', '}', body_without_html)  # 마지막 쉼표 제거
                            body_without_html = re.sub(r',\s*]', ']', body_without_html)
                            try:
                                partial_body = json.loads(body_without_html)
                                # HTML은 별도로 base64로 추가
                                partial_body['html_base64'] = html_base64_encoded
                                body = partial_body
                                logger.info("✅ HTML 필드 제거 후 JSON 파싱 성공, base64로 추가")
                            except Exception as e5:
                                logger.warning(f"부분 파싱도 실패: {e5}")
                except Exception as e3:
                    logger.warning(f"정규식 추출 실패: {e3}")
                
                # 방법 3: 제어 문자 이스케이프 처리
                if body is None:
                    try:
                        cleaned_body = escape_control_chars_in_strings(body_str)
                        body = json.loads(cleaned_body)
                        logger.info("✅ 제어 문자 이스케이프 후 JSON 파싱 성공")
                    except json.JSONDecodeError as e2:
                        logger.warning(f"제어 문자 처리도 실패: {e2}")
                
                # 방법 4: 공격적인 제어 문자 제거
                if body is None:
                    try:
                        import unicodedata
                        aggressive_clean = ''.join(
                            char if unicodedata.category(char)[0] != 'C' or char in '\n\r\t'
                            else ''
                            for char in body_str
                        )
                        body = json.loads(aggressive_clean)
                        logger.info("✅ 공격적인 제어 문자 제거 후 파싱 성공")
                    except:
                        pass
                
                # 모든 시도 실패
                if body is None:
                    logger.error(f"❌ 모든 JSON 파싱 시도 실패")
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "message": "유효하지 않은 JSON 형식입니다",
                            "error": str(e),
                            "hint": "HTML 문자열의 줄바꿈을 \\n으로 이스케이프하거나, HTML을 base64로 인코딩하여 전송해주세요. (html_base64 필드 사용 권장)"
                        }
                    )
        
        # Pydantic 모델로 검증
        try:
            convert_request = ConvertRequest(**body)
        except ValidationError as e:
            logger.error(f"❌ 요청 검증 실패: {e.errors()}")
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "요청 검증 실패",
                    "errors": e.errors()
                }
            )
        
        # html_base64가 있으면 디코딩하여 html 필드에 설정
        if convert_request.html_base64:
            try:
                convert_request.html = base64.b64decode(convert_request.html_base64).decode('utf-8')
                logger.info("✅ html_base64 디코딩 완료")
            except Exception as e:
                logger.error(f"❌ html_base64 디코딩 실패: {str(e)}")
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "html_base64 디코딩 실패",
                        "error": str(e)
                    }
                )
        
        # html 필드가 base64로 인코딩되어 있는지 확인하고 디코딩
        if convert_request.html:
            html_stripped = convert_request.html.strip()
            # HTML 태그로 시작하지 않으면 base64일 가능성 확인
            if not html_stripped.startswith('<') and not html_stripped.startswith('<!DOCTYPE'):
                # base64 디코딩 시도
                try:
                    # 공백 제거 후 디코딩 시도
                    base64_str = html_stripped.replace('\n', '').replace('\r', '').replace(' ', '')
                    decoded_html = base64.b64decode(base64_str).decode('utf-8')
                    # 디코딩된 결과가 HTML인지 확인
                    decoded_stripped = decoded_html.strip()
                    if decoded_stripped.startswith('<!DOCTYPE') or decoded_stripped.startswith('<html') or decoded_stripped.startswith('<HTML'):
                        convert_request.html = decoded_html
                        logger.info("✅ html 필드의 base64 자동 디코딩 완료")
                except Exception as e:
                    # base64 디코딩 실패하면 원본 그대로 사용 (일반 HTML 문자열일 수 있음)
                    logger.debug(f"html 필드 base64 디코딩 시도 실패 (원본 그대로 사용): {e}")
        
        # html 또는 html_base64 중 하나는 필수
        if not convert_request.html:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "html 또는 html_base64 필드 중 하나는 필수입니다",
                    "hint": "HTML 문자열의 줄바꿈을 \\n으로 이스케이프하거나, HTML을 base64로 인코딩하여 html_base64 필드로 전송해주세요."
                }
            )
        
        logger.info(f"📄 문서 변환 요청: format={convert_request.format}, filename={convert_request.filename}, html 길이: {len(convert_request.html)}")
        
        # CrewAI 도구를 직접 호출하여 변환 (확실한 방법)
        format_name = {
            "pdf": "PDF",
            "docx": "DOCX",
            "hwp": "HWP"
        }.get(convert_request.format, convert_request.format.upper())
        
        logger.info(f"📄 HTML → {format_name} 변환 시작...")
        
        file_bytes = None
        
        try:
            # convert_html_document 함수 사용 (PDF는 DOCX 경로 사용, 인코딩 문제 해결)
            from app.utils.document_converter import convert_html_document
            
            logger.info(f"convert_html_document 호출: format={convert_request.format}")
            file_bytes = convert_html_document(convert_request.html, convert_request.format)
            logger.info(f"✅ {format_name.upper()} 변환 완료: {len(file_bytes)} bytes")
        except Exception as e2:
            import traceback
            logger.error(f"❌ 변환 실패: {str(e2)}")
            logger.error(f"스택 트레이스:\n{traceback.format_exc()}")
            # HTTPException은 그대로 전파
            from fastapi import HTTPException as FastAPIHTTPException
            if isinstance(e2, FastAPIHTTPException):
                raise
            raise HTTPException(
                status_code=500,
                detail=f"{format_name} 변환 실패: {str(e2)}"
            )
        
        # Content-Type 및 확장자 설정
        # HWP는 LibreOffice에서 지원하지 않으므로 DOCX로 변환됨
        actual_format = convert_request.format
        if actual_format == "hwp":
            # HWP 요청은 실제로 DOCX로 변환되므로 DOCX로 처리
            actual_format = "docx"
            logger.warning("⚠️ HWP 변환은 지원하지 않습니다. DOCX 파일을 반환합니다.")
        
        content_type_map = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "hwp": "application/x-hwp"
        }
        content_type = content_type_map.get(actual_format)
        extension = actual_format
        
        if file_bytes is None:
            raise HTTPException(
                status_code=500,
                detail=f"{format_name} 변환 실패: 파일을 생성할 수 없습니다."
            )
        
        logger.info(f"✅ 변환 완료: {len(file_bytes)} bytes")
        
        # 파일명 생성 (확장자 추가)
        filename = f"{convert_request.filename}.{extension}"
        
        # 한글 파일명을 HTTP 헤더에 안전하게 인코딩 (RFC 5987)
        # ASCII 문자만 있으면 그대로 사용, 한글이 있으면 UTF-8로 인코딩
        try:
            filename.encode('ascii')
            # ASCII만 있으면 그대로 사용
            content_disposition = f'attachment; filename="{filename}"'
        except UnicodeEncodeError:
            # 한글이 있으면 RFC 5987 형식으로 인코딩
            encoded_filename = quote(filename, safe='')
            content_disposition = f"attachment; filename*=UTF-8''{encoded_filename}"
        
        # 스트리밍 응답 생성
        file_stream = io.BytesIO(file_bytes)
        
        return StreamingResponse(
            file_stream,
            media_type=content_type,
            headers={
                "Content-Disposition": content_disposition,
                "Content-Length": str(len(file_bytes))
            }
        )
        
    except Exception as e:
        import traceback
        logger.error(f"❌ 문서 변환 실패: {str(e)}")
        logger.error(f"최상위 except 스택 트레이스:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"문서 변환 중 오류가 발생했습니다: {str(e)}"
        )
