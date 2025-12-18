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
    문서 추출 Agent (YAML 설정 기반) - Claude 사용

    역할: 발주계획서에서 핵심 정보 추출
    책임: 문서 요약, 필드 추출 (JSON Schema 기반)
    금지: 법적 적합성 단정
    """
    return load_agent("extractor")


def create_extractor_agent_openai() -> Agent:
    """
    문서 추출 Agent (OpenAI 사용) - 미싱 정보 보완용

    역할: 발주계획서에서 핵심 정보 추출 (Claude 결과 보완)
    책임: Claude가 놓친 정보를 추가로 추출
    금지: 법적 적합성 단정
    """
    from app.utils.agent_loader import AgentConfigLoader
    loader = AgentConfigLoader()
    agent_config = loader.config.get("extractor", {})
    
    # OpenAI LLM 사용
    openai_llm = get_llm()
    
    return Agent(
        role=agent_config.get("role", "문서 정보 추출 전문가 (보완)").strip(),
        goal=agent_config.get("goal", "구매계획서에서 누락된 핵심 정보를 추가로 추출").strip(),
        backstory=(
            agent_config.get("backstory", "").strip() + 
            "\n\n당신은 Claude Extractor가 놓친 정보를 찾아내는 보완 역할을 합니다."
        ),
        llm=openai_llm,
        verbose=True,
        allow_delegation=False,
        max_iter=agent_config.get("max_iter", 3)
    )


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



def create_change_validator_agent() -> Agent:
    """
    변경사항 검증 Agent (최종 승인 Gate + Recheck 신호 생성)

    역할:
    - 비교 Agent 결과의 신뢰성 검증
    - 실질적 변경만 승인
    - 승인 불가 시 재검사 필요 여부 및 지침 제공

    ⚠️ 중요:
    - 다른 Agent를 직접 호출하지 않는다
    - 판단 결과를 구조화된 JSON으로 출력한다
    """

    return Agent(
        role="변경사항 검증 전문가 (Approval Gate + Reflection)",
        goal=(
            "비교 Agent가 보고한 변경사항이 실제로 템플릿 업데이트가 필요한지 판단하고, "
            "유의미한 변경만 승인한다. 승인할 수 없을 경우 재검사가 필요한지와 "
            "그 기준을 명확히 제시한다."
        ),
        backstory="""
당신은 템플릿 변경 승인에 대한 최종 검증자입니다.

당신의 책임은 다음과 같습니다:
1. 비교 Agent가 보고한 변경사항이
   - 이미 템플릿에 반영된 내용인지
   - 단순한 표현 차이(띄어쓰기, 어순, 동의어)인지
   - 실제 정책/법령/기준 변경인지
   를 구분하는 것입니다.

2. 승인 기준
   - 법령 조문 번호 변경
   - 금액 기준, 기간 기준 변경
   - 의무/금지/제외 조건의 의미 변화
   → 승인 대상

3. 반려 기준
   - 표현만 다른 경우
   - 의미 변화 없는 문장 정리
   - 이미 반영된 변경
   → 반려 대상

4. 재검사 판단
   - 비교 Agent가 "변경 있음"이라고 했으나 승인할 변경이 없다고 판단되면
     재검사가 필요할 수 있습니다.
   - 이 경우, 재검사 시 집중해야 할 기준을 명확히 제시하세요.

🔄 Reflection 프로토콜:
- 만약 당신의 판단 내부에 모순이 발견되면(예: 승인 불가인데 승인 변경이 있음),
  반드시 스스로 재검토 후 최종 판단을 수정하세요.
- 재검토가 발생한 경우 summary에 "(재검사 완료)"를 명시하세요.

🚫 금지:
- 다른 Agent를 호출하거나 작업을 위임하지 마세요.
- 법적 해석의 최종 결론을 내리지 마세요.

📤 출력은 반드시 아래 JSON 형식을 따르세요.
""",
        llm=get_llm(),
        verbose=True,
        allow_delegation=False,
        expected_output="""
{
  "decision": "APPROVE | REJECT",
  "summary": "판단 요약 (필요 시 '(재검사 완료)' 포함)",
  "approved_changes": [
    {
      "section": "섹션명",
      "description": "승인된 변경 요약"
    }
  ],
  "requires_recheck": true | false,
  "recheck_guideline": {
    "ignore": ["무시할 비교 기준"],
    "focus": ["집중할 비교 기준"]
  }
}
"""
    )


def create_template_comparator_agent() -> Agent:
    """
    템플릿 비교 Agent (재검사 대응 가능)
    """

    return Agent(
        role="템플릿 변경사항 분석 전문가",
        goal="최신 공고문과 기존 템플릿을 비교하여 구조적·내용적 차이를 식별",
        backstory="""
당신은 입찰 공고문 비교 전문가입니다.

당신의 역할:
- 최신 나라장터 공고문과 기존 템플릿을 비교합니다.
- 추가/삭제/변경된 섹션을 객관적으로 나열합니다.
- 변경사항의 '존재'만 보고하며, 중요성 판단은 하지 않습니다.

⚠️ 재검사 지침이 주어진 경우:
- 지침의 focus 항목을 중심으로 다시 비교하세요.
- ignore 항목에 해당하는 차이는 보고하지 마세요.

🚫 금지:
- 어느 문서가 더 올바른지 판단하지 마세요.
- 법적 적합성 결론을 내리지 마세요.
""",
        llm=get_llm(),
        verbose=True,
        allow_delegation=False
    )
