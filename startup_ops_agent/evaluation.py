from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from startup_ops_agent.config import default_data_dir, load_settings
from startup_ops_agent.energy_repository import EnergyJsonRepository
from startup_ops_agent.energy_service import EnergyOptimizationService
from startup_ops_agent.instructions import build_agent_instruction, evaluate_instruction_contract


@dataclass(frozen=True)
class EvaluationResult:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class EvaluationReport:
    total: int
    passed: int
    failed: int
    results: list[EvaluationResult]
    metrics: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "results": [result.__dict__ for result in self.results],
            "metrics": self.metrics,
        }


def _copy_data_dir(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if path.is_file():
            shutil.copy(path, target / path.name)


def _result(name: str, passed: bool, detail: str) -> EvaluationResult:
    return EvaluationResult(name=name, passed=passed, detail=detail)


def _evaluate_instruction_contract() -> EvaluationResult:
    instruction = build_agent_instruction(load_settings())
    missing = evaluate_instruction_contract(instruction)
    return _result(
        "instruction_contract",
        not missing,
        "Instruction includes required energy tool trajectory and safety clauses."
        if not missing
        else f"Missing instruction phrases: {missing}",
    )


def _evaluate_track2_mandates() -> EvaluationResult:
    from startup_ops_agent.agent import root_agent

    sub_agent_names = {agent.name for agent in root_agent.sub_agents}
    expected = {
        "weather_pricing_grounding_agent",
        "comfort_cost_conflict_agent",
        "energy_action_governance_agent",
    }
    if sub_agent_names != expected:
        return _result(
            "track2_multi_agent_mandates",
            False,
            f"Expected ADK sub-agents {sorted(expected)}, got {sorted(sub_agent_names)}.",
        )
    if load_settings().model == "":
        return _result(
            "track2_multi_agent_mandates",
            False,
            "Gemini model configuration is empty.",
        )
    return _result(
        "track2_multi_agent_mandates",
        True,
        "ADK root agent coordinates simulation-grounded conflict and governance agents.",
    )


def _evaluate_energy_simulation(service: EnergyOptimizationService) -> EvaluationResult:
    results = service.run_all_simulations()
    failed = [result for result in results if not result.passed]
    if failed:
        return _result(
            "energy_extreme_weather_peak_pricing_simulation",
            False,
            f"Failed simulation cases: {[result.case_id for result in failed]}.",
        )
    critical = next(
        result
        for result in results
        if result.case_id == "heat-dome-peak-price-critical-occupancy"
    )
    expected_steps = [
        "retrieve_context",
        "detect_conflict",
        "evaluate_priority",
        "allocate_load_shed",
        "governance_safety_check",
        "compute_impact",
    ]
    has_trace = [step.step for step in critical.trace] == expected_steps
    if critical.plan.primary_priority.value != "safety" or not has_trace:
        return _result(
            "energy_extreme_weather_peak_pricing_simulation",
            False,
            "Critical rare-event case did not prioritize safety with observability trace.",
        )
    return _result(
        "energy_extreme_weather_peak_pricing_simulation",
        True,
        "Synthetic rare-event simulation prioritizes safety and emits trace steps.",
    )


def _evaluate_energy_business_impact(service: EnergyOptimizationService) -> EvaluationResult:
    plan = service.build_optimization_plan(
        building_id="bldg-medtech-hq",
        weather_event_id="weather-heat-dome",
        pricing_event_id="pricing-peak-surge",
        occupancy_id="occupancy-business-critical",
    )
    shed_load_ids = {decision.load_id for decision in plan.load_shed}
    expected_loads = {"cafeteria-cooling", "conference-preconditioning"}
    if shed_load_ids != expected_loads:
        return _result(
            "energy_b2b_business_impact",
            False,
            "Expected non-critical shed loads "
            f"{sorted(expected_loads)}, got {sorted(shed_load_ids)}.",
        )
    if (
        plan.estimated_cost_avoidance_usd <= 0
        or plan.estimated_business_risk_avoided_usd <= 0
    ):
        return _result(
            "energy_b2b_business_impact",
            False,
            "Plan did not include both cost avoidance and protected business risk impact.",
        )
    return _result(
        "energy_b2b_business_impact",
        True,
        "Rare-event plan reports load-level shedding, cost avoidance, and protected risk.",
    )


def _evaluate_safety_invariants(service: EnergyOptimizationService) -> EvaluationResult:
    results = service.run_all_simulations()
    offending = {
        result.case_id: [violation.code for violation in result.plan.safety_violations]
        for result in results
        if result.plan.safety_violations
    }
    if offending:
        return _result(
            "energy_safety_invariants",
            False,
            f"Safety invariants violated in simulated plans: {offending}.",
        )
    return _result(
        "energy_safety_invariants",
        True,
        f"All {len(results)} simulated plans satisfy safety invariants: no critical-zone "
        "shedding, setpoints within safe bounds, shed within capacity.",
    )


def _compute_metrics(service: EnergyOptimizationService) -> dict[str, object]:
    cases = service.repository.simulation_cases()
    sim_results = service.run_all_simulations()
    passed = sum(1 for result in sim_results if result.passed)
    total = len(cases)

    priority_distribution: dict[str, int] = {}
    safety_violations_total = 0
    source_id_preserved = 0
    latencies_ms: list[float] = []
    for case in cases:
        start = time.perf_counter()
        plan = service.build_optimization_plan(
            building_id=case.building_id,
            weather_event_id=case.weather_event_id,
            pricing_event_id=case.pricing_event_id,
            occupancy_id=case.occupancy_id,
        )
        latencies_ms.append((time.perf_counter() - start) * 1000.0)
        priority_distribution[plan.primary_priority.value] = (
            priority_distribution.get(plan.primary_priority.value, 0) + 1
        )
        safety_violations_total += len(plan.safety_violations)
        expected_ids = {
            case.building_id,
            case.weather_event_id,
            case.pricing_event_id,
            case.occupancy_id,
        }
        if expected_ids.issubset(set(plan.source_ids)):
            source_id_preserved += 1

    return {
        "simulation_total": total,
        "simulation_passed": passed,
        "simulation_pass_rate": round(passed / total, 4) if total else 0.0,
        "safety_violations_total": safety_violations_total,
        "priority_distribution": priority_distribution,
        "avg_decision_latency_ms": round(sum(latencies_ms) / len(latencies_ms), 3)
        if latencies_ms
        else 0.0,
        "source_id_preservation_rate": round(source_id_preserved / total, 4) if total else 0.0,
    }


def _evaluate_energy_portfolio(service: EnergyOptimizationService) -> EvaluationResult:
    plan = service.build_portfolio_plan(
        weather_event_id="weather-heat-dome",
        pricing_event_id="pricing-grid-emergency",
    )
    if not plan.target_met:
        return _result(
            "energy_portfolio_demand_response",
            False,
            f"Portfolio left {plan.unmet_shed_kw} kW of the fleet target unmet.",
        )
    if not plan.protected_buildings:
        return _result(
            "energy_portfolio_demand_response",
            False,
            "Portfolio did not protect any safety-critical building during the grid emergency.",
        )
    protected = {c.building_id: c for c in plan.contributions if c.protected}
    over_shed = [
        building_id
        for building_id, contribution in protected.items()
        if contribution.allocated_shed_kw >= contribution.sheddable_capacity_kw
        and contribution.sheddable_capacity_kw > 0
    ]
    if over_shed:
        return _result(
            "energy_portfolio_demand_response",
            False,
            f"Protected buildings were shed to capacity instead of last: {sorted(over_shed)}.",
        )
    if plan.total_cost_avoidance_usd <= 0 or plan.total_co2_avoided_kg <= 0:
        return _result(
            "energy_portfolio_demand_response",
            False,
            "Portfolio plan did not report fleet cost and CO2 avoidance.",
        )
    return _result(
        "energy_portfolio_demand_response",
        True,
        "Portfolio meets the fleet demand-response target while protecting critical buildings "
        "and reporting cost and CO2 avoidance.",
    )


def run_evaluations(data_dir: Path | None = None) -> EvaluationReport:
    source = data_dir or default_data_dir()
    with tempfile.TemporaryDirectory(prefix="startup-ops-eval-") as temp_dir:
        isolated_data_dir = Path(temp_dir)
        _copy_data_dir(source, isolated_data_dir)
        energy_service = EnergyOptimizationService(EnergyJsonRepository(isolated_data_dir))
        results = [
            _evaluate_instruction_contract(),
            _evaluate_track2_mandates(),
            _evaluate_energy_simulation(energy_service),
            _evaluate_energy_business_impact(energy_service),
            _evaluate_energy_portfolio(energy_service),
            _evaluate_safety_invariants(energy_service),
        ]
        metrics = _compute_metrics(energy_service)
    passed = sum(1 for result in results if result.passed)
    return EvaluationReport(
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        results=results,
        metrics=metrics,
    )


def write_report(path: Path, report: EvaluationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
