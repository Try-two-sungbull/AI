"""
세부품명번호(품목코드) 로더

item_codes.json 파일에서 세부품명번호로 품목명을 조회합니다.
"""

import json
from pathlib import Path
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)

# item_codes.json 파일 경로
# 도커 환경과 로컬 환경 모두 지원
# __file__: app/utils/item_code_loader.py
# parent: app/utils/
# parent.parent: app/
# parent.parent.parent: 프로젝트 루트
ITEM_CODES_FILE = Path(__file__).parent.parent.parent / "item_codes.json"

# 도커 환경에서도 작동하도록 절대 경로도 시도
if not ITEM_CODES_FILE.exists():
    # 도커 컨테이너 내부 경로 (/app/item_codes.json)
    ITEM_CODES_FILE = Path("/app/item_codes.json")


class ItemCodeLoader:
    """세부품명번호 로더"""
    
    def __init__(self):
        self.item_codes: Dict[str, str] = {}
        self._load_item_codes()
    
    def _load_item_codes(self):
        """item_codes.json 파일 로드"""
        # 여러 경로 시도 (로컬 환경, 도커 환경 모두 지원)
        possible_paths = [
            ITEM_CODES_FILE,  # 상대 경로 (프로젝트 루트)
            Path("/app/item_codes.json"),  # 도커 컨테이너 절대 경로
            Path(__file__).parent.parent.parent.parent / "item_codes.json",  # 추가 시도
        ]
        
        for file_path in possible_paths:
            try:
                if file_path.exists():
                    with open(file_path, 'r', encoding='utf-8') as f:
                        self.item_codes = json.load(f)
                    logger.info(f"품목코드 로드 완료: {len(self.item_codes)}개 (경로: {file_path})")
                    return
            except Exception as e:
                logger.debug(f"경로 {file_path}에서 로드 실패: {str(e)}")
                continue
        
        # 모든 경로에서 실패
        logger.warning(f"품목코드 파일을 찾을 수 없습니다. 시도한 경로: {possible_paths}")
        self.item_codes = {}
    
    def get_item_name(self, item_code: str) -> Optional[str]:
        """
        세부품명번호로 품목명 조회
        
        Args:
            item_code: 세부품명번호 (10자리)
        
        Returns:
            품목명 또는 None
        """
        return self.item_codes.get(item_code)


# Singleton 인스턴스
_item_code_loader = None


def get_item_code_loader() -> ItemCodeLoader:
    """전역 ItemCodeLoader 인스턴스 반환"""
    global _item_code_loader
    if _item_code_loader is None:
        _item_code_loader = ItemCodeLoader()
    return _item_code_loader


def get_item_name(item_code: str) -> Optional[str]:
    """
    세부품명번호로 품목명 조회 (편의 함수)
    
    Args:
        item_code: 세부품명번호 (10자리)
    
    Returns:
        품목명 또는 None
    """
    loader = get_item_code_loader()
    return loader.get_item_name(item_code)

