from __future__ import annotations

from typing import Any

from backend.config import Settings
from backend.crew.agents import build_agents
from backend.crew.tasks import build_tasks


def create_due_diligence_crew(settings: Settings, context: dict[str, Any] | None = None):
    """Build a real sequential CrewAI crew; flow state remains owned outside the crew."""
    from crewai import Crew, Process

    agents = build_agents(settings)
    if context is None:
        return agents
    return Crew(agents=list(agents.values()), tasks=build_tasks(agents, context), process=Process.sequential, verbose=False, memory=False)
