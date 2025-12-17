"""
Example Loader Tool

실제 공고문 샘플을 로드하여 Few-Shot Learning에 활용
"""

from pathlib import Path
from typing import List, Optional
import random


class ExampleLoader:
    """
    실제 공고문 샘플을 로드하는 도구

    Few-Shot Learning을 위해 공고 유형별 실제 예시를 제공합니다.
    """

    def __init__(self, examples_dir: str = None):
        """
        Args:
            examples_dir: 샘플 디렉토리 경로 (기본값: data/examples/)
        """
        if examples_dir is None:
            # 프로젝트 루트의 data/examples 디렉토리
            self.examples_dir = Path(__file__).parent.parent.parent / "data" / "examples"
        else:
            self.examples_dir = Path(examples_dir)

        # 공고 유형별 디렉토리 매핑
        self.type_mapping = {
            "적격심사": "적격심사",
            "소액수의": "소액수의",
            "최저가낙찰": "최저가낙찰",
            "협상계약": "협상계약"
        }

    def load_examples(
        self,
        announcement_type: str,
        max_samples: int = 3
    ) -> List[str]:
        """
        특정 공고 유형의 샘플들을 로드 (PDF 지원)

        Args:
            announcement_type: 공고 유형 (적격심사, 최저가낙찰, 협상계약)
            max_samples: 최대 샘플 개수 (기본값: 3)

        Returns:
            샘플 공고문 리스트
        """
        type_dir = self.type_mapping.get(announcement_type)
        if type_dir is None:
            return []

        example_path = self.examples_dir / type_dir

        if not example_path.exists():
            return []

        # PDF 파일만 읽기
        sample_files = list(example_path.glob("*.pdf"))

        if not sample_files:
            return []

        # 무작위로 max_samples 개 선택
        selected_files = random.sample(
            sample_files,
            min(len(sample_files), max_samples)
        )

        examples = []
        for file_path in selected_files:
            content = self._read_pdf(file_path)
            if content:
                examples.append(content)

        return examples

    def _read_pdf(self, file_path: Path) -> Optional[str]:
        """
        PDF 파일을 읽어서 텍스트로 반환

        Args:
            file_path: PDF 파일 경로

        Returns:
            파일 내용 (텍스트)
        """
        try:
            # document_parser 재사용
            from app.utils.document_parser import parse_document
            with open(file_path, 'rb') as f:
                content = f.read()
            return parse_document(content, file_path.name)

        except Exception as e:
            print(f"PDF 읽기 실패: {file_path} - {e}")
            return None

    def create_few_shot_prompt(
        self,
        announcement_type: str,
        extracted_data: dict,
        template: str,
        max_samples: int = 2
    ) -> str:
        """
        Few-Shot Learning을 위한 프롬프트 생성

        Args:
            announcement_type: 공고 유형
            extracted_data: 추출된 데이터
            template: 템플릿 내용
            max_samples: 참고할 샘플 개수

        Returns:
            Few-Shot 프롬프트
        """
        examples = self.load_examples(announcement_type, max_samples)

        prompt_parts = [
            f"# 입찰 공고문 작성 작업",
            f"",
            f"## 공고 유형",
            f"{announcement_type}",
            f"",
        ]

        # 실제 샘플 추가
        if examples:
            prompt_parts.append("## 실제 공고문 예시")
            prompt_parts.append("")
            prompt_parts.append("다음은 실제로 작성된 우수한 공고문 샘플입니다. 이 샘플들의 문체, 구조, 표현 방식을 참고하세요.")
            prompt_parts.append("")

            for i, example in enumerate(examples, 1):
                prompt_parts.append(f"### 샘플 {i}")
                prompt_parts.append("```")
                prompt_parts.append(example)
                prompt_parts.append("```")
                prompt_parts.append("")

        # 템플릿 추가
        prompt_parts.extend([
            "## 템플릿",
            "",
            "다음 템플릿을 기반으로 작성하되, 위 샘플들의 표현 방식을 참고하여 자연스럽게 작성하세요.",
            "",
            "```",
            template,
            "```",
            "",
        ])

        # 추출 데이터 추가
        prompt_parts.extend([
            "## 추출된 데이터",
            "",
            "다음 데이터를 템플릿에 적절히 채워 넣으세요:",
            "",
            "```json",
        ])

        import json
        prompt_parts.append(json.dumps(extracted_data, ensure_ascii=False, indent=2))
        prompt_parts.extend([
            "```",
            "",
        ])

        # 작성 지침
        prompt_parts.extend([
            "## 작성 지침",
            "",
            "1. **샘플 참고**: 위 실제 공고문 샘플들의 문체와 표현 방식을 참고하세요",
            "2. **템플릿 준수**: 템플릿의 구조를 유지하세요",
            "3. **데이터 활용**: 추출된 데이터를 정확히 반영하세요",
            "4. **법령 준수**: 국가계약법 및 관련 법령에 부합하는 표현을 사용하세요",
            "5. **자연스러운 표현**: 기계적이지 않고 자연스러운 문장으로 작성하세요",
            "",
            "## 주의사항 (CLAUDE.md 철학)",
            "",
            "- 법적 판단이나 확정적 결론을 내리지 마세요",
            "- 추천이나 제안 수준으로만 표현하세요",
            "- 불확실한 부분은 \"별도 확인 필요\" 등으로 표시하세요",
            "",
        ])

        return "\n".join(prompt_parts)

    def save_example(
        self,
        announcement_type: str,
        content: str,
        filename: Optional[str] = None
    ) -> Path:
        """
        새로운 샘플을 저장

        Args:
            announcement_type: 공고 유형
            content: 공고문 내용
            filename: 파일명 (기본값: 자동 생성)

        Returns:
            저장된 파일 경로
        """
        type_dir = self.type_mapping.get(announcement_type)
        if type_dir is None:
            raise ValueError(f"Unknown announcement type: {announcement_type}")

        example_path = self.examples_dir / type_dir
        example_path.mkdir(parents=True, exist_ok=True)

        # 파일명 생성
        if filename is None:
            existing_files = list(example_path.glob("sample_*.md"))
            next_num = len(existing_files) + 1
            filename = f"sample_{next_num:02d}.md"

        file_path = example_path / filename

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return file_path

    def list_examples(self, announcement_type: str) -> List[Path]:
        """
        특정 유형의 모든 샘플 파일 목록 반환

        Args:
            announcement_type: 공고 유형

        Returns:
            샘플 파일 경로 리스트
        """
        type_dir = self.type_mapping.get(announcement_type)
        if type_dir is None:
            return []

        example_path = self.examples_dir / type_dir

        if not example_path.exists():
            return []

        return list(example_path.glob("*.md"))


# Singleton 인스턴스
_example_loader = None


def get_example_loader() -> ExampleLoader:
    """전역 ExampleLoader 인스턴스 반환"""
    global _example_loader
    if _example_loader is None:
        _example_loader = ExampleLoader()
    return _example_loader


def create_few_shot_prompt(
    announcement_type: str,
    extracted_data: dict,
    template: str,
    max_samples: int = 2
) -> str:
    """
    Few-Shot 프롬프트 생성 편의 함수

    Args:
        announcement_type: 공고 유형
        extracted_data: 추출된 데이터
        template: 템플릿 내용
        max_samples: 샘플 개수

    Returns:
        Few-Shot 프롬프트
    """
    loader = get_example_loader()
    return loader.create_few_shot_prompt(
        announcement_type,
        extracted_data,
        template,
        max_samples
    )
