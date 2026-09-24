"""Route a conversion unit to the right agent based on its category."""
from __future__ import annotations

from src.agents.base import BaseAgent
from src.agents.data_engineering import DataEngineeringAgent
from src.agents.modelling import ModellingAgent
from src.llm.base import LLMClient

_AGENTS: dict[str, type[BaseAgent]] = {
    "data_engineering": DataEngineeringAgent,
    "modelling": ModellingAgent,
}


def get_agent(category: str, client: LLMClient, knowledge_dir: str | None = None) -> BaseAgent:
    agent_cls = _AGENTS.get(category, DataEngineeringAgent)
    return agent_cls(client, knowledge_dir=knowledge_dir)
