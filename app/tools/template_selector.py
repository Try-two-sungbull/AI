"""
Template Selector Tool

공고 유형에 맞는 템플릿을 선택하는 도구
"""

from pathlib import Path
from typing import Optional
from app.models.schemas import DocumentTemplate, ClassificationResult


class TemplateSelector:
    """템플릿 선택 도구"""

    def __init__(self, templates_dir: str = None):
        """
        Args:
            templates_dir: 템플릿 디렉토리 경로 (기본값: templates/)
        """
        if templates_dir is None:
            # 프로젝트 루트의 templates 디렉토리
            self.templates_dir = Path(__file__).parent.parent.parent / "templates"
        else:
            self.templates_dir = Path(templates_dir)

        # 템플릿 매핑
        self.template_mapping = {
            "적격심사": "qualification_review.md",
            "최저가낙찰": "lowest_price.md",
            "협상계약": "negotiation.md"
        }

    def select_template(
        self,
        classification_result: ClassificationResult
    ) -> DocumentTemplate:
        """
        분류 결과에 따라 적절한 템플릿 선택

        Args:
            classification_result: 공고 유형 분류 결과

        Returns:
            DocumentTemplate: 선택된 템플릿
        """
        template_type = classification_result.recommended_type
        template_filename = self.template_mapping.get(template_type)

        if template_filename is None:
            raise ValueError(f"Unknown template type: {template_type}")

        template_path = self.templates_dir / template_filename

        if not template_path.exists():
            raise FileNotFoundError(f"Template file not found: {template_path}")

        # 템플릿 파일 읽기
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 플레이스홀더 추출
        placeholders = self._extract_placeholders(content)

        return DocumentTemplate(
            template_id=f"template_{template_type}",
            template_type=template_type,
            content=content,
            placeholders=placeholders
        )

    def select_template_by_type(self, template_type: str) -> DocumentTemplate:
        """
        템플릿 유형으로 직접 선택

        Args:
            template_type: 템플릿 유형

        Returns:
            DocumentTemplate: 선택된 템플릿
        """
        from app.models.schemas import ClassificationResult

        # Dummy classification result
        dummy_classification = ClassificationResult(
            recommended_type=template_type,
            confidence=1.0,
            reason="Manual selection"
        )

        return self.select_template(dummy_classification)

    def _extract_placeholders(self, content: str) -> list:
        """
        템플릿에서 플레이스홀더 추출

        {변수} 형태의 플레이스홀더를 찾음

        Args:
            content: 템플릿 내용

        Returns:
            플레이스홀더 리스트
        """
        import re
        pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
        matches = re.findall(pattern, content)
        return list(set(matches))  # 중복 제거

    def list_available_templates(self) -> list:
        """
        사용 가능한 템플릿 목록 반환

        Returns:
            템플릿 유형 리스트
        """
        return list(self.template_mapping.keys())


# Singleton 인스턴스
_template_selector = None


def get_template_selector() -> TemplateSelector:
    """전역 TemplateSelector 인스턴스 반환"""
    global _template_selector
    if _template_selector is None:
        _template_selector = TemplateSelector()
    return _template_selector


def select_template(classification_result: ClassificationResult) -> DocumentTemplate:
    """
    템플릿 선택 편의 함수

    Args:
        classification_result: 분류 결과

    Returns:
        DocumentTemplate
    """
    selector = get_template_selector()
    return selector.select_template(classification_result)
