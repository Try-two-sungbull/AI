"""
Web Search Tool

최신 공고문 및 법령 정보를 웹에서 검색하는 도구
"""

import requests
from typing import List, Dict, Any, Optional
import os
from datetime import datetime


class WebSearchTool:
    """
    웹 검색 도구

    주요 대상:
    - 나라장터 (www.g2b.go.kr): 최신 공고문
    - 국가법령정보센터 (www.law.go.kr): 법령 정보
    """

    def __init__(self):
        self.g2b_api_key = os.getenv("G2B_API_KEY", "")
        self.law_api_key = os.getenv("LAW_API_KEY", "")

    def search_recent_announcements(
        self,
        procurement_type: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        최신 공고문 검색

        Args:
            procurement_type: 조달 유형 (용역/공사/물품)
            limit: 최대 결과 수

        Returns:
            공고문 목록
        """
        # 실제 구현 시 나라장터 API 호출
        # 현재는 Mock 데이터 반환

        mock_data = [
            {
                "announcement_id": "20250001",
                "title": f"{procurement_type} 공고 샘플 1",
                "organization": "국토교통부",
                "amount": 150000000,
                "method": "적격심사",
                "published_date": "2025-01-15",
                "url": "https://www.g2b.go.kr/example1"
            },
            {
                "announcement_id": "20250002",
                "title": f"{procurement_type} 공고 샘플 2",
                "organization": "환경부",
                "amount": 80000000,
                "method": "최저가낙찰",
                "published_date": "2025-01-14",
                "url": "https://www.g2b.go.kr/example2"
            }
        ]

        return mock_data[:limit]

    def search_law_references(
        self,
        law_name: str = "국가계약법",
        section: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        법령 정보 검색

        Args:
            law_name: 법령명
            section: 조항 (선택사항)

        Returns:
            법령 정보
        """
        # 실제 구현 시 국가법령정보센터 API 호출
        # 현재는 Mock 데이터 반환

        mock_law = {
            "law_name": law_name,
            "law_id": "001234",
            "last_updated": "2024-12-01",
            "sections": [
                {
                    "section": "제26조",
                    "title": "수의계약에 의할 수 있는 경우",
                    "content": "계약담당공무원은 다음 각 호의 어느 하나에 해당하는 경우에는 수의계약에 의할 수 있다..."
                },
                {
                    "section": "제27조",
                    "title": "낙찰자의 결정",
                    "content": "낙찰자는 예정가격 이하로서 최저가격으로 입찰한 자로 한다..."
                }
            ],
            "url": "https://www.law.go.kr/example"
        }

        if section:
            # 특정 조항 필터링
            mock_law["sections"] = [
                s for s in mock_law["sections"]
                if s["section"] == section
            ]

        return mock_law

    def search_similar_documents(
        self,
        keywords: List[str],
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """
        키워드로 유사 공고문 검색

        Args:
            keywords: 검색 키워드 목록
            limit: 최대 결과 수

        Returns:
            유사 공고문 목록
        """
        # Mock 구현
        results = []
        for i, keyword in enumerate(keywords[:limit]):
            results.append({
                "title": f"{keyword} 관련 공고문",
                "organization": "샘플 기관",
                "published_date": "2025-01-10",
                "similarity_score": 0.85 - (i * 0.1),
                "url": f"https://www.g2b.go.kr/doc{i+1}"
            })

        return results


class LawDatabaseSearchTool:
    """
    국가법령정보센터 API 검색 도구

    국가법령정보센터 Open API를 활용한 법령 검색
    """

    def __init__(self):
        self.api_key = os.getenv("LAW_API_KEY", "")
        self.base_url = "https://www.law.go.kr/DRF/lawSearch.do"

    def search_law(
        self,
        law_name: str,
        query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        법령 검색

        Args:
            law_name: 법령명
            query: 검색어 (선택사항)

        Returns:
            법령 검색 결과
        """
        # 실제 API 호출 구현
        if not self.api_key:
            # API Key가 없으면 Mock 데이터 반환
            return self._get_mock_law_data(law_name)

        try:
            params = {
                "OC": self.api_key,
                "target": "law",
                "type": "XML",
                "query": query or law_name
            }

            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()

            # XML 파싱 및 데이터 추출 (실제 구현 필요)
            # 현재는 Mock 데이터 반환
            return self._get_mock_law_data(law_name)

        except Exception as e:
            print(f"Law API Error: {e}")
            return self._get_mock_law_data(law_name)

    def get_law_content(self, law_id: str) -> Dict[str, Any]:
        """
        법령 상세 내용 조회

        Args:
            law_id: 법령 ID

        Returns:
            법령 상세 정보
        """
        # Mock 구현
        return {
            "law_id": law_id,
            "law_name": "국가계약법",
            "content": "제1조 (목적) 이 법은 국가를 당사자로 하는 계약에 관한 기본적인 사항을 정함으로써...",
            "last_updated": "2024-12-01"
        }

    def _get_mock_law_data(self, law_name: str) -> Dict[str, Any]:
        """Mock 법령 데이터 반환"""
        return {
            "law_name": law_name,
            "law_id": "00123",
            "enacted_date": "1995-01-05",
            "last_updated": "2024-12-01",
            "sections": [
                {
                    "section": "제26조",
                    "title": "수의계약",
                    "content": "계약담당공무원은 경쟁에 부칠 여유가 없거나 경쟁에 부치는 것이 불리하다고 인정될 때에는 수의계약에 의할 수 있다."
                },
                {
                    "section": "제27조",
                    "title": "낙찰자 결정",
                    "content": "낙찰자는 예정가격 이하로서 최저가격으로 입찰한 자로 한다. 다만, 대통령령으로 정하는 경우에는 적격심사를 거쳐 낙찰자를 결정할 수 있다."
                }
            ],
            "url": f"https://www.law.go.kr/법령/{law_name}"
        }


# Singleton 인스턴스
_web_search = None
_law_search = None


def get_web_search() -> WebSearchTool:
    """전역 WebSearchTool 인스턴스 반환"""
    global _web_search
    if _web_search is None:
        _web_search = WebSearchTool()
    return _web_search


def get_law_search() -> LawDatabaseSearchTool:
    """전역 LawDatabaseSearchTool 인스턴스 반환"""
    global _law_search
    if _law_search is None:
        _law_search = LawDatabaseSearchTool()
    return _law_search
