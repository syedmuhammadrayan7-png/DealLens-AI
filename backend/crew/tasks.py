"""Concrete CrewAI task definitions with bounded, evidence-first inputs."""
from __future__ import annotations

import json
from typing import Any

from backend.schemas.case import DueDiligenceReport


def build_tasks(agents: dict[str, Any], context: dict[str, Any]):
    from crewai import Task

    evidence = json.dumps(context, default=str, indent=2)
    company = Task(
        description=f"""Create a company-research finding for {context['company_name']}.
Use only this supplied evidence: {evidence}
Return product summary, public company information, public-company claims, founder-provided claims, and evidence labels.
Claims from the company website must be public_company_claim, not founder_provided. Founder_provided is reserved for an uploaded pitch deck, manually supplied financial inputs, or founder notes.
Never present an unavailable source or an inference as verified.""",
        expected_output="Evidence-labelled company findings, compact JSON-like prose.", agent=agents["company"],
    )
    market = Task(
        description="Using the company context supplied in the previous task, identify market context, competitors or alternatives only where supported, differentiation, moat signals, and market risks. Missing research is unavailable, not a fact.",
        expected_output="Evidence-labelled market finding.", agent=agents["market"], context=[company],
    )
    technical = Task(
        description="Use only supplied GitHub metadata. Report repository metadata, activity, contributors, languages, releases, issues and limited engineering maturity signals. If metadata is unavailable, return structured unavailable evidence and continue.",
        expected_output="Evidence-labelled technical finding.", agent=agents["technical"], context=[company],
    )
    financial = Task(
        description="Use the Finance MCP tool for every available financial calculation. Interpret its outputs without doing arithmetic yourself. Where values are absent or the tool cannot respond, clearly mark the finding unavailable.",
        expected_output="Evidence-labelled financial finding grounded in Finance MCP tool outputs.", agent=agents["financial"],
    )
    risk = Task(
        description="Challenge the preceding findings: identify unsupported claims, contradictions, evidence gaps, risk level and confidence. Missing evidence is uncertainty, not proof of a negative.",
        expected_output="Evidence-labelled risk committee finding and verification questions.", agent=agents["risk"], context=[company, market, technical, financial],
    )
    memo = Task(
        description=f"""Create the final Pydantic DueDiligenceReport for case {context['case_id']}.
Company name must be {context['company_name']}; sector is {context['sector']}; funding stage is {context['funding_stage']}.
Use prior findings only. Populate every score 0–100, classify every evidence item, and use only permitted recommendation values. This is decision support, never an investment guarantee.""",
        expected_output="A valid DueDiligenceReport object.", agent=agents["memo"], context=[company, market, technical, financial, risk], output_pydantic=DueDiligenceReport,
    )
    return [company, market, technical, financial, risk, memo]
