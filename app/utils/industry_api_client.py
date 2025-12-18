"""
공공데이터포탈 업종코드 API 클라이언트

업종코드로 법령 정보를 조회합니다.
"""

import requests
from typing import Optional, Dict
from xml.etree import ElementTree as ET
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


class IndustryAPIClient:
    """공공데이터포탈 업종코드 API 클라이언트"""
    
    def __init__(self):
        settings = get_settings()
        self.base_url = settings.data_go_kr_base_url
        self.service_key = settings.data_go_kr_service_key
        
        if not self.service_key:
            logger.warning("DATA_GO_KR_SERVICE_KEY가 설정되지 않았습니다. API 호출이 실패할 수 있습니다.")
    
    def get_industry_info(self, industry_code: str) -> Optional[Dict[str, str]]:
        """
        업종코드로 업종 정보 조회
        
        Args:
            industry_code: 업종코드 (4자리, 예: "4608", "0001")
        
        Returns:
            업종 정보 딕셔너리 또는 None
            {
                "law": "법령명",
                "section": "조항",
                "name": "업종명",
                "code": "업종코드"
            }
        """
        if not self.service_key:
            logger.error("DATA_GO_KR_SERVICE_KEY가 설정되지 않았습니다.")
            return None
        
        # 업종코드가 4자리가 아니면 패딩
        industry_code = str(industry_code).zfill(4)
        
        try:
            params = {
                "serviceKey": self.service_key,
                "pageNo": "1",
                "numOfRows": "1",
                "indstrytyCd": industry_code
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            
            # XML 파싱
            root = ET.fromstring(response.content)
            
            # resultCode 확인
            result_code = root.find(".//resultCode")
            if result_code is not None and result_code.text != "00":
                result_msg = root.find(".//resultMsg")
                logger.error(f"API 오류: {result_msg.text if result_msg is not None else 'Unknown error'}")
                return None
            
            # item 추출
            item = root.find(".//item")
            if item is None:
                logger.warning(f"업종코드 {industry_code}에 대한 정보를 찾을 수 없습니다.")
                return None
            
            # 필드 추출 (XML 응답 형식에 맞춰 파싱)
            # 예시: <baseLawordNm>건설산업기본법</baseLawordNm>
            base_laword_nm = item.find("baseLawordNm")
            base_laword_artcl_clause_nm = item.find("baseLawordArtclClauseNm")
            indstryty_nm = item.find("indstrytyNm")
            indstryty_cd = item.find("indstrytyCd")
            
            # 필수 필드 검증 (태그가 존재하고 텍스트가 있어야 함)
            if base_laword_nm is None or not (base_laword_nm.text and base_laword_nm.text.strip()):
                logger.warning(f"업종코드 {industry_code}: baseLawordNm이 누락되었습니다.")
                return None
            
            if base_laword_artcl_clause_nm is None or not (base_laword_artcl_clause_nm.text and base_laword_artcl_clause_nm.text.strip()):
                logger.warning(f"업종코드 {industry_code}: baseLawordArtclClauseNm이 누락되었습니다.")
                return None
            
            if indstryty_nm is None or not (indstryty_nm.text and indstryty_nm.text.strip()):
                logger.warning(f"업종코드 {industry_code}: indstrytyNm이 누락되었습니다.")
                return None
            
            # 업종코드는 없으면 입력값 사용
            code = indstryty_cd.text.strip() if (indstryty_cd is not None and indstryty_cd.text) else industry_code
            
            return {
                "law": base_laword_nm.text.strip(),
                "section": base_laword_artcl_clause_nm.text.strip(),
                "name": indstryty_nm.text.strip(),
                "code": code
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API 요청 실패: {str(e)}")
            return None
        except ET.ParseError as e:
            logger.error(f"XML 파싱 실패: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"업종 정보 조회 중 오류 발생: {str(e)}")
            return None
    
    def format_industry_text(self, industry_code: str) -> str:
        """
        업종코드로 형식화된 텍스트 생성
        
        예: "「고압가스안전관리법」 제4조에 의한 고압가스판매업(업종코드: 4608)"
        
        Args:
            industry_code: 업종코드
        
        Returns:
            형식화된 텍스트
        """
        info = self.get_industry_info(industry_code)
        
        if info:
            return (
                f"「{info['law']}」 {info['section']}에 의한 "
                f"{info['name']}(업종코드: {info['code']})"
            )
        else:
            # API 조회 실패 시 기본 형식
            return f"업종코드 {industry_code}에 해당하는 업종을 영위하는 자"


# Singleton 인스턴스
_industry_api_client = None


def get_industry_api_client() -> IndustryAPIClient:
    """전역 IndustryAPIClient 인스턴스 반환"""
    global _industry_api_client
    if _industry_api_client is None:
        _industry_api_client = IndustryAPIClient()
    return _industry_api_client

