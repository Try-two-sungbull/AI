"""
Claude 법령 설명 Agent

Rule Engine 근거를 사람이 이해할 수 있게 설명하는 Agent
- "왜 별표2인가?" 질문에 답변
- 법령 조항을 자연어로 설명
"""

from typing import Dict, Any
from crewai import Agent, Task, Crew, Process
from app.services.agents import create_generator_agent  # Claude Agent 재사용


class ClaudeLawExplainer:
    """
    Claude 기반 법령 설명 Agent
    
    역할: Rule Engine 근거를 자연어로 설명
    특징: 판단 ❌, 설명 ⭕
    """
    
    def __init__(self):
        self.explainer = create_generator_agent()  # Claude Agent 재사용
    
    def explain_classification_reason(
        self,
        classification_result: Dict[str, Any]
    ) -> str:
        """
        분류 결과의 근거를 사람이 이해할 수 있게 설명
        
        Args:
            classification_result: 분류 결과 (reason_trace 포함)
            
        Returns:
            자연어 설명
        """
        reason_trace = classification_result.get("reason_trace", {})
        
        if not reason_trace:
            return classification_result.get("reason", "분류 근거를 설명할 수 없습니다.")
        
        task = Task(
            description=f"""
            당신은 국가계약법 전문가입니다.
            Rule Engine이 내린 분류 결정의 근거를 **사람이 이해할 수 있게** 설명하세요.
            
            **중요**: 판단이나 해석을 하지 마세요. 단순히 **설명**만 하세요.
            
            분류 결과:
            {{
                "estimated_price_exc_vat": {reason_trace.get('estimated_price_exc_vat', 0):,.0f}원,
                "applied_annex": "{reason_trace.get('applied_annex', '')}",
                "sme_restriction": "{reason_trace.get('sme_restriction', '')}",
                "contract_method": "{classification_result.get('recommended_type', '')}"
            }}
            
            Rule Engine 계산 단계:
            {chr(10).join(reason_trace.get('calculation_steps', []))}
            
            다음을 포함하여 설명하세요:
            1. 왜 이 공고 방식이 선택되었는지
            2. 적용된 별표가 무엇인지, 왜 적용되었는지
            3. 중소기업 제한이 왜 필요한지 (또는 없는지)
            
            설명은 **간결하고 명확하게**, 법령 전문가가 아닌 사람도 이해할 수 있게 작성하세요.
            """,
            agent=self.explainer,
            expected_output="분류 근거에 대한 자연어 설명 (2-3문단)"
        )
        
        crew = Crew(
            agents=[self.explainer],
            tasks=[task],
            process=Process.sequential,
            verbose=False
        )
        
        result = crew.kickoff()
        return str(result)
    
    def explain_law_article(
        self,
        law_name: str,
        article: str
    ) -> str:
        """
        법령 조항을 사람이 이해할 수 있게 설명
        
        Args:
            law_name: 법령명
            article: 조항
            
        Returns:
            자연어 설명
        """
        task = Task(
            description=f"""
            다음 법령 조항을 **일반인이 이해할 수 있게** 설명하세요.
            
            법령: {law_name}
            조항: {article}
            
            **중요**: 
            - 법적 해석이나 판단을 하지 마세요
            - 단순히 "이 조항이 무엇을 말하는지" 설명만 하세요
            - 예시를 들어 설명하면 더 좋습니다
            
            설명은 1-2문단으로 간결하게 작성하세요.
            """,
            agent=self.explainer,
            expected_output="법령 조항에 대한 자연어 설명"
        )
        
        crew = Crew(
            agents=[self.explainer],
            tasks=[task],
            process=Process.sequential,
            verbose=False
        )
        
        result = crew.kickoff()
        return str(result)


# Singleton 인스턴스
_claude_explainer = None


def get_claude_explainer() -> ClaudeLawExplainer:
    """전역 Claude Explainer 인스턴스 반환"""
    global _claude_explainer
    if _claude_explainer is None:
        _claude_explainer = ClaudeLawExplainer()
    return _claude_explainer


