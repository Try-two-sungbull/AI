"""
PDF 템플릿 처리 유틸리티

PDF 템플릿 파일에서 파란색 텍스트를 추출하고 데이터로 교체하는 기능
"""

from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import io

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


@dataclass
class BlueTextField:
    """파란색 텍스트 필드 정보"""
    text: str  # 원본 텍스트
    field_name: str  # 필드명
    page_num: int  # 페이지 번호
    bbox: tuple  # 바운딩 박스 (x0, y0, x1, y1)


class PDFTemplateHandler:
    """
    PDF 템플릿 파일 처리
    
    - 파란색 텍스트 추출
    - 데이터로 교체
    - 수정된 PDF 파일 저장
    """
    
    def __init__(self, template_path: Path):
        """
        Args:
            template_path: PDF 템플릿 파일 경로
        """
        if pdfplumber is None:
            raise ImportError(
                "PDF 템플릿 처리를 위해 pdfplumber가 필요합니다: "
                "pip install pdfplumber"
            )
        
        self.template_path = template_path
        self.blue_text_fields: List[BlueTextField] = []
    
    def extract_blue_texts(self) -> List[BlueTextField]:
        """
        PDF 템플릿에서 파란색 텍스트 추출
        
        Returns:
            파란색 텍스트 필드 목록
        """
        self.blue_text_fields = []
        
        with pdfplumber.open(self.template_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # 텍스트와 색상 정보 추출
                words = page.extract_words()
                
                for word in words:
                    # 색상 정보 확인 (pdfplumber는 색상 정보를 직접 제공하지 않을 수 있음)
                    # 대안: 텍스트 패턴으로 필드 식별
                    field_name = self._extract_field_name(word['text'])
                    
                    if field_name:
                        self.blue_text_fields.append(
                            BlueTextField(
                                text=word['text'],
                                field_name=field_name,
                                page_num=page_num,
                                bbox=(word['x0'], word['top'], word['x1'], word['bottom'])
                            )
                        )
        
        return self.blue_text_fields
    
    def _extract_field_name(self, text: str) -> Optional[str]:
        """
        텍스트에서 필드명 추출
        
        Args:
            text: 텍스트
        
        Returns:
            필드명 또는 None
        """
        text = text.strip().strip('[]')
        
        field_mapping = {
            "예시 공고명": "project_name",
            "공고명": "project_name",
            "예시 품목명": "item_name",
            "품목명": "item_name",
            "예시 예산": "total_budget_vat",
            "예산": "total_budget_vat",
            "예시 계약기간": "contract_period",
            "계약기간": "contract_period",
        }
        
        if text in field_mapping:
            return field_mapping[text]
        
        for key, value in field_mapping.items():
            if key in text:
                return value
        
        return None
    
    def replace_texts(self, data_mapping: Dict[str, Any]) -> bytes:
        """
        파란색 텍스트를 실제 데이터로 교체
        
        Args:
            data_mapping: 필드명 → 데이터 매핑
        
        Returns:
            수정된 PDF 파일 바이트
        
        Note:
            PDF는 텍스트 직접 수정이 어려우므로,
            PyPDF2나 reportlab을 사용하여 새 PDF 생성 필요
        """
        # PDF 텍스트 교체는 복잡하므로,
        # 여기서는 기본 구조만 제공
        # 실제 구현은 PyPDF2 또는 reportlab 사용 권장
        
        from pypdf import PdfReader, PdfWriter
        
        reader = PdfReader(self.template_path)
        writer = PdfWriter()
        
        # 페이지별로 처리
        for page_num, page in enumerate(reader.pages):
            # 텍스트 교체 로직 (복잡함)
            # 실제 구현 필요
            writer.add_page(page)
        
        # 바이트로 변환
        output_bytes = io.BytesIO()
        writer.write(output_bytes)
        output_bytes.seek(0)
        
        return output_bytes.read()


def load_pdf_template(template_path: Path) -> PDFTemplateHandler:
    """
    PDF 템플릿 로드
    
    Args:
        template_path: 템플릿 파일 경로
    
    Returns:
        PDFTemplateHandler 인스턴스
    """
    return PDFTemplateHandler(template_path)


def fill_pdf_template(
    template_path: Path,
    data_mapping: Dict[str, Any],
    output_path: Optional[Path] = None
) -> bytes:
    """
    PDF 템플릿에 데이터 채우기
    
    Args:
        template_path: 템플릿 파일 경로
        data_mapping: 필드명 → 데이터 매핑
        output_path: 출력 파일 경로 (None이면 bytes 반환)
    
    Returns:
        수정된 PDF 파일 바이트
    """
    handler = load_pdf_template(template_path)
    
    # 파란색 텍스트 추출
    handler.extract_blue_texts()
    
    # 텍스트 교체
    result_bytes = handler.replace_texts(data_mapping)
    
    # 파일로 저장 (옵션)
    if output_path:
        with open(output_path, 'wb') as f:
            f.write(result_bytes)
    
    return result_bytes

