"""Actual stdio MCP client for the custom DealLens Finance server."""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from backend.schemas.case import ToolDiscovery


class DealLensMCPClient:
    def discover(self) -> list[ToolDiscovery]:
        return [ToolDiscovery(
            server="DealLens Finance MCP",
            tools=["calculate_runway", "calculate_monthly_burn", "calculate_arpu", "calculate_revenue_growth", "calculate_customer_concentration", "calculate_basic_unit_economics"],
            resources=["deallens://frameworks/preseed", "deallens://frameworks/saas-metrics", "deallens://risk-policy"],
            prompts=["investment_committee_memo"],
        )]


class MCPUnavailableError(RuntimeError):
    pass


class FinanceMCPClient:
    """Calls the Finance MCP server over stdio; no calculation functions are imported here."""

    async def _call_async(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:  # pragma: no cover - dependency check is environment-specific
            raise MCPUnavailableError("MCP runtime is unavailable. Install the backend requirements using a supported Python version.") from exc
        params = StdioServerParameters(command=sys.executable, args=["-m", "backend.mcp.servers.finance_server"])
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                if tool_name not in {item.name for item in tools.tools}:
                    raise MCPUnavailableError(f"Finance MCP did not advertise required tool: {tool_name}")
                result = await session.call_tool(tool_name, arguments)
                if result.isError:
                    raise MCPUnavailableError(f"Finance MCP tool {tool_name} returned an error.")
                text = "".join(getattr(item, "text", "") for item in result.content)
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text

    def call_tool(self, tool_name: str, **arguments: Any) -> Any:
        """Synchronous boundary for CrewAI's synchronous tool execution."""
        return asyncio.run(self._call_async(tool_name, arguments))

    def financial_metrics(self, values: dict[str, Any]) -> dict[str, float | None]:
        result = self.call_tool("calculate_basic_unit_economics", **values)
        if not isinstance(result, dict):
            raise MCPUnavailableError("Finance MCP returned an invalid metrics payload.")
        return result
