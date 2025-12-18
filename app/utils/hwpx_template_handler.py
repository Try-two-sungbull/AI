"""
HWPX 템플릿 처리 유틸리티

HWPX 템플릿 파일에서 파란색 텍스트를 추출하고 데이터로 교체하는 기능
"""

from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import io
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass
class BlueTextField:
    """파란색 텍스트 필드 정보"""
    text: str  # 원본 텍스트 (예: "[예시 공고명]")
    field_name: str  # 필드명 (예: "project_name")
    xml_path: str  # XML 내 위치 경로
    element: ET.Element  # XML 요소 참조


class HWPXTemplateHandler:
    """
    HWPX 템플릿 파일 처리
    
    - 파란색 텍스트 추출
    - 데이터로 교체
    - 수정된 HWPX 파일 저장
    """
    
    def __init__(self, template_path: Path):
        """
        Args:
            template_path: HWPX 템플릿 파일 경로
        """
        self.template_path = template_path
        self.temp_dir = None
        self.blue_text_fields: List[BlueTextField] = []
    
    def extract_blue_texts(self) -> List[BlueTextField]:
        """
        HWPX 템플릿에서 파란색 텍스트 추출
        
        Returns:
            파란색 텍스트 필드 목록
        """
        self.blue_text_fields = []
        
        # HWPX = ZIP 파일
        with zipfile.ZipFile(self.template_path, 'r') as zf:
            # Contents/section*.xml 파일들에서 텍스트 추출
            for filename in zf.namelist():
                if filename.startswith('Contents/section') and filename.endswith('.xml'):
                    xml_content = zf.read(filename)
                    self._parse_xml_for_blue_texts(xml_content, filename)
        
        return self.blue_text_fields
    
    def _parse_xml_for_blue_texts(self, xml_content: bytes, filename: str):
        """
        XML에서 파란색 텍스트 추출
        
        Args:
            xml_content: XML 파일 내용
            filename: XML 파일명
        """
        try:
            root = ET.fromstring(xml_content)
            
            # 모든 텍스트 요소 순회
            for elem in root.iter():
                # 텍스트가 있는 요소 찾기
                if elem.text and elem.text.strip():
                    # 색상 정보 확인 (파란색: RGB(0, 0, 255) 또는 유사)
                    color = self._get_text_color(elem)
                    
                    if self._is_blue_color(color):
                        # 필드명 추출 (예: "[예시 공고명]" → "project_name")
                        field_name = self._extract_field_name(elem.text)
                        
                        if field_name:
                            self.blue_text_fields.append(
                                BlueTextField(
                                    text=elem.text.strip(),
                                    field_name=field_name,
                                    xml_path=filename,
                                    element=elem
                                )
                            )
        except Exception as e:
            print(f"⚠️ XML 파싱 실패 ({filename}): {e}")
    
    def _get_text_color(self, element: ET.Element) -> Optional[Tuple[int, int, int]]:
        """
        요소의 텍스트 색상 추출
        
        Args:
            element: XML 요소
            
        Returns:
            RGB 색상 튜플 (R, G, B) 또는 None
        """
        # HWPX XML에서 색상 정보는 보통 부모 요소나 스타일에서 찾음
        # 실제 구조에 따라 수정 필요
        parent = element
        for _ in range(5):  # 최대 5단계 상위까지 검색
            if parent is None:
                break
            
            # 색상 속성 찾기 (HWPX 구조에 따라 다를 수 있음)
            color_attr = parent.get('color') or parent.get('textColor')
            if color_attr:
                return self._parse_color(color_attr)
            
            parent = parent.getparent() if hasattr(parent, 'getparent') else None
        
        return None
    
    def _parse_color(self, color_str: str) -> Optional[Tuple[int, int, int]]:
        """
        색상 문자열을 RGB 튜플로 변환
        
        Args:
            color_str: 색상 문자열 (예: "#0000FF", "rgb(0,0,255)")
        
        Returns:
            RGB 튜플
        """
        try:
            # #RRGGBB 형식
            if color_str.startswith('#'):
                r = int(color_str[1:3], 16)
                g = int(color_str[3:5], 16)
                b = int(color_str[5:7], 16)
                return (r, g, b)
            
            # rgb(r, g, b) 형식
            if color_str.startswith('rgb'):
                import re
                match = re.search(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', color_str)
                if match:
                    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except:
            pass
        
        return None
    
    def _is_blue_color(self, color: Optional[Tuple[int, int, int]]) -> bool:
        """
        색상이 파란색인지 확인
        
        Args:
            color: RGB 색상 튜플
        
        Returns:
            파란색 여부
        """
        if color is None:
            return False
        
        r, g, b = color
        
        # 파란색 판단: B가 높고, R과 G가 낮음
        # 유연한 판단: B > 200 and R < 100 and G < 100
        return b > 200 and r < 100 and g < 100
    
    def _extract_field_name(self, text: str) -> Optional[str]:
        """
        텍스트에서 필드명 추출
        
        예: "[예시 공고명]" → "project_name"
        예: "[예시 품목명]" → "item_name"
        
        Args:
            text: 파란색 텍스트
        
        Returns:
            필드명 또는 None
        """
        # 대괄호 제거
        text = text.strip().strip('[]')
        
        # 필드명 매핑 (한글 텍스트 → 키 이름)
        # TEMPLATE_FIELD_KEYS.md 참조
        field_mapping = {
            # 입찰에 부치는 사항
            "공고명": "announcement_name",
            "예시 공고명": "announcement_name",
            "용역기간": "service_period",
            "예시 용역기간": "service_period",
            "예산액": "budget_amount",
            "예시 예산액": "budget_amount",
            "구매범위": "purchase_scope",
            "전자입찰서 제출기간": "bid_submission_period",  # 시작/종료 분리 필요 시 별도 처리
            "개찰일시": "opening_datetime",
            "개찰일시 및 장소": "opening_datetime",
            "개찰장소": "opening_location",
            
            # 견적(입찰) 및 계약방식
            "계약 방법": "contract_method_detail",
            "적격심사 대상": "qualification_review_target",
            "청렴계약이행 서약제": "integrity_pledge_target",
            
            # 입찰참가자격
            "G2B 등록": "g2b_registration_requirement",
            "세부품명번호": "detail_item_code_with_name",
            "업종코드": "industry_code_with_name",
            "중소기업 제한": "sme_restriction_detail",
            "법적 결격사유": "legal_disqualification",
            "조세포탈": "tax_evasion_pledge",
            
            # 공동계약
            "공동계약": "joint_contract_status",
            "공동계약 상세": "joint_contract_details",
            
            # 예정가격 및 낙찰자 결정방법
            "예정가격 결정": "estimated_price_method",
            "낙찰자 결정": "award_decision_method",
            "동일가격 처리": "same_price_handling",
            
            # 적격심사 자료제출
            "적격심사 자료 제출": "qualification_submission_deadline",
            "적격심사 제출 방법": "qualification_submission_method",
            
            # 기타 필수 필드
            "공고일자": "announcement_date",
            "공고번호": "announcement_number",
            "담당 부서": "contact_department",
            "담당자": "contact_person",
            "담당자 전화번호": "contact_phone",
            "공고기관": "organization",
            
            # 하위 호환성 (기존 키)
            "project_name": "announcement_name",
            "item_name": "announcement_name",
            "total_budget_vat": "budget_amount",
            "contract_period": "service_period",
        }
        
        # 직접 매칭
        if text in field_mapping:
            return field_mapping[text]
        
        # 부분 매칭
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
            수정된 HWPX 파일 바이트
        """
        # HWPX 파일을 임시 디렉토리에 압축 해제
        import tempfile
        import shutil
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # ZIP 압축 해제
            with zipfile.ZipFile(self.template_path, 'r') as zf:
                zf.extractall(temp_path)
            
            # 각 XML 파일 수정
            for field in self.blue_text_fields:
                if field.field_name in data_mapping:
                    xml_file = temp_path / field.xml_path
                    
                    if xml_file.exists():
                        # XML 읽기
                        tree = ET.parse(xml_file)
                        root = tree.getroot()
                        
                        # 해당 요소 찾기 및 텍스트 교체
                        # (실제 구현은 XML 구조에 따라 다를 수 있음)
                        self._replace_text_in_xml(root, field, data_mapping[field.field_name])
                        
                        # XML 저장
                        tree.write(xml_file, encoding='utf-8', xml_declaration=True)
            
            # 다시 ZIP으로 압축
            output_bytes = io.BytesIO()
            with zipfile.ZipFile(output_bytes, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path in temp_path.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(temp_path)
                        zf.write(file_path, arcname)
            
            output_bytes.seek(0)
            return output_bytes.read()
    
    def _replace_text_in_xml(self, root: ET.Element, field: BlueTextField, new_text: str):
        """
        XML에서 특정 텍스트 교체
        
        Args:
            root: XML 루트 요소
            field: 교체할 필드 정보
            new_text: 새로운 텍스트
        """
        # 요소 찾기 및 텍스트 교체
        # (실제 구현은 XML 구조에 따라 다를 수 있음)
        for elem in root.iter():
            if elem.text == field.text:
                elem.text = str(new_text)
                break


def load_hwpx_template(template_path: Path) -> HWPXTemplateHandler:
    """
    HWPX 템플릿 로드
    
    Args:
        template_path: 템플릿 파일 경로
    
    Returns:
        HWPXTemplateHandler 인스턴스
    """
    return HWPXTemplateHandler(template_path)


def fill_hwpx_template(
    template_path: Path,
    data_mapping: Dict[str, Any],
    output_path: Optional[Path] = None
) -> bytes:
    """
    HWPX 템플릿에 데이터 채우기
    
    Args:
        template_path: 템플릿 파일 경로
        data_mapping: 필드명 → 데이터 매핑
        output_path: 출력 파일 경로 (None이면 bytes 반환)
    
    Returns:
        수정된 HWPX 파일 바이트
    """
    handler = load_hwpx_template(template_path)
    
    # 파란색 텍스트 추출
    handler.extract_blue_texts()
    
    # 텍스트 교체
    result_bytes = handler.replace_texts(data_mapping)
    
    # 파일로 저장 (옵션)
    if output_path:
        with open(output_path, 'wb') as f:
            f.write(result_bytes)
    
    return result_bytes

