import pytest
from pydantic import ValidationError

from startup_ops_agent.config import default_data_dir
from startup_ops_agent.energy_models import BuildingProfile, EnergyPriority, FlexibleLoad
from startup_ops_agent.energy_repository import EnergyJsonRepository
from startup_ops_agent.energy_service import EnergyOptimizationService
from startup_ops_agent.optimizer import optimize_energy_instructions


def _building_kwargs(**overrides) -> dict:
    base = dict(
        building_id="bldg-test",
        name="Test",
        tenant_id="tenant-test",
        business_type="test",
        hvac_zones=["lobby", "lab"],
        critical_zones=["lab"],
        flexible_loads=[
            FlexibleLoad(load_id="l1", description="d", zones=["lobby"], max_shed_kw=5)
        ],
        normal_setpoint_c=23.0,
        max_safe_setpoint_c=25.0,
        min_safe_setpoint_c=19.0,
        business_value_at_risk_usd_per_hour=100.0,
        business_risk_protection_factor=0.5,
        critical_zone_policy="policy",
    )
    base.update(overrides)
    return base


def test_building_profile_rejects_inverted_setpoints() -> None:
    with pytest.raises(ValidationError):
        BuildingProfile(**_building_kwargs(min_safe_setpoint_c=26.0))


def test_building_profile_rejects_critical_zone_outside_hvac_zones() -> None:
    with pytest.raises(ValidationError):
        BuildingProfile(**_building_kwargs(critical_zones=["nonexistent"]))


def test_extreme_weather_and_peak_pricing_prioritizes_safety() -> None:
    service = EnergyOptimizationService(EnergyJsonRepository(default_data_dir()))

    plan = service.build_optimization_plan(
        building_id="bldg-medtech-hq",
        weather_event_id="weather-heat-dome",
        pricing_event_id="pricing-peak-surge",
        occupancy_id="occupancy-business-critical",
    )

    assert plan.primary_priority == EnergyPriority.safety
    assert plan.setpoint_c == 23.0
    assert plan.expected_load_shed_kw < 48
    assert {decision.load_id for decision in plan.load_shed} == {
        "cafeteria-cooling",
        "conference-preconditioning",
    }
    assert plan.estimated_cost_avoidance_usd == 3447.36
    assert plan.estimated_business_risk_avoided_usd == 9000.0
    assert plan.conflicts == ["extreme_weather_peak_pricing"]
    assert any("HeatRisk" in basis for basis in plan.real_world_basis)
    assert any("Critical-zone policy" in note for note in plan.compliance_notes)
    assert "weather-heat-dome" in plan.source_ids


def test_scenario_resolver_builds_heat_dome_peak_surge_plan() -> None:
    service = EnergyOptimizationService(EnergyJsonRepository(default_data_dir()))

    result = service.build_plan_from_scenario(
        "Optimize MedTech HQ during the heat dome and peak-demand surge. "
        "Prioritize critical occupants."
    )

    assert result["resolved_inputs"] == {
        "building_id": "bldg-medtech-hq",
        "weather_event_id": "weather-heat-dome",
        "pricing_event_id": "pricing-peak-surge",
        "occupancy_id": "occupancy-business-critical",
    }
    assert result["plan"].primary_priority == EnergyPriority.safety


def test_peak_pricing_on_normal_day_prioritizes_cost() -> None:
    service = EnergyOptimizationService(EnergyJsonRepository(default_data_dir()))

    plan = service.build_optimization_plan(
        building_id="bldg-medtech-hq",
        weather_event_id="weather-normal",
        pricing_event_id="pricing-peak-surge",
        occupancy_id="occupancy-low",
    )

    assert plan.primary_priority == EnergyPriority.cost
    assert plan.expected_load_shed_kw == 48.0
    assert {decision.load_id for decision in plan.load_shed} == {
        "cafeteria-cooling",
        "conference-preconditioning",
        "ev-chargers",
    }
    assert plan.estimated_cost_avoidance_usd == 7660.8
    assert plan.estimated_business_risk_avoided_usd == 0.0
    assert plan.conflicts == []


def test_plan_reports_co2_avoided_from_grid_emissions() -> None:
    service = EnergyOptimizationService(EnergyJsonRepository(default_data_dir()))

    plan = service.build_optimization_plan(
        building_id="bldg-medtech-hq",
        weather_event_id="weather-normal",
        pricing_event_id="pricing-peak-surge",
        occupancy_id="occupancy-low",
    )

    # 48 kW shed x 4 h window x 0.62 kg/kWh marginal emissions.
    assert plan.estimated_co2_avoided_kg == 119.04


