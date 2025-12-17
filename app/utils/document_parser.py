"""
문서 파싱 유틸리티

PDF, DOCX, HWP 지원
- HWP 5.0 이전 버전 (OLE 기반)
- HWP 5.0+ 버전 (ZIP 기반)
"""

from pypdf import PdfReader
from docx import Document
import olefile
import io
import struct
from typing import Union
import chardet


def decode_text_with_fallback(data: bytes) -> str:
    """
    다양한 인코딩을 시도하여 텍스트 디코딩

    Args:
        data: 바이트 데이터

    Returns:
        디코딩된 텍스트
    """
    # 1. chardet으로 인코딩 감지
    try:
        detected = chardet.detect(data)
        if detected['encoding'] and detected['confidence'] > 0.7:
            return data.decode(detected['encoding'], errors='replace')
    except:
        pass

    # 2. 일반적인 인코딩 순차 시도
    encodings = [
        'utf-8',
        'cp949',  # 한국어 Windows
        'euc-kr',  # 한국어 Unix/Linux
        'utf-16',
        'utf-16le',
        'utf-16be',
        'latin-1'  # 최후의 수단 (거의 모든 바이트 시퀀스 허용)
    ]

    for encoding in encodings:
        try:
            decoded = data.decode(encoding)
            # 유효한 텍스트인지 간단히 확인
            if len(decoded.strip()) > 0:
                return decoded
        except (UnicodeDecodeError, LookupError):
            continue

    # 3. 최종 폴백: replace 모드로 UTF-8 디코딩
    return data.decode('utf-8', errors='replace')


def parse_document(file_content: bytes, filename: str) -> str:
    """
    업로드된 문서에서 텍스트 추출

    Args:
        file_content: 파일 바이트 내용
        filename: 파일 이름

    Returns:
        추출된 텍스트

    Raises:
        ValueError: 지원하지 않는 파일 형식
    """
    file_extension = filename.lower().split('.')[-1]

    if file_extension == 'pdf':
        return parse_pdf(file_content)
    elif file_extension in ['docx', 'doc']:
        return parse_docx(file_content)
    elif file_extension == 'hwp':
        return parse_hwp(file_content)
    elif file_extension == 'txt':
        return decode_text_with_fallback(file_content)
    else:
        raise ValueError(f"지원하지 않는 파일 형식: {file_extension}")


def parse_pdf(file_content: bytes) -> str:
    """
    PDF 파일에서 텍스트 추출

    Args:
        file_content: PDF 파일 바이트

    Returns:
        추출된 텍스트
    """
    try:
        pdf_file = io.BytesIO(file_content)
        reader = PdfReader(pdf_file)

        text_parts = []
        for page in reader.pages:
            try:
                text = page.extract_text()
                if text:
                    # PDF 추출 텍스트에 인코딩 문제가 있을 수 있음
                    # 깨진 문자 정리
                    cleaned_text = text.encode('utf-8', errors='ignore').decode('utf-8')
                    if cleaned_text.strip():
                        text_parts.append(cleaned_text)
            except Exception as page_error:
                # 개별 페이지 오류는 무시하고 계속
                continue

        full_text = '\n\n'.join(text_parts)

        if not full_text.strip():
            raise ValueError("PDF에서 텍스트를 추출할 수 없습니다")

        return clean_text(full_text)

    except Exception as e:
        raise ValueError(f"PDF 파싱 실패: {str(e)}")


def parse_docx(file_content: bytes) -> str:
    """
    DOCX 파일에서 텍스트 추출

    Args:
        file_content: DOCX 파일 바이트

    Returns:
        추출된 텍스트
    """
    try:
        docx_file = io.BytesIO(file_content)
        doc = Document(docx_file)

        text_parts = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text_parts.append(paragraph.text)

        # 표(table)에서도 텍스트 추출
        for table in doc.tables:
            for row in table.rows:
                row_text = ' | '.join(cell.text.strip() for cell in row.cells)
                if row_text.strip():
                    text_parts.append(row_text)

        full_text = '\n'.join(text_parts)

        if not full_text.strip():
            raise ValueError("DOCX에서 텍스트를 추출할 수 없습니다")

        return clean_text(full_text)

    except Exception as e:
        raise ValueError(f"DOCX 파싱 실패: {str(e)}")


