"""All CrewAI agents share the single configured OpenAI model."""
from __future__ import annotations

from backend.config import Settings
from backend.mcp.clients import FinanceMCPClient

AGENT_SPECS = {
    "company": ("Company Intelligence Agent", "Verify public company claims, product and observable traction. Clearly label evidence."),
    "market": ("Market & Competition Agent", "Research market structure, competitors, alternatives and defensibility. Do not infer unsupported facts."),
    "technical": ("Technical Due-Diligence Agent", "Assess supplied public GitHub evidence only. Never claim code quality without evidence."),
    "financial": ("Financial Analysis Agent", "Interpret deterministic MCP financial outputs. Never do arithmetic in prose."),
    "risk": ("Risk Committee Agent", "Challenge contradictions and separate uncertainty from risk."),
    "memo": ("Investment Memo Agent", "Produce a concise structured decision-support memo, without investment guarantees."),
}


def build_agents(settings: Settings):
    """Lazy import keeps health/config errors usable even when CrewAI is not installed."""
    from crewai import Agent, LLM
    from crewai.tools import tool

    api_key = settings.require_openai()
    # The OpenAI SDK already retries transient statuses only; 400/401/403 fail immediately.
    llm = LLM(model=f"openai/{settings.openai_model}", api_key=api_key, timeout=settings.openai_timeout_seconds, max_retries=settings.openai_max_retries)

    @tool("DealLens Finance MCP")
    def finance_mcp(tool_name: str, arguments_json: str) -> str:
        """Call a deterministic DealLens Finance MCP tool. Arguments must be a JSON object."""
        import json
        result = FinanceMCPClient().call_tool(tool_name, **json.loads(arguments_json))
        return json.dumps(result)

    agents = {}
    for name, (role, goal) in AGENT_SPECS.items():
        agents[name] = Agent(
            role=role, goal=goal, backstory="You work on DealLens AI, an evidence-first venture diligence platform. Do not expose internal reasoning; return concise evidence-backed findings.",
            llm=llm, verbose=False, allow_delegation=False,
            tools=[finance_mcp] if name == "financial" else [],
            max_retry_limit=0,
        )
    return agents
