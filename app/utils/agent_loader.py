"""
YAML 파일에서 Agent 설정을 로드하는 유틸리티

agent.yaml 파일을 읽어서 CrewAI Agent 객체를 생성합니다.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List
from crewai import Agent
from langchain_openai import ChatOpenAI
import os


class AgentConfigLoader:
    """Agent 설정을 YAML에서 로드하는 클래스"""

    def __init__(self, config_path: str = None):
        """
        Args:
            config_path: agent.yaml 파일 경로 (기본값: app/agent.yaml)
        """
        if config_path is None:
            # 기본 경로: app/agent.yaml
            config_path = Path(__file__).parent.parent / "agent.yaml"

        self.config_path = Path(config_path)
        self.config = self._load_config()
        # LLM은 Agent별로 동적으로 생성하므로 여기서는 생성하지 않음

    def _load_config(self) -> Dict[str, Any]:
        """YAML 파일 로드"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Agent config file not found: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _get_llm(self, agent_name: str = None):
        """
        Agent별 LLM 인스턴스 생성
        
        멀티 에이전트 아키텍처:
        - Claude (Anthropic): Extractor, Generator (해석/생성)
        - OpenAI: Classifier, Validator (검증/감사)
        
        Args:
            agent_name: agent 이름 (extractor, classifier, generator, validator)
        """
        from app.config import get_settings
        from langchain_anthropic import ChatAnthropic
        settings = get_settings()
        
        # Claude를 사용하는 Agent들
        claude_agents = ["extractor", "generator"]
        
        # OpenAI를 사용하는 Agent들
        openai_agents = ["classifier", "validator"]
        
        if agent_name in claude_agents:
            # Claude 사용 (Extractor, Generator)
            if not settings.anthropic_api_key:
                print(f"⚠️ ANTHROPIC_API_KEY가 설정되지 않아 OpenAI를 사용합니다.")
                return ChatOpenAI(
                    model=os.getenv("OPENAI_MODEL", settings.openai_model),
                    openai_api_key=settings.openai_api_key,
                    temperature=0.3
                )
            return ChatAnthropic(
                model=os.getenv("ANTHROPIC_MODEL", settings.anthropic_model),
                anthropic_api_key=settings.anthropic_api_key,
                temperature=0.3,
                max_tokens=8192  # 긴 문서 생성 시 충분한 토큰 할당
            )
        elif agent_name == "validator":
            # Validator는 별도 OpenAI 모델 사용 가능
            validator_model = os.getenv("OPENAI_MODEL_VALIDATOR", getattr(settings, 'openai_model_validator', settings.openai_model))
            return ChatOpenAI(
                model=validator_model,
                openai_api_key=settings.openai_api_key,
                temperature=0.1  # Validator는 더 낮은 temperature
            )
        else:
            # OpenAI 사용 (Classifier 등)
            return ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", settings.openai_model),
                openai_api_key=settings.openai_api_key,
                temperature=0.3
            )

    def create_agent(self, agent_name: str) -> Agent:
        """
        YAML 설정으로 Agent 생성

        Args:
            agent_name: agent 이름 (extractor, classifier, generator, validator)

        Returns:
            CrewAI Agent 객체
        """
        if agent_name not in self.config:
            raise ValueError(f"Agent '{agent_name}' not found in config")

        agent_config = self.config[agent_name]
        
        # Agent별 Tool 로드
        tools = self._get_agent_tools(agent_name)
        
        # Agent별 LLM 선택 (멀티 에이전트 아키텍처)
        agent_llm = self._get_llm(agent_name)

        return Agent(
            role=agent_config.get("role", "").strip(),
            goal=agent_config.get("goal", "").strip(),
            backstory=agent_config.get("backstory", "").strip(),
            llm=agent_llm,  # Agent별로 다른 LLM 사용
            verbose=agent_config.get("verbose", True),
            allow_delegation=agent_config.get("allow_delegation", False),
            max_iter=agent_config.get("max_iter", 3),
            tools=tools
        )
    
    def _get_agent_tools(self, agent_name: str) -> list:
        """
        Agent별 Tool 목록 반환
        
        Args:
            agent_name: agent 이름
            
        Returns:
            Tool 목록
        """
        from app.tools.crewai_tools import (
            get_classifier_tools,
            get_generator_tools,
            get_validator_tools,
            get_classifier_tools_with_notice
        )
        
        if agent_name == "classifier":
            # Classifier는 고시금액 조회도 필요할 수 있음
            return get_classifier_tools_with_notice()
        elif agent_name == "generator":
            return get_generator_tools()
        elif agent_name == "validator":
            return get_validator_tools()
        else:
            return []  # extractor는 기본적으로 tool 없음

    def get_all_agents(self) -> Dict[str, Agent]:
        """
        모든 Agent를 생성하여 딕셔너리로 반환

        Returns:
            {agent_name: Agent} 형태의 딕셔너리
        """
        agent_names = ["extractor", "classifier", "generator", "validator"]
        return {
            name: self.create_agent(name)
            for name in agent_names
            if name in self.config
        }

    def get_tools_config(self) -> Dict[str, Any]:
        """
        Tools 설정 반환

        Returns:
            tools 설정 딕셔너리
        """
        return self.config.get("tools", {})

    def get_crew_config(self) -> Dict[str, Any]:
        """
        Crew 설정 반환

        Returns:
            crew 설정 딕셔너리
        """
        return self.config.get("crew", {})


# Singleton 패턴으로 전역 로더 제공
_global_loader = None

def get_agent_loader() -> AgentConfigLoader:
    """전역 AgentConfigLoader 인스턴스 반환"""
    global _global_loader
    if _global_loader is None:
        _global_loader = AgentConfigLoader()
    return _global_loader


# 편의 함수들
def load_agent(agent_name: str) -> Agent:
    """
    YAML 설정에서 특정 Agent 로드

    Args:
        agent_name: agent 이름

    Returns:
        Agent 객체
    """
    loader = get_agent_loader()
    return loader.create_agent(agent_name)


def load_all_agents() -> Dict[str, Agent]:
    """
    YAML 설정에서 모든 Agent 로드

    Returns:
        {agent_name: Agent} 딕셔너리
    """
    loader = get_agent_loader()
    return loader.get_all_agents()
