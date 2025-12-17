"""
CrewAI Agents 정의

각 Agent는 특정 역할을 수행하며, CLAUDE.md의 철학에 따라
법적 판단이 아닌 문서 이해·비교·재작성·제안 역할만 수행합니다.

이제 agent.yaml 파일에서 설정을 로드합니다.
"""

from crewai import Agent
from langchain_openai import ChatOpenAI
import os
from app.utils.agent_loader import load_agent, load_all_agents

SHARED_LLM = None

def get_llm():
    """OpenAI LLM 인스턴스 생성"""
    global SHARED_LLM
    if SHARED_LLM is None:
        SHARED_LLM = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.3
        )
    return SHARED_LLM


def create_extractor_agent() -> Agent:
    """
    문서 추출 Agent (YAML 설정 기반)

    역할: 발주계획서에서 핵심 정보 추출
    책임: 문서 요약, 필드 추출 (JSON Schema 기반)
    금지: 법적 적합성 단정
    """
    return load_agent("extractor")


def create_classifier_agent() -> Agent:
    """
    공고 유형 분류 Agent (YAML 설정 기반)

    역할: 공고 유형 추천 (적격심사, 최저가 등)
    책임: 국가계약법 기준 참고하여 추천 및 신뢰도 제공
    금지: 낙찰 방식 확정 판단 (추천만 가능)
    """
    return load_agent("classifier")


def create_generator_agent() -> Agent:
    """
    공고문 생성 Agent (YAML 설정 기반)

    역할: 템플릿 기반 공고문 초안 작성
    책임: 템플릿 채우기, 사용자 커스텀 프롬프트 반영
    금지: 법적 책임 있는 최종 확정
    """
    return load_agent("generator")


def create_validator_agent() -> Agent:
    """
    법령 검증 Agent (YAML 설정 기반)

    역할: 생성된 공고문과 최신 법령 비교
    책임: 법령 개정 차이 설명, 수정 제안
    금지: 법령 해석의 최종 결론
    """
    return load_agent("validator")