def parse_hwp(file_content: bytes) -> str:
    """
    HWP 파일에서 텍스트 추출

    HWP 5.0 이전 버전(OLE 기반) 및 5.0+ 버전 지원

    Args:
        file_content: HWP 파일 바이트

    Returns:
        추출된 텍스트
    """
    try:
        hwp_file = io.BytesIO(file_content)

        # HWP 5.0+ (ZIP 기반) 확인
        if file_content[:2] == b'PK':
            return parse_hwp_50_plus(file_content)

        # HWP 5.0 이전 버전 (OLE 기반)
        if not olefile.isOleFile(hwp_file):
            raise ValueError("지원하지 않는 HWP 파일 형식입니다")

        ole = olefile.OleFileIO(hwp_file)

        # HWP 파일의 텍스트 스트림 찾기
        text_parts = []

        # BodyText 섹션에서 텍스트 추출
        for dir_entry in ole.listdir():
            if 'BodyText' in dir_entry or 'Section' in str(dir_entry):
                try:
                    stream = ole.openstream(dir_entry)
                    data = stream.read()

                    # 간단한 텍스트 추출 (HWP 구조는 복잡하므로 기본적인 추출만)
                    # 다양한 인코딩 시도
                    try:
                        decoded_text = decode_text_with_fallback(data)
                        # 제어 문자 제거
                        cleaned = ''.join(char for char in decoded_text if char.isprintable() or char in ['\n', '\r', '\t'])
                        if cleaned.strip():
                            text_parts.append(cleaned)
                    except:
                        pass
                except:
                    continue

        ole.close()

        full_text = '\n'.join(text_parts)

        if not full_text.strip():
            raise ValueError(
                "HWP 파일에서 텍스트를 추출할 수 없습니다. "
                "PDF로 변환 후 업로드를 권장합니다."
            )

        return clean_text(full_text)

    except Exception as e:
        raise ValueError(f"HWP 파싱 실패: {str(e)}")


def parse_hwp_50_plus(file_content: bytes) -> str:
    """
    HWP 5.0+ (ZIP 기반) 파일에서 텍스트 추출

    Args:
        file_content: HWP 파일 바이트

    Returns:
        추출된 텍스트
    """
    import zipfile
    import xml.etree.ElementTree as ET

    try:
        hwp_file = io.BytesIO(file_content)
        with zipfile.ZipFile(hwp_file, 'r') as zf:
            text_parts = []

            # section*.xml 파일들에서 텍스트 추출
            for filename in zf.namelist():
                if filename.startswith('Contents/section') and filename.endswith('.xml'):
                    xml_content = zf.read(filename)

                    try:
                        root = ET.fromstring(xml_content)
                        # t 태그에서 텍스트 추출
                        for elem in root.iter():
                            if elem.text and elem.text.strip():
                                text_parts.append(elem.text.strip())
                    except:
                        pass

            full_text = '\n'.join(text_parts)

            if not full_text.strip():
                raise ValueError("HWP 5.0+ 파일에서 텍스트를 추출할 수 없습니다")

            return clean_text(full_text)

    except Exception as e:
        raise ValueError(f"HWP 5.0+ 파싱 실패: {str(e)}")


def clean_text(text: str) -> str:
    """
    추출된 텍스트 정리

    - 과도한 공백 제거
    - 줄바꿈 정리
    - 깨진 문자 제거

    Args:
        text: 원본 텍스트

    Returns:
        정리된 텍스트
    """
    import re

    # 유니코드 정규화 (NFC)
    import unicodedata
    text = unicodedata.normalize('NFC', text)

    # 제어 문자 제거 (줄바꿈, 탭 제외)
    text = ''.join(char for char in text if char.isprintable() or char in ['\n', '\r', '\t', ' '])

    # 연속된 공백을 하나로 (단, 줄바꿈은 유지)
    lines = text.split('\n')
    cleaned_lines = [' '.join(line.split()) for line in lines]
    text = '\n'.join(cleaned_lines)

    # 연속된 줄바꿈을 최대 2개로 제한
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()
