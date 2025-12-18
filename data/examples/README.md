# 공고문 샘플 파일 저장소

## 📁 디렉토리 구조

```
data/examples/
├── 적격심사/
│   ├── sample_01.pdf
│   ├── sample_02.pdf
│   └── sample_03.pdf
├── 소액수의/
│   ├── sample_01.pdf
│   └── sample_02.pdf
├── 최저가낙찰/
│   ├── sample_01.pdf
│   └── sample_02.pdf
└── 협상계약/
    └── sample_01.pdf
```

## 📄 파일 준비 방법

### 1. 실제 공고문 수집

- 나라장터(G2B)에서 실제 입찰 공고문 다운로드
- 기관 내부에서 사용한 공고문
- 법적 문제 없는 샘플만 사용

### 2. 파일 형식

- **PDF 형식**만 지원 (`.pdf`)
- 텍스트가 추출 가능한 PDF (스캔 이미지만 있는 PDF는 불가)
- 파일명은 자유롭게 설정 가능

### 3. 파일 배치

각 공고 유형별 폴더에 PDF 파일을 넣으세요:

- `data/examples/적격심사/` → 적격심사 공고문 PDF들
- `data/examples/소액수의/` → 소액수의 공고문 PDF들
- `data/examples/최저가낙찰/` → 최저가낙찰 공고문 PDF들
- `data/examples/협상계약/` → 협상계약 공고문 PDF들

## 🎯 샘플 파일의 역할

이 샘플 파일들은 **Few-Shot Learning**에 사용됩니다:

1. Generator Agent가 샘플들을 학습
2. 샘플의 구조, 문체, 표현 방식을 파악
3. 새로운 공고문 생성 시 참고

## ⚠️ 주의사항

- **개인정보**: 개인정보가 포함된 샘플은 사용하지 마세요
- **법적 문제**: 실제 사용 가능한 샘플만 사용하세요
- **품질**: 잘 작성된 우수한 샘플을 사용하세요

## 📝 샘플 파일 예시

각 폴더에 최소 1개 이상의 PDF 파일을 넣어주세요.

예:
- `data/examples/적격심사/2024_적격심사_공고문_예시.pdf`
- `data/examples/소액수의/2024_소액수의_공고문_예시.pdf`

## 🔍 확인 방법

Python으로 확인:

```python
from app.tools.example_loader import get_example_loader

loader = get_example_loader()

# 적격심사 샘플 확인
examples = loader.load_examples("적격심사", max_samples=3)
print(f"적격심사 샘플 개수: {len(examples)}")

# 소액수의 샘플 확인
examples = loader.load_examples("소액수의", max_samples=3)
print(f"소액수의 샘플 개수: {len(examples)}")
```

