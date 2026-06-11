from startup_ops_agent.evaluation import run_evaluations


def test_evaluation_harness_passes_baseline_cases() -> None:
    report = run_evaluations()

    assert report.failed == 0
    assert {result.name for result in report.results} == {
        "instruction_contract",
        "track2_multi_agent_mandates",
        "energy_extreme_weather_peak_pricing_simulation",
        "energy_b2b_business_impact",
        "energy_portfolio_demand_response",
        "energy_safety_invariants",
    }


def test_evaluation_report_includes_quantitative_metrics() -> None:
    report = run_evaluations()
    metrics = report.to_dict()["metrics"]

    assert metrics["simulation_pass_rate"] == 1.0
    assert metrics["safety_violations_total"] == 0
    assert metrics["source_id_preservation_rate"] == 1.0
    assert metrics["simulation_total"] == metrics["simulation_passed"]
    assert sum(metrics["priority_distribution"].values()) == metrics["simulation_total"]
    assert metrics["avg_decision_latency_ms"] >= 0.0
