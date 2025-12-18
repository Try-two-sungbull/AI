"""
문서 변환 유틸리티

마크다운 형식의 공고문을 PDF, DOCX, HWP 형식으로 변환
Claude를 사용하여 마크다운을 PDF/DOCX에 최적화된 형식으로 변환
"""

from typing import Optional
import io
import re
import os
import tempfile
import subprocess
from pathlib import Path
from app.config import get_settings

try:
    import markdown
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration
except ImportError:
    markdown = None
    HTML = None
    CSS = None
    FontConfiguration = None

try:
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
except ImportError:
    Document = None


def markdown_to_pdf(markdown_content: str, output_path: Optional[str] = None) -> bytes:
    """
    마크다운을 PDF로 변환

    Args:
        markdown_content: 마크다운 형식의 텍스트
        output_path: 출력 파일 경로 (None이면 bytes 반환)

    Returns:
        PDF 파일 바이트 (output_path가 None인 경우)
    """
    if HTML is None:
        raise ImportError(
            "PDF 변환을 위해 다음 패키지가 필요합니다: "
            "pip install markdown weasyprint"
        )

    # 마크다운을 HTML로 변환
    html_content = markdown.markdown(
        markdown_content,
        extensions=['tables', 'fenced_code']
    )

    # HTML 스타일 추가 (공공문서 스타일)
    styled_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{
                size: A4;
                margin: 2cm;
            }}
            body {{
                font-family: "맑은 고딕", "Malgun Gothic", sans-serif;
                font-size: 11pt;
                line-height: 1.6;
                color: #000;
            }}
            h1 {{
                font-size: 18pt;
                font-weight: bold;
                margin-top: 20pt;
                margin-bottom: 10pt;
                text-align: center;
            }}
            h2 {{
                font-size: 14pt;
                font-weight: bold;
                margin-top: 15pt;
                margin-bottom: 8pt;
                border-bottom: 1px solid #ccc;
                padding-bottom: 3pt;
            }}
            h3 {{
                font-size: 12pt;
                font-weight: bold;
                margin-top: 10pt;
                margin-bottom: 5pt;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 10pt 0;
            }}
            th, td {{
                border: 1px solid #000;
                padding: 5pt;
                text-align: left;
            }}
            th {{
                background-color: #f0f0f0;
                font-weight: bold;
            }}
            p {{
                margin: 5pt 0;
            }}
            strong {{
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """

    # HTML을 PDF로 변환
    font_config = FontConfiguration()
    pdf_bytes = HTML(string=styled_html).write_pdf(font_config=font_config)

    if output_path:
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)
        return pdf_bytes
    else:
        return pdf_bytes


def markdown_to_docx(markdown_content: str, output_path: Optional[str] = None) -> bytes:
    """
    마크다운을 DOCX로 변환 (한글에서 열 수 있음)

    Args:
        markdown_content: 마크다운 형식의 텍스트
        output_path: 출력 파일 경로 (None이면 bytes 반환)

    Returns:
        DOCX 파일 바이트 (output_path가 None인 경우)
    """
    if Document is None:
        raise ImportError(
            "DOCX 변환을 위해 다음 패키지가 필요합니다: "
            "pip install python-docx"
        )

    # DOCX 문서 생성
    doc = Document()

    # 마크다운 파싱 (간단한 구현)
    lines = markdown_content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        # 제목 처리
        if line.startswith('# '):
            # H1
            heading = doc.add_heading(line[2:], level=1)
            heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif line.startswith('## '):
            # H2
            doc.add_heading(line[3:], level=2)
        elif line.startswith('### '):
            # H3
            doc.add_heading(line[4:], level=3)
        elif line.startswith('---'):
            # 구분선 (빈 줄로 대체)
            doc.add_paragraph('')
        elif line.startswith('|'):
            # 테이블 처리
            table_data = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                row = [cell.strip() for cell in lines[i].split('|')[1:-1]]
                if row and not all(cell.startswith('-') for cell in row):  # 헤더 구분선 제외
                    table_data.append(row)
                i += 1
            i -= 1  # 다음 반복에서 현재 줄 다시 처리

            if table_data:
                table = doc.add_table(rows=len(table_data), cols=len(table_data[0]))
                table.style = 'Light Grid Accent 1'

                for row_idx, row_data in enumerate(table_data):
                    for col_idx, cell_data in enumerate(row_data):
                        cell = table.rows[row_idx].cells[col_idx]
                        cell.text = cell_data
                        # 첫 번째 행은 헤더로 스타일링
                        if row_idx == 0:
                            for paragraph in cell.paragraphs:
                                for run in paragraph.runs:
                                    run.bold = True

        elif line.startswith('- ') or line.startswith('* '):
            # 리스트 항목
            list_text = line[2:]
            doc.add_paragraph(list_text, style='List Bullet')
        elif line.startswith('**') and line.endswith('**'):
            # 볼드 텍스트
            text = line[2:-2]
            p = doc.add_paragraph()
            run = p.add_run(text)
            run.bold = True
        else:
            # 일반 문단
            # 인라인 마크다운 처리 (간단한 구현)
            text = line
            # **볼드** 처리
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # 볼드 제거 (일단)
            # {플레이스홀더} 제거 (혹시 남아있을 경우)
            text = re.sub(r'\{[^}]+\}', '', text)
            
            if text.strip():
                doc.add_paragraph(text)

        i += 1

    # 문서 스타일 설정
    style = doc.styles['Normal']
    font = style.font
    font.name = '맑은 고딕'
    font.size = Pt(11)

    # 바이트로 변환
    doc_bytes = io.BytesIO()
    doc.save(doc_bytes)
    doc_bytes.seek(0)
    result_bytes = doc_bytes.read()

    if output_path:
        with open(output_path, 'wb') as f:
            f.write(result_bytes)
        return result_bytes
    else:
        return result_bytes


def convert_markdown_with_anthropic(
    markdown_content: str,
    output_format: str = "pdf"
) -> str:
    """
    Anthropic API를 직접 사용하여 마크다운을 PDF/DOCX에 최적화된 형식으로 변환
    
    Args:
        markdown_content: 마크다운 형식의 텍스트
        output_format: 출력 형식 ("pdf", "docx")
    
    Returns:
        변환된 HTML 또는 구조화된 텍스트
    """
    try:
        import anthropic
        settings = get_settings()
        
        if not settings.anthropic_api_key:
            print(f"⚠️ ANTHROPIC_API_KEY가 설정되지 않았습니다. 기존 라이브러리 사용")
            return None
        
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        model_name = os.getenv("ANTHROPIC_MODEL", settings.anthropic_model)
        
        format_instruction = {
            "pdf": "PDF 형식에 최적화된 완전한 HTML 문서로 변환하세요. <!DOCTYPE html><html><head><meta charset='UTF-8'><style>@page {size: A4; margin: 2cm;} body {font-family: '맑은 고딕', 'Malgun Gothic', sans-serif; font-size: 11pt; line-height: 1.6;}</style></head><body>...</body></html> 형식으로 완전한 HTML을 출력하세요.",
            "docx": "DOCX 형식에 최적화된 구조화된 마크다운으로 변환하세요. 제목, 단락, 테이블 구조를 명확히 구분하세요."
        }
        
        prompt = f"""
다음 마크다운 문서를 {output_format.upper()} 형식에 최적화된 형식으로 변환하세요.

{format_instruction.get(output_format.lower(), "")}

마크다운 내용:
```markdown
{markdown_content}
```

변환 규칙:
1. 모든 내용을 정확히 보존하세요
2. 섹션 구조를 명확히 유지하세요
3. 테이블, 리스트, 강조 표시를 올바르게 변환하세요
4. 한국어 폰트와 스타일을 고려하세요

변환된 결과만 출력하세요 (설명 없이).
"""
        
        response = client.messages.create(
            model=model_name,
            max_tokens=16000,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        # 응답 처리 (document_parser.py와 동일한 방식)
        if response.content and len(response.content) > 0:
            result_text = response.content[0].text
            if result_text and result_text.strip():
                print(f"✅ Anthropic API로 {output_format.upper()} 변환 성공 ({len(result_text)}자)")
                return result_text
            else:
                print(f"⚠️ Anthropic API 응답 텍스트가 비어있습니다. 기존 라이브러리 사용")
        else:
            print(f"⚠️ Anthropic API 응답에 content가 없습니다. 기존 라이브러리 사용")
        
        return None
        
    except Exception as e:
        print(f"⚠️ Anthropic API 변환 실패: {e}. 기존 라이브러리 사용")
        return None


def _is_html(content: str) -> bool:
    """
    내용이 HTML인지 마크다운인지 판단
    
    Args:
        content: 텍스트 내용
    
    Returns:
        HTML이면 True, 마크다운이면 False
    """
    content_stripped = content.strip()
    return (
        content_stripped.startswith("<!DOCTYPE html>") or
        content_stripped.startswith("<html>") or
        content_stripped.startswith("<HTML>") or
        ("<body>" in content_stripped.lower() and "<head>" in content_stripped.lower())
    )


def convert_document(
    content: str,
    output_format: str = "pdf",
    output_path: Optional[str] = None,
    is_html: Optional[bool] = None
) -> bytes:
    """
    문서를 지정된 형식으로 변환 (HTML 또는 마크다운 지원)
    
    HTML인 경우: convert_html_document 사용
    마크다운인 경우: 기존 로직 사용 (Claude 우선)

    Args:
        content: HTML 또는 마크다운 형식의 텍스트
        output_format: 출력 형식 ("pdf", "docx", "hwp")
        output_path: 출력 파일 경로 (None이면 bytes 반환)
        is_html: HTML 여부 (None이면 자동 감지)

    Returns:
        변환된 파일 바이트

    Raises:
        ValueError: 지원하지 않는 형식
        ImportError: 필요한 패키지가 설치되지 않음
    """
    # HTML 여부 자동 감지
    if is_html is None:
        is_html = _is_html(content)
    
    # HTML인 경우 직접 변환
    if is_html:
        return convert_html_document(content, output_format, output_path)
    
    # 마크다운인 경우 기존 로직 사용
    markdown_content = content
    # Anthropic API로 먼저 변환 시도
    anthropic_result = convert_markdown_with_anthropic(markdown_content, output_format)
    
    if anthropic_result and output_format.lower() == "pdf":
        # Anthropic이 HTML을 반환했다면, 이를 PDF로 변환
        if HTML is None:
            raise ImportError("PDF 변환을 위해 weasyprint가 필요합니다: pip install weasyprint")
        
        # Anthropic이 이미 완전한 HTML을 반환했는지 확인
        if anthropic_result.strip().startswith("<!DOCTYPE html>") or anthropic_result.strip().startswith("<html>"):
            # 이미 완전한 HTML이면 그대로 사용
            styled_html = anthropic_result
        else:
            # HTML body만 있으면 전체 HTML 구조로 감싸기
            styled_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    @page {{
                        size: A4;
                        margin: 2cm;
                    }}
                    body {{
                        font-family: "맑은 고딕", "Malgun Gothic", sans-serif;
                        font-size: 11pt;
                        line-height: 1.6;
                        color: #000;
                    }}
                </style>
            </head>
            <body>
                {anthropic_result}
            </body>
            </html>
            """
        
        font_config = FontConfiguration()
        pdf_bytes = HTML(string=styled_html).write_pdf(font_config=font_config)
        
        if output_path:
            with open(output_path, 'wb') as f:
                f.write(pdf_bytes)
        return pdf_bytes
    
    elif anthropic_result and output_format.lower() == "docx":
        # Anthropic이 구조화된 텍스트를 반환했다면, 이를 DOCX로 변환
        if Document is None:
            raise ImportError("DOCX 변환을 위해 python-docx가 필요합니다: pip install python-docx")
        
        # Anthropic 결과를 파싱하여 DOCX 생성 (기존 markdown_to_docx 로직 활용)
        return markdown_to_docx(anthropic_result, output_path)
    
    # Anthropic 변환 실패 시 기존 라이브러리 사용
    print("📝 Anthropic API 변환 실패 또는 미사용. 기존 라이브러리 사용")
    if output_format.lower() == "pdf":
        return markdown_to_pdf(markdown_content, output_path)
    elif output_format.lower() == "docx":
        return markdown_to_docx(markdown_content, output_path)
    elif output_format.lower() == "hwp":
        # HWP 변환은 HTML을 통해서만 가능
        # 마크다운을 HTML로 변환 후 HWP로 변환
        if HTML is None:
            raise ImportError("HWP 변환을 위해 weasyprint가 필요합니다: pip install weasyprint")
        
        # 마크다운을 HTML로 변환
        html_content = markdown.markdown(
            markdown_content,
            extensions=['tables', 'fenced_code']
        )
        
        # HTML 구조로 감싸기
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: "맑은 고딕", "Malgun Gothic", sans-serif;
                    font-size: 11pt;
                    line-height: 1.6;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
        
        return html_to_hwp_with_libreoffice(full_html, output_path)
    else:
        raise ValueError(f"지원하지 않는 형식: {output_format}. 'pdf' 또는 'docx'를 사용하세요.")


# 편의 함수
def export_to_file(
    markdown_content: str,
    output_format: str,
    filename: str
) -> str:
    """
    마크다운을 파일로 내보내기

    Args:
        markdown_content: 마크다운 형식의 텍스트
        output_format: 출력 형식 ("pdf", "docx")
        filename: 출력 파일명 (확장자 포함)

    Returns:
        저장된 파일 경로
    """
    output_path = Path(filename)
    convert_document(markdown_content, output_format, str(output_path))
    return str(output_path)


def _find_libreoffice() -> Optional[str]:
    """
    LibreOffice 실행 파일 경로 찾기
    
    Returns:
        LibreOffice 실행 파일 경로 또는 None
    """
    soffice_paths = [
        "/usr/bin/soffice",            # Linux (Docker)
        "/opt/homebrew/bin/soffice",  # macOS Homebrew
        "/usr/local/bin/soffice",      # macOS
        "/Applications/LibreOffice.app/Contents/MacOS/soffice"  # macOS app
    ]
    
    for path in soffice_paths:
        if os.path.exists(path):
            return path
    
    return None


def html_to_pdf(html_content: str, output_path: Optional[str] = None) -> bytes:
    """
    HTML을 PDF로 변환 (파란색 스타일 유지)
    
    Args:
        html_content: HTML 형식의 텍스트
        output_path: 출력 파일 경로 (None이면 bytes 반환)
    
    Returns:
        PDF 파일 바이트
    """
    if HTML is None:
        raise ImportError("PDF 변환을 위해 weasyprint가 필요합니다: pip install weasyprint")
    
    # HTML이 완전한 문서인지 확인
    if not html_content.strip().startswith("<!DOCTYPE html>") and not html_content.strip().startswith("<html>"):
        # HTML body만 있으면 전체 구조로 감싸기
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                @page {{
                    size: A4;
                    margin: 2cm;
                }}
                body {{
                    font-family: "맑은 고딕", "Malgun Gothic", sans-serif;
                    font-size: 11pt;
                    line-height: 1.6;
                    color: #000;
                }}
                .modified, .extracted {{
                    color: #0066CC;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
    
    font_config = FontConfiguration()
    pdf_bytes = HTML(string=html_content).write_pdf(font_config=font_config)
    
    if output_path:
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)
    
    return pdf_bytes


def html_to_docx_with_libreoffice(html_content: str, output_path: Optional[str] = None) -> bytes:
    """
    HTML을 DOCX로 변환 (LibreOffice 사용, 파란색 스타일 유지)
    
    Args:
        html_content: HTML 형식의 텍스트
        output_path: 출력 파일 경로 (None이면 bytes 반환)
    
    Returns:
        DOCX 파일 바이트
    
    Raises:
        RuntimeError: LibreOffice가 설치되지 않았거나 변환 실패
    """
    soffice_path = _find_libreoffice()
    
    if not soffice_path:
        raise RuntimeError(
            "LibreOffice가 설치되지 않았습니다. "
            "Docker 환경에서는 Dockerfile에 LibreOffice 설치가 필요합니다."
        )
    
    # HTML이 완전한 문서인지 확인
    if not html_content.strip().startswith("<!DOCTYPE html>") and not html_content.strip().startswith("<html>"):
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: "맑은 고딕", "Malgun Gothic", sans-serif;
                    font-size: 11pt;
                    line-height: 1.6;
                }}
                .modified, .extracted {{
                    color: #0066CC;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
    
    # 임시 디렉토리 생성
    with tempfile.TemporaryDirectory() as temp_dir:
        # HTML 파일 저장
        html_path = os.path.join(temp_dir, "input.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        # LibreOffice로 DOCX 변환
        try:
            result = subprocess.run(
                [
                    soffice_path,
                    "--headless",
                    "--convert-to", "docx",
                    "--outdir", temp_dir,
                    html_path
                ],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                raise RuntimeError(
                    f"HTML → DOCX 변환 실패 (exit code {result.returncode}): {result.stderr or result.stdout}"
                )
            
            # 변환된 DOCX 파일 읽기
            docx_path = os.path.join(temp_dir, "input.docx")
            if not os.path.exists(docx_path):
                raise RuntimeError(
                    f"DOCX 파일이 생성되지 않았습니다. 생성된 파일: {os.listdir(temp_dir)}"
                )
            
            with open(docx_path, "rb") as f:
                docx_content = f.read()
            
            if output_path:
                with open(output_path, 'wb') as f:
                    f.write(docx_content)
            
            print(f"✅ HTML → DOCX 변환 성공 (LibreOffice)")
            return docx_content
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("HTML → DOCX 변환 시간 초과 (60초)")
        except Exception as e:
            raise RuntimeError(f"HTML → DOCX 변환 중 오류: {str(e)}")


def html_to_hwp_with_libreoffice(html_content: str, output_path: Optional[str] = None) -> bytes:
    """
    HTML을 HWP로 변환 (LibreOffice 사용, 파란색 스타일 유지)
    
    Args:
        html_content: HTML 형식의 텍스트
        output_path: 출력 파일 경로 (None이면 bytes 반환)
    
    Returns:
        HWP 파일 바이트
    
    Raises:
        RuntimeError: LibreOffice가 설치되지 않았거나 변환 실패
    """
    soffice_path = _find_libreoffice()
    
    if not soffice_path:
        raise RuntimeError(
            "LibreOffice가 설치되지 않았습니다. "
            "Docker 환경에서는 Dockerfile에 LibreOffice 설치가 필요합니다."
        )
    
    # HTML이 완전한 문서인지 확인
    if not html_content.strip().startswith("<!DOCTYPE html>") and not html_content.strip().startswith("<html>"):
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: "맑은 고딕", "Malgun Gothic", sans-serif;
                    font-size: 11pt;
                    line-height: 1.6;
                }}
                .modified, .extracted {{
                    color: #0066CC;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
    
    # 임시 디렉토리 생성
    with tempfile.TemporaryDirectory() as temp_dir:
        # HTML 파일 저장
        html_path = os.path.join(temp_dir, "input.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        # LibreOffice로 HWP 변환
        try:
            result = subprocess.run(
                [
                    soffice_path,
                    "--headless",
                    "--convert-to", "hwp",
                    "--outdir", temp_dir,
                    html_path
                ],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                raise RuntimeError(
                    f"HTML → HWP 변환 실패 (exit code {result.returncode}): {result.stderr or result.stdout}"
                )
            
            # 변환된 HWP 파일 읽기
            hwp_path = os.path.join(temp_dir, "input.hwp")
            if not os.path.exists(hwp_path):
                raise RuntimeError(
                    f"HWP 파일이 생성되지 않았습니다. 생성된 파일: {os.listdir(temp_dir)}"
                )
            
            with open(hwp_path, "rb") as f:
                hwp_content = f.read()
            
            if output_path:
                with open(output_path, 'wb') as f:
                    f.write(hwp_content)
            
            print(f"✅ HTML → HWP 변환 성공 (LibreOffice)")
            return hwp_content
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("HTML → HWP 변환 시간 초과 (60초)")
        except Exception as e:
            raise RuntimeError(f"HTML → HWP 변환 중 오류: {str(e)}")


def mark_modified_text_in_html(html_content: str, modified_texts: list, extracted_texts: list = None) -> str:
    """
    HTML에서 수정/추출된 텍스트를 파란색으로 마킹
    
    Args:
        html_content: HTML 형식의 텍스트
        modified_texts: 수정된 텍스트 목록
        extracted_texts: 자동 추출된 텍스트 목록 (선택)
    
    Returns:
        파란색으로 마킹된 HTML
    """
    if extracted_texts is None:
        extracted_texts = []
    
    result = html_content
    
    # 수정된 텍스트를 파란색으로 마킹
    for text in modified_texts:
        if text and text.strip():
            # HTML 특수문자 이스케이프
            escaped_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            # 파란색 span으로 감싸기
            marked_text = f'<span class="modified" style="color: #0066CC;">{escaped_text}</span>'
            # 텍스트를 찾아서 교체 (대소문자 구분 없이)
            result = re.sub(
                re.escape(text),
                marked_text,
                result,
                flags=re.IGNORECASE
            )
    
    # 자동 추출된 텍스트를 파란색으로 마킹
    for text in extracted_texts:
        if text and text.strip():
            # HTML 특수문자 이스케이프
            escaped_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            # 파란색 span으로 감싸기
            marked_text = f'<span class="extracted" style="color: #0066CC;">{escaped_text}</span>'
            # 텍스트를 찾아서 교체 (대소문자 구분 없이)
            result = re.sub(
                re.escape(text),
                marked_text,
                result,
                flags=re.IGNORECASE
            )
    
    return result


def convert_html_document(
    html_content: str,
    output_format: str = "pdf",
    output_path: Optional[str] = None
) -> bytes:
    """
    HTML 문서를 지정된 형식으로 변환 (PDF, DOCX, HWP)
    
    Args:
        html_content: HTML 형식의 텍스트
        output_format: 출력 형식 ("pdf", "docx", "hwp")
        output_path: 출력 파일 경로 (None이면 bytes 반환)
    
    Returns:
        변환된 파일 바이트
    
    Raises:
        ValueError: 지원하지 않는 형식
        ImportError: 필요한 패키지가 설치되지 않음
        RuntimeError: LibreOffice 변환 실패
    """
    output_format_lower = output_format.lower()
    
    if output_format_lower == "pdf":
        return html_to_pdf(html_content, output_path)
    elif output_format_lower == "docx":
        return html_to_docx_with_libreoffice(html_content, output_path)
    elif output_format_lower == "hwp":
        return html_to_hwp_with_libreoffice(html_content, output_path)
    else:
        raise ValueError(f"지원하지 않는 형식: {output_format}. 'pdf', 'docx', 또는 'hwp'를 사용하세요.")


def hwp_to_pdf(hwp_content: bytes) -> bytes:
    """
    HWP 파일을 PDF로 변환 (LibreOffice 사용)

    Args:
        hwp_content: HWP 파일 바이트

    Returns:
        PDF 파일 바이트

    Raises:
        RuntimeError: LibreOffice가 설치되지 않았거나 변환 실패
    """
    # LibreOffice 경로 확인
    soffice_path = _find_libreoffice()
    
    if not soffice_path:
        raise RuntimeError(
            "LibreOffice가 설치되지 않았습니다. "
            "Docker 환경에서는 Dockerfile에 LibreOffice 설치가 필요합니다."
        )

    # 임시 디렉토리 생성
    with tempfile.TemporaryDirectory() as temp_dir:
        # HWP 파일 저장
        hwp_path = os.path.join(temp_dir, "input.hwp")
        with open(hwp_path, "wb") as f:
            f.write(hwp_content)

        # LibreOffice로 PDF 변환
        try:
            result = subprocess.run(
                [
                    soffice_path,
                    "--headless",
                    "--convert-to", "pdf",
                    "--outdir", temp_dir,
                    hwp_path
                ],
                capture_output=True,
                text=True,
                timeout=60  # 60초 타임아웃
            )

            # 디버깅: 출력 확인
            print(f"🔍 LibreOffice 실행 결과:")
            print(f"  Return code: {result.returncode}")
            print(f"  STDOUT: {result.stdout}")
            print(f"  STDERR: {result.stderr}")

            # 생성된 파일 목록 확인
            generated_files = os.listdir(temp_dir)
            print(f"  생성된 파일들: {generated_files}")

            if result.returncode != 0:
                raise RuntimeError(
                    f"HWP → PDF 변환 실패 (exit code {result.returncode}): {result.stderr or result.stdout}"
                )

            # 변환된 PDF 파일 읽기
            pdf_path = os.path.join(temp_dir, "input.pdf")
            if not os.path.exists(pdf_path):
                raise RuntimeError(
                    f"PDF 파일이 생성되지 않았습니다. 생성된 파일: {generated_files}"
                )

            with open(pdf_path, "rb") as f:
                pdf_content = f.read()

            return pdf_content

        except subprocess.TimeoutExpired:
            raise RuntimeError("HWP → PDF 변환 시간 초과 (60초)")
        except Exception as e:
            raise RuntimeError(f"HWP → PDF 변환 중 오류: {str(e)}")


