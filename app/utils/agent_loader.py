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
        self.llm = self._get_llm()

    def _load_config(self) -> Dict[str, Any]:
        """YAML 파일 로드"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Agent config file not found: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _get_llm(self):
        """LLM 인스턴스 생성"""
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
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

        return Agent(
            role=agent_config.get("role", "").strip(),
            goal=agent_config.get("goal", "").strip(),
            backstory=agent_config.get("backstory", "").strip(),
            llm=self.llm,
            verbose=agent_config.get("verbose", True),
            allow_delegation=agent_config.get("allow_delegation", False),
            max_iter=agent_config.get("max_iter", 3)
            # tools는 추후 구현
        )

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
