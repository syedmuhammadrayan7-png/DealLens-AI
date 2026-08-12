from backend.mcp.finance import calculate_arpu, calculate_customer_concentration, calculate_revenue_growth, calculate_runway


def test_finance_calculations_are_deterministic():
    assert calculate_runway(120_000, 10_000) == 12
    assert calculate_arpu(2_500, 5) == 500
    assert calculate_revenue_growth(150, 100) == 50
    assert calculate_customer_concentration(2_000, 10_000) == 20


def test_missing_financial_inputs_do_not_invent_values():
    assert calculate_runway(100, 0) is None
    assert calculate_arpu(100, 0) is None
