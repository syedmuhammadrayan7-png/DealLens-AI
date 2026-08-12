"""DealLens Finance MCP server: tools, resources, and a memo prompt."""
from __future__ import annotations

from backend.mcp.finance import (
    calculate_arpu, calculate_basic_unit_economics, calculate_customer_concentration,
    calculate_monthly_burn, calculate_revenue_growth, calculate_runway,
)

try:  # Keeps core API testable when optional MCP runtime is not installed.
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    FastMCP = None


PRESEED_FRAMEWORK = """Pre-seed review: validate founder-market fit, customer pain, speed of learning, and 12–18 month capital plan. Treat deck claims as founder-provided."""
SAAS_METRICS = """SaaS metrics: runway, growth, ARPU, retention, customer concentration, gross margin, and cash efficiency. Missing data lowers confidence; it is not a negative fact."""
RISK_POLICY = """Evidence policy: verified requires an authoritative public source; supported requires corroboration; unavailable means no conclusion. Never upgrade founder-provided claims without corroboration."""


def create_finance_server():
    if FastMCP is None:
        raise RuntimeError("MCP runtime is unavailable. Install dependencies from backend/requirements.txt.")
    server = FastMCP("DealLens Finance")
    server.tool()(calculate_runway)
    server.tool()(calculate_monthly_burn)
    server.tool()(calculate_arpu)
    server.tool()(calculate_revenue_growth)
    server.tool()(calculate_customer_concentration)
    server.tool()(calculate_basic_unit_economics)

    @server.resource("deallens://frameworks/preseed")
    def preseed_framework() -> str:
        return PRESEED_FRAMEWORK

    @server.resource("deallens://frameworks/saas-metrics")
    def saas_metrics() -> str:
        return SAAS_METRICS

    @server.resource("deallens://risk-policy")
    def risk_policy() -> str:
        return RISK_POLICY

    @server.prompt()
    def investment_committee_memo(company_name: str, findings: str) -> str:
        return f"Prepare a decision-support memo for {company_name}. Apply the risk policy and label every finding. Findings:\n{findings}"

    return server


if __name__ == "__main__":
    create_finance_server().run()
