"""
템플릿 로더

JSON 파일 또는 DB에서 템플릿을 로드합니다.
"""

import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from app.models.template import BiddingTemplate


class TemplateLoader:
    """
    템플릿 로더

    - JSON 파일에서 템플릿 로드
    - 향후 DB 연동 가능
    """

    def __init__(self, templates_dir: str = "data/templates"):
        self.templates_dir = Path(templates_dir)
        self._cache: Dict[str, BiddingTemplate] = {}

    def load_template(self, template_id: str) -> Optional[BiddingTemplate]:
        """
        템플릿 ID로 템플릿 로드

        Args:
            template_id: 템플릿 고유 ID (예: "qualified_bid_v1")

        Returns:
            BiddingTemplate 객체 또는 None
        """
        # 캐시 확인
        if template_id in self._cache:
            return self._cache[template_id]

        # 파일에서 로드
        template_file = self.templates_dir / f"{template_id}.json"

        if not template_file.exists():
            # ID를 파일명으로 직접 찾기
            for file in self.templates_dir.glob("*.json"):
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if data.get("template_id") == template_id:
                            template = BiddingTemplate(**data)
                            self._cache[template_id] = template
                            return template
                except Exception:
                    continue
            return None

        try:
            with open(template_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                template = BiddingTemplate(**data)
                self._cache[template_id] = template
                return template
        except Exception as e:
            print(f"템플릿 로드 실패: {template_id} - {e}")
            return None

    def load_template_by_type(self, announcement_type: str) -> Optional[BiddingTemplate]:
        """
        공고 유형으로 템플릿 조회

        Args:
            announcement_type: 공고 유형 (lowest_price, qualified_bid 등)

        Returns:
            해당 유형의 템플릿 (active=True인 것 우선)
        """
        for file in self.templates_dir.glob("*.json"):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if (data.get("announcement_type") == announcement_type and
                        data.get("is_active", True)):
                        template = BiddingTemplate(**data)
                        self._cache[template.template_id] = template
                        return template
            except Exception:
                continue

        return None

    def list_templates(self) -> List[Dict[str, Any]]:
        """
        사용 가능한 모든 템플릿 목록

        Returns:
            템플릿 메타데이터 리스트
        """
        templates = []

        for file in self.templates_dir.glob("*.json"):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    templates.append({
                        "template_id": data.get("template_id"),
                        "template_name": data.get("template_name"),
                        "announcement_type": data.get("announcement_type"),
                        "description": data.get("description"),
                        "version": data.get("version"),
                        "is_active": data.get("is_active", True)
                    })
            except Exception:
                continue

        return templates

    def get_default_template(self) -> BiddingTemplate:
        """
        기본 템플릿 반환

        Returns:
            적격심사 템플릿 (기본값)
        """
        template = self.load_template("qualified_bid_v1")
        if not template:
            raise ValueError("기본 템플릿(qualified_bid_v1)을 찾을 수 없습니다")
        return template


# 싱글톤 인스턴스
_loader_instance: Optional[TemplateLoader] = None


def get_template_loader() -> TemplateLoader:
    """
    TemplateLoader 싱글톤 인스턴스 반환
    """
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = TemplateLoader()
    return _loader_instance
