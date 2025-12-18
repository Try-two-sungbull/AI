"""
문서 변환 유틸리티

마크다운 형식의 공고문을 PDF, DOCX, HWP 형식으로 변환
"""

from typing import Optional
import io
import re
from pathlib import Path

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


def convert_document(
    markdown_content: str,
    output_format: str = "pdf",
    output_path: Optional[str] = None
) -> bytes:
    """
    마크다운 문서를 지정된 형식으로 변환

    Args:
        markdown_content: 마크다운 형식의 텍스트
        output_format: 출력 형식 ("pdf", "docx", "hwp")
        output_path: 출력 파일 경로 (None이면 bytes 반환)

    Returns:
        변환된 파일 바이트

    Raises:
        ValueError: 지원하지 않는 형식
        ImportError: 필요한 패키지가 설치되지 않음
    """
    if output_format.lower() == "pdf":
        return markdown_to_pdf(markdown_content, output_path)
    elif output_format.lower() == "docx":
        return markdown_to_docx(markdown_content, output_path)
    elif output_format.lower() == "hwp":
        # HWP는 복잡하므로 DOCX로 변환 후 사용자가 한글에서 열도록 안내
        # 또는 향후 pyhwp 라이브러리 사용 고려
        raise NotImplementedError(
            "HWP 변환은 아직 지원되지 않습니다. "
            "DOCX 형식으로 변환 후 한글에서 열 수 있습니다."
        )
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

