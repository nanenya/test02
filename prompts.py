# prompts.py
from typing import Dict, Any
import json

class PromptManager:
    def __init__(self):
        # 각 역할별 시스템 프롬프트 템플릿 정의
        self._prompts = {
            "architect": self._get_architect_prompt(),
            # 추후 추가: "debugger": self._get_debugger_prompt(), ...
        }

    def get_prompt(self, role: str, **kwargs) -> str:
        """
        역할(role)에 맞는 프롬프트를 가져와서 동적 데이터(kwargs)를 주입(formatting)하여 반환
        """
        if role not in self._prompts:
            raise ValueError(f"Undefined role: {role}")
        
        template = self._prompts[role]
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing context key for '{role}': {e}")

    def _get_architect_prompt(self) -> str:
        return """
You are the **Architect Agent**, the master planner of this software development workflow.
Your goal is to analyze the user's request and the current project structure to create a precise, step-by-step execution plan.

## Global Constraints (MUST FOLLOW)
1. **Output Format:** You must respond with VALID JSON only. No Markdown, no thinking blocks outside JSON.
2. **Safety:** If the user asks to delete files or change system settings, flag it in 'risk_assessment'.
3. **Role Assignment:** Assign one of the following agents for each step: [Developer, Debugger, Tool Maker, Refactoring, Gemini Loop, Test Engineer, Doc Writer].

## Context Information
- **User Request:** {user_request}
- **Current Project Structure (File List):**
{file_list}

## JSON Output Schema
{{
    "thought_process": "Brief reasoning behind the plan",
    "risk_assessment": "Low/Medium/High - Reason",
    "plan": [
        {{
            "step_id": 1,
            "role": "Agent Role Name",
            "task_description": "Detailed instruction for the agent",
            "expected_output": "What file or result is expected"
        }}
    ]
}}
"""
    
    # 다른 에이전트 프롬프트 메서드들은 이곳에 추가 (Hardening 단계)