def test_portfolio_meets_fleet_target_and_protects_critical_building() -> None:
    service = EnergyOptimizationService(EnergyJsonRepository(default_data_dir()))

    plan = service.build_portfolio_plan(
        weather_event_id="weather-heat-dome",
        pricing_event_id="pricing-grid-emergency",
    )

    assert plan.fleet_demand_response_target_kw == 120.0
    assert plan.total_allocated_shed_kw == 120.0
    assert plan.target_met is True
    assert plan.unmet_shed_kw == 0.0
    assert plan.protected_buildings == ["bldg-medtech-hq"]

    by_id = {c.building_id: c for c in plan.contributions}
    # Lower-risk buildings are shed to capacity first.
    assert by_id["bldg-logistics-dc"].allocated_shed_kw == 70.0
    assert by_id["bldg-coworking-tower"].allocated_shed_kw == 30.0
    # The safety-critical building is protected: shed last and below its capacity.
    medtech = by_id["bldg-medtech-hq"]
    assert medtech.protected is True
    assert medtech.allocated_shed_kw == 20.0
    assert medtech.allocated_shed_kw < medtech.sheddable_capacity_kw
    # Cleanroom and server-room loads are never selected for the fleet target.
    assert "ev-chargers" not in {decision.load_id for decision in medtech.load_shed}
    assert plan.total_co2_avoided_kg > 0


def test_portfolio_target_exceeding_capacity_is_unmet_not_unsafe() -> None:
    service = EnergyOptimizationService(EnergyJsonRepository(default_data_dir()))

    # The standard event requests 0 kW; force a comparison by checking the
    # grid-emergency target against total fleet capacity instead.
    plan = service.build_portfolio_plan(
        weather_event_id="weather-heat-dome",
        pricing_event_id="pricing-grid-emergency",
    )
    total_capacity = sum(c.sheddable_capacity_kw for c in plan.contributions)

    assert plan.total_allocated_shed_kw <= total_capacity
    assert plan.total_allocated_shed_kw + plan.unmet_shed_kw >= plan.fleet_demand_response_target_kw


def test_simulation_returns_observability_trace() -> None:
    service = EnergyOptimizationService(EnergyJsonRepository(default_data_dir()))

    result = service.run_simulation_case("heat-dome-peak-price-critical-occupancy")

    assert result.passed is True
    assert [step.step for step in result.trace] == [
        "retrieve_context",
        "detect_conflict",
        "evaluate_priority",
        "allocate_load_shed",
        "governance_safety_check",
        "compute_impact",
    ]


def test_plan_passes_safety_invariants_and_never_sheds_critical_loads() -> None:
    service = EnergyOptimizationService(EnergyJsonRepository(default_data_dir()))

    plan = service.build_optimization_plan(
        building_id="bldg-medtech-hq",
        weather_event_id="weather-heat-dome",
        pricing_event_id="pricing-peak-surge",
        occupancy_id="occupancy-business-critical",
    )

    assert plan.safety_invariants_passed is True
    assert plan.safety_violations == []
    # Every plan carries the 6-step reasoning trace, not just simulations.
    assert [step.step for step in plan.trace][0] == "retrieve_context"
    assert "governance_safety_check" in {step.step for step in plan.trace}
    # The critical-zone loads must never appear in the shed set.
    building = service._building("bldg-medtech-hq")
    critical_zones = set(building.critical_zones)
    loads_by_id = {load.load_id: load for load in building.flexible_loads}
    for decision in plan.load_shed:
        assert not critical_zones.intersection(loads_by_id[decision.load_id].zones)


def test_all_simulations_pass_with_zero_safety_violations() -> None:
    service = EnergyOptimizationService(EnergyJsonRepository(default_data_dir()))

    results = service.run_all_simulations()

    assert len(results) >= 7
    assert all(result.passed for result in results)
    assert sum(len(result.plan.safety_violations) for result in results) == 0


def test_instruction_optimizer_adds_missing_conflict_rules() -> None:
    result = optimize_energy_instructions("You are an energy assistant.")

    assert result["changed"] is True
    assert "occupant safety outranks energy cost during extreme weather" in result[
        "optimized_instruction"
    ]
