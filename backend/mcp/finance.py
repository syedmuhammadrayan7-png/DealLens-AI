"""Pure deterministic financial functions shared by MCP and the workflow."""
from __future__ import annotations


def calculate_runway(cash_available: float | None, monthly_burn: float | None) -> float | None:
    if cash_available is None or monthly_burn is None or monthly_burn <= 0:
        return None
    return round(cash_available / monthly_burn, 2)


def calculate_monthly_burn(monthly_revenue: float | None, monthly_costs: float | None) -> float | None:
    if monthly_revenue is None or monthly_costs is None:
        return None
    return round(max(0, monthly_costs - monthly_revenue), 2)


def calculate_arpu(monthly_revenue: float | None, customers: int | None) -> float | None:
    if monthly_revenue is None or not customers:
        return None
    return round(monthly_revenue / customers, 2)


def calculate_revenue_growth(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous <= 0:
        return None
    return round(((current - previous) / previous) * 100, 2)


def calculate_customer_concentration(largest_customer_revenue: float | None, monthly_revenue: float | None) -> float | None:
    if largest_customer_revenue is None or not monthly_revenue or monthly_revenue <= 0:
        return None
    return round((largest_customer_revenue / monthly_revenue) * 100, 2)


def calculate_basic_unit_economics(monthly_revenue: float | None, monthly_burn: float | None, customers: int | None) -> dict[str, float | None]:
    return {
        "arpu": calculate_arpu(monthly_revenue, customers),
        "net_cash_flow": None if monthly_revenue is None or monthly_burn is None else round(monthly_revenue - monthly_burn, 2),
    }
