"""
CrewAI Agents 정의

각 Agent는 특정 역할을 수행하며, CLAUDE.md의 철학에 따라
법적 판단이 아닌 문서 이해·비교·재작성·제안 역할만 수행합니다.

이제 agent.yaml 파일에서 설정을 로드합니다.
"""

from crewai import Agent
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
import os
from app.utils.agent_loader import load_agent, load_all_agents
from app.config import get_settings

SHARED_LLM = None
SHARED_CLAUDE_LLM = None

def get_llm():
    """OpenAI LLM 인스턴스 생성 (환경 변수 기반)"""
    global SHARED_LLM
    if SHARED_LLM is None:
        settings = get_settings()
        SHARED_LLM = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", settings.openai_model),
            openai_api_key=settings.openai_api_key,
            temperature=0.3
        )
    return SHARED_LLM

def get_claude_llm():
    """Claude LLM 인스턴스 생성 (환경 변수 기반)"""
    global SHARED_CLAUDE_LLM
    if SHARED_CLAUDE_LLM is None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        SHARED_CLAUDE_LLM = ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", settings.anthropic_model),
            anthropic_api_key=settings.anthropic_api_key,
            temperature=0.3
        )
    return SHARED_CLAUDE_LLM


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


def create_template_comparator_agent() -> Agent:
    """
    템플릿 비교 Agent

    역할: 최신 공고문과 기존 템플릿 비교
    책임:
    - 두 문서의 구조적 차이 분석
    - 추가/삭제/변경된 섹션 식별
    - 변경사항의 중요도 평가
    금지: 법적 판단, 어느 버전이 "올바른지" 확정
    """
    return Agent(
        role="템플릿 변경사항 분석 전문가",
        goal="최신 공고문과 기존 템플릿을 비교하여 변경사항을 정확히 식별",
        backstory="""
        당신은 입찰 공고문의 구조와 내용을 분석하는 전문가입니다.
        최신 나라장터 공고문과 우리의 템플릿을 비교하여,
        어떤 섹션이 추가되었는지, 삭제되었는지, 변경되었는지를 명확히 식별합니다.

        중요: 당신은 "어느 버전이 올바른지" 판단하지 않습니다.
        단지 두 문서의 차이점을 객관적으로 나열할 뿐입니다.
        """,
        llm=get_llm(),
        verbose=True,
        allow_delegation=False
    )
