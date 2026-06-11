from __future__ import annotations

import hashlib
import re

from startup_ops_agent.energy_models import (
    BuildingContribution,
    BuildingProfile,
    EnergyAction,
    EnergyOptimizationPlan,
    EnergyPriority,
    FlexibleLoad,
    LoadShedDecision,
    OccupancyProfile,
    PortfolioOptimizationPlan,
    SafetyViolation,
    SimulationResult,
    TraceStep,
    UtilityPricingEvent,
    WeatherEvent,
)
from startup_ops_agent.energy_repository import EnergyJsonRepository
from startup_ops_agent.service import NotFoundError, SafetyInvariantError


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", value.lower()) if token}


class EnergyOptimizationService:
    def __init__(self, repository: EnergyJsonRepository) -> None:
        self.repository = repository

    def build_optimization_plan(
        self,
        *,
        building_id: str,
        weather_event_id: str,
        pricing_event_id: str,
        occupancy_id: str,
    ) -> EnergyOptimizationPlan:
        building = self._building(building_id)
        weather = self._weather(weather_event_id)
        pricing = self._pricing(pricing_event_id)
        occupancy = self._occupancy(occupancy_id)
        if occupancy.building_id != building.building_id:
            raise NotFoundError("Occupancy profile does not belong to the requested building.")

        extreme_weather = weather.severity == "extreme" or weather.heat_risk_level >= 3
        peak_pricing = pricing.price_multiplier >= 2.0 or pricing.demand_response_requested_kw > 0
        vulnerable_or_critical = occupancy.vulnerable_occupants or bool(
            set(occupancy.occupied_zones).intersection(building.critical_zones)
        )
        conflicts: list[str] = []
        if extreme_weather and peak_pricing:
            conflicts.append("extreme_weather_peak_pricing")

        if extreme_weather and vulnerable_or_critical:
            primary = EnergyPriority.safety
            setpoint = building.normal_setpoint_c
            decision = "Preserve safety-critical comfort and shed only flexible/non-critical load."
        elif extreme_weather:
            primary = EnergyPriority.comfort
            setpoint = min(building.max_safe_setpoint_c, building.normal_setpoint_c + 1.0)
            decision = "Bias toward occupant comfort while allowing a narrow setpoint adjustment."
        elif peak_pricing:
            primary = EnergyPriority.cost
            setpoint = min(building.max_safe_setpoint_c, building.normal_setpoint_c + 2.0)
            decision = (
                "Prioritize cost reduction because comfort and safety constraints are normal."
            )
        else:
            primary = EnergyPriority.resilience
            setpoint = building.normal_setpoint_c
            decision = "Maintain normal operations and monitor grid and weather changes."

        eligible_loads = self._eligible_flexible_loads(
            building=building,
            vulnerable_or_critical=vulnerable_or_critical,
        )
        load_shed = self._load_shed_decisions(
            building=building,
            pricing=pricing,
            primary=primary,
            vulnerable_or_critical=vulnerable_or_critical,
        )
        shed_kw = round(sum(decision.shed_kw for decision in load_shed), 2)
        source_ids = [
            building.building_id,
            weather.event_id,
            pricing.pricing_event_id,
            occupancy.occupancy_id,
        ]
        cost_avoidance = self._estimated_cost_avoidance(shed_kw, pricing)
        co2_avoided = self._estimated_co2_avoided(shed_kw, pricing)
        business_risk = self._business_risk_avoided(
            building=building,
            primary=primary,
            vulnerable_or_critical=vulnerable_or_critical,
        )

        violations = self._check_safety_invariants(
            building=building,
            primary=primary,
            setpoint=setpoint,
            load_shed=load_shed,
            source_ids=source_ids,
        )
        critical_breach = next(
            (v for v in violations if v.code == "critical_zone_load_shed"), None
        )
        if critical_breach is not None:
            raise SafetyInvariantError(critical_breach.detail)

        trace = self._build_trace(
            building=building,
            weather=weather,
            pricing=pricing,
            occupancy=occupancy,
            extreme_weather=extreme_weather,
            peak_pricing=peak_pricing,
            vulnerable_or_critical=vulnerable_or_critical,
            conflicts=conflicts,
            primary=primary,
            decision=decision,
            setpoint=setpoint,
            load_shed=load_shed,
            eligible_loads=eligible_loads,
            shed_kw=shed_kw,
            cost_avoidance=cost_avoidance,
            co2_avoided=co2_avoided,
            business_risk=business_risk,
            violations=violations,
            source_ids=source_ids,
        )

        return EnergyOptimizationPlan(
            plan_id=f"energy-plan-{_stable_id(*source_ids)}",
            building_id=building.building_id,
            decision=decision,
            primary_priority=primary,
            setpoint_c=setpoint,
            expected_load_shed_kw=shed_kw,
            load_shed=load_shed,
            estimated_cost_avoidance_usd=cost_avoidance,
            estimated_co2_avoided_kg=co2_avoided,
            estimated_business_risk_avoided_usd=business_risk,
            actions=self._actions(building, weather, pricing, primary, source_ids),
            conflicts=conflicts,
            compliance_notes=self._compliance_notes(building, weather, vulnerable_or_critical),
            real_world_basis=self._real_world_basis(weather, pricing),
            trace=trace,
            safety_invariants_passed=not violations,
            safety_violations=violations,
            source_ids=source_ids,
        )

    def build_plan_from_scenario(self, scenario: str) -> dict[str, object]:
        building = self._resolve_building(scenario)
        weather = self._resolve_weather(scenario)
        pricing = self._resolve_pricing(scenario)
        occupancy = self._resolve_occupancy(scenario, building)
        plan = self.build_optimization_plan(
            building_id=building.building_id,
            weather_event_id=weather.event_id,
            pricing_event_id=pricing.pricing_event_id,
            occupancy_id=occupancy.occupancy_id,
        )
        return {
            "resolved_inputs": {
                "building_id": building.building_id,
                "weather_event_id": weather.event_id,
                "pricing_event_id": pricing.pricing_event_id,
                "occupancy_id": occupancy.occupancy_id,
            },
            "resolution_notes": [
                f"Matched building '{building.name}' from available building records.",
                f"Selected weather event '{weather.event_id}' for the requested weather risk.",
                (
                    f"Selected pricing event '{pricing.pricing_event_id}' for the "
                    "requested utility pricing risk."
                ),
                (
                    f"Selected occupancy profile '{occupancy.occupancy_id}' for "
                    "critical/vulnerable occupancy."
                ),
            ],
            "plan": plan,
        }

    def run_simulation_case(self, case_id: str) -> SimulationResult:
        case = self._case(case_id)
        plan = self.build_optimization_plan(
            building_id=case.building_id,
            weather_event_id=case.weather_event_id,
            pricing_event_id=case.pricing_event_id,
            occupancy_id=case.occupancy_id,
        )
        failures: list[str] = []
        if plan.primary_priority != case.expected_primary_priority:
            failures.append(
                f"priority {plan.primary_priority.value} != "
                f"expected {case.expected_primary_priority.value}"
            )
        if bool(plan.conflicts) != case.expected_conflict:
            failures.append(
                f"conflict {bool(plan.conflicts)} != expected {case.expected_conflict}"
            )
        if case.expected_setpoint_c is not None and plan.setpoint_c != case.expected_setpoint_c:
            failures.append(f"setpoint {plan.setpoint_c} != expected {case.expected_setpoint_c}")
        if not plan.safety_invariants_passed:
            failures.append(
                f"safety invariants failed: {[v.code for v in plan.safety_violations]}"
            )
        return SimulationResult(
            case_id=case.case_id,
            passed=not failures,
            plan=plan,
            trace=plan.trace,
            failure_reason=None if not failures else "; ".join(failures),
        )

    def run_all_simulations(self) -> list[SimulationResult]:
        return [
            self.run_simulation_case(case.case_id)
            for case in self.repository.simulation_cases()
        ]

    def build_portfolio_plan(
        self,
        *,
        weather_event_id: str,
        pricing_event_id: str,
    ) -> PortfolioOptimizationPlan:
        """Meet a grid-wide demand-response target across the whole building fleet.

        Flexible load is shed from lower-business-risk buildings first, and
        safety-critical buildings are protected (shed last and only from
        non-critical loads).
        """
        weather = self._weather(weather_event_id)
        pricing = self._pricing(pricing_event_id)
        fleet_target = round(pricing.demand_response_requested_kw, 2)

        buildings = self.repository.buildings()
        if not buildings:
            raise NotFoundError("No buildings available for portfolio optimization.")

        # Evaluate each building against the same grid event to learn its priority,
        # protection status, and how much non-critical load it can safely shed.
        evaluated: list[tuple[BuildingProfile, EnergyOptimizationPlan, list[FlexibleLoad]]] = []
        for building in buildings:
            occupancy = self._most_critical_occupancy(building)
            if occupancy is None:
                continue
            plan = self.build_optimization_plan(
                building_id=building.building_id,
                weather_event_id=weather.event_id,
                pricing_event_id=pricing.pricing_event_id,
                occupancy_id=occupancy.occupancy_id,
            )
            vulnerable_or_critical = plan.primary_priority == EnergyPriority.safety
            eligible = self._eligible_flexible_loads(
                building=building,
                vulnerable_or_critical=vulnerable_or_critical,
            )
            evaluated.append((building, plan, eligible))

        if not evaluated:
            raise NotFoundError("No occupancy profiles found for any building in the portfolio.")

        # Shed unprotected, lower-risk buildings first; protected buildings shed last.
        order = sorted(
            evaluated,
            key=lambda item: (
                item[1].primary_priority == EnergyPriority.safety,
                item[0].business_value_at_risk_usd_per_hour,
                item[0].building_id,
            ),
        )

        remaining = fleet_target
        contributions: list[BuildingContribution] = []
        protected_buildings: list[str] = []
        source_ids = [weather.event_id, pricing.pricing_event_id]
        for building, plan, eligible in order:
            protected = plan.primary_priority == EnergyPriority.safety
            if protected:
                protected_buildings.append(building.building_id)
            capacity = round(sum(load.max_shed_kw for load in eligible), 2)
            building_target = round(min(capacity, remaining), 2) if remaining > 0 else 0.0
            decisions = self._allocate_load_shed(
                eligible_loads=eligible,
                target_kw=building_target,
                primary=plan.primary_priority,
            )
            allocated = round(sum(decision.shed_kw for decision in decisions), 2)
            remaining = round(remaining - allocated, 2)
            contributions.append(
                BuildingContribution(
                    building_id=building.building_id,
                    name=building.name,
                    primary_priority=plan.primary_priority,
                    sheddable_capacity_kw=capacity,
                    allocated_shed_kw=allocated,
                    load_shed=decisions,
                    estimated_cost_avoidance_usd=self._estimated_cost_avoidance(allocated, pricing),
                    estimated_co2_avoided_kg=self._estimated_co2_avoided(allocated, pricing),
                    business_value_at_risk_usd_per_hour=building.business_value_at_risk_usd_per_hour,
                    protected=protected,
                    reason=(
                        "Protected safety-critical building: only non-critical load shed, last in "
                        "allocation order."
                        if protected
                        else "Lower-risk building selected earlier to meet the fleet target."
                    ),
                    source_ids=[building.building_id, weather.event_id, pricing.pricing_event_id],
                )
            )
            source_ids.append(building.building_id)

        total_shed = round(sum(c.allocated_shed_kw for c in contributions), 2)
        unmet = round(max(fleet_target - total_shed, 0.0), 2)
        allocation_notes = self._portfolio_allocation_notes(
            fleet_target=fleet_target,
            total_shed=total_shed,
            unmet=unmet,
            protected_buildings=protected_buildings,
        )
        trace = [
            TraceStep(
                step="retrieve_fleet_context",
                decision=f"Evaluated {len(contributions)} buildings against the grid event.",
                reason="Portfolio demand response requires every building's priority and capacity.",
                source_ids=source_ids,
            ),
            TraceStep(
                step="rank_and_allocate",
                decision=f"Allocated {total_shed} kW of the {fleet_target} kW fleet target.",
                reason=(
                    "Lower-business-risk buildings are shed first; "
                    "protected buildings shed last."
                ),
                source_ids=[c.building_id for c in contributions],
            ),
            TraceStep(
                step="protect_critical_buildings",
                decision="protected: " + (", ".join(protected_buildings) or "none"),
                reason=(
                    allocation_notes[-1]
                    if unmet > 0
                    else "Fleet target met within safe limits."
                ),
                source_ids=[weather.event_id, pricing.pricing_event_id],
            ),
        ]
        return PortfolioOptimizationPlan(
            portfolio_plan_id=f"portfolio-plan-{_stable_id(*source_ids)}",
            weather_event_id=weather.event_id,
            pricing_event_id=pricing.pricing_event_id,
            fleet_demand_response_target_kw=fleet_target,
            total_allocated_shed_kw=total_shed,
            target_met=unmet <= 0,
            unmet_shed_kw=unmet,
            total_cost_avoidance_usd=round(
                sum(c.estimated_cost_avoidance_usd for c in contributions), 2
            ),
            total_co2_avoided_kg=round(sum(c.estimated_co2_avoided_kg for c in contributions), 2),
            total_business_risk_avoided_usd=round(
                sum(plan.estimated_business_risk_avoided_usd for _, plan, _ in order), 2
            ),
            protected_buildings=protected_buildings,
            contributions=contributions,
            allocation_notes=allocation_notes,
            trace=trace,
            source_ids=source_ids,
        )

    def _most_critical_occupancy(self, building: BuildingProfile) -> OccupancyProfile | None:
        profiles = [
            occupancy
            for occupancy in self.repository.occupancy_profiles()
            if occupancy.building_id == building.building_id
        ]
        if not profiles:
            return None
        critical_zones = set(building.critical_zones)
        return max(
            profiles,
            key=lambda item: (
                item.vulnerable_occupants,
                len(critical_zones.intersection(item.occupied_zones)),
                item.business_hours,
            ),
        )

    def _portfolio_allocation_notes(
        self,
        *,
        fleet_target: float,
        total_shed: float,
        unmet: float,
        protected_buildings: list[str],
    ) -> list[str]:
        notes = [
            (
                f"Allocated {total_shed} kW of {fleet_target} kW fleet demand-response target "
                "by shedding lower-business-risk buildings first."
            )
        ]
        if protected_buildings:
            notes.append(
                "Protected safety-critical buildings (shed last, non-critical loads only): "
                + ", ".join(protected_buildings)
            )
        if unmet > 0:
            notes.append(
                f"{unmet} kW of the target remains unmet without touching critical-zone HVAC; "
                "escalate to the utility before relaxing safety constraints."
            )
        return notes

    def _check_safety_invariants(
        self,
        *,
        building: BuildingProfile,
        primary: EnergyPriority,
        setpoint: float,
        load_shed: list[LoadShedDecision],
        source_ids: list[str],
    ) -> list[SafetyViolation]:
        violations: list[SafetyViolation] = []
        critical_zones = set(building.critical_zones)
        loads_by_id = {load.load_id: load for load in building.flexible_loads}
        for decision in load_shed:
            load = loads_by_id.get(decision.load_id)
            if load is None:
                violations.append(
                    SafetyViolation(
                        code="unknown_shed_load",
                        detail=f"Shed load {decision.load_id} is not in the building profile.",
                        source_ids=[building.building_id],
                    )
                )
                continue
            shared_critical = critical_zones.intersection(load.zones)
            if shared_critical:
                violations.append(
                    SafetyViolation(
                        code="critical_zone_load_shed",
                        detail=(
                            f"Load {decision.load_id} serves critical zone(s) "
                            f"{sorted(shared_critical)} and must never be shed."
                        ),
                        source_ids=[building.building_id],
                    )
                )
            if decision.shed_kw > load.max_shed_kw + 1e-6:
                violations.append(
                    SafetyViolation(
                        code="shed_exceeds_capacity",
                        detail=(
                            f"Load {decision.load_id} shed {decision.shed_kw} kW exceeds its "
                            f"{load.max_shed_kw} kW capacity."
                        ),
                        source_ids=[building.building_id],
                    )
                )
        if not building.min_safe_setpoint_c <= setpoint <= building.max_safe_setpoint_c:
            violations.append(
                SafetyViolation(
                    code="setpoint_out_of_bounds",
                    detail=(
                        f"Setpoint {setpoint}C is outside the safe band "
                        f"[{building.min_safe_setpoint_c}, {building.max_safe_setpoint_c}]."
                    ),
                    source_ids=[building.building_id],
                )
            )
        if primary == EnergyPriority.safety and setpoint != building.normal_setpoint_c:
            violations.append(
                SafetyViolation(
                    code="critical_comfort_relaxed",
                    detail=(
                        "Safety priority requires the normal critical-zone setpoint "
                        f"{building.normal_setpoint_c}C, but got {setpoint}C."
                    ),
                    source_ids=source_ids,
                )
            )
        return violations

    def _build_trace(
        self,
        *,
        building: BuildingProfile,
        weather: WeatherEvent,
        pricing: UtilityPricingEvent,
        occupancy: OccupancyProfile,
        extreme_weather: bool,
        peak_pricing: bool,
        vulnerable_or_critical: bool,
        conflicts: list[str],
        primary: EnergyPriority,
        decision: str,
        setpoint: float,
        load_shed: list[LoadShedDecision],
        eligible_loads: list[FlexibleLoad],
        shed_kw: float,
        cost_avoidance: float,
        co2_avoided: float,
        business_risk: float,
        violations: list[SafetyViolation],
        source_ids: list[str],
    ) -> list[TraceStep]:
        shed_ids = [decision.load_id for decision in load_shed]
        eligible_ids = [load.load_id for load in eligible_loads]
        critical_zones = sorted(building.critical_zones)
        return [
            TraceStep(
                step="retrieve_context",
                decision="Loaded building, weather, pricing, and occupancy records.",
                reason="Grounded multi-source context is required before any energy action.",
                source_ids=source_ids,
            ),
            TraceStep(
                step="detect_conflict",
                decision="conflict" if conflicts else "no_conflict",
                reason=(
                    f"extreme_weather={extreme_weather}, peak_pricing={peak_pricing}, "
                    f"vulnerable_or_critical={vulnerable_or_critical}."
                ),
                source_ids=[weather.event_id, pricing.pricing_event_id, occupancy.occupancy_id],
            ),
            TraceStep(
                step="evaluate_priority",
                decision=primary.value,
                reason=decision,
                source_ids=source_ids,
            ),
            TraceStep(
                step="allocate_load_shed",
                decision=(
                    f"Shed {shed_kw} kW from {shed_ids}." if shed_ids else "No load shed required."
                ),
                reason=(
                    f"Eligible non-critical loads {eligible_ids}; critical zones "
                    f"{critical_zones} excluded from shedding."
                    if critical_zones
                    else f"Eligible loads {eligible_ids}; building has no critical zones."
                ),
                source_ids=[building.building_id, pricing.pricing_event_id],
            ),
            TraceStep(
                step="governance_safety_check",
                decision="passed" if not violations else "violations_found",
                reason=(
                    f"Setpoint {setpoint}C within "
                    f"[{building.min_safe_setpoint_c}, {building.max_safe_setpoint_c}]; "
                    "no critical-zone load shed."
                    if not violations
                    else f"Invariant issues: {[violation.code for violation in violations]}."
                ),
                source_ids=[building.building_id],
            ),
            TraceStep(
                step="compute_impact",
                decision=(
                    f"cost_avoidance=${cost_avoidance}, co2_avoided={co2_avoided}kg, "
                    f"business_risk_avoided=${business_risk}"
                ),
                reason=(
                    "Financial and carbon impact computed deterministically from tariff, "
                    "grid emissions, and building value fields."
                ),
                source_ids=source_ids,
            ),
        ]

    def _load_by_id(self, items: list, field: str, value: str):
        for item in items:
            if getattr(item, field) == value:
                return item
        raise NotFoundError(f"Energy record not found: {value}")

    def _building(self, building_id: str) -> BuildingProfile:
        return self._load_by_id(self.repository.buildings(), "building_id", building_id)

    def _weather(self, event_id: str) -> WeatherEvent:
        return self._load_by_id(self.repository.weather_events(), "event_id", event_id)

    def _pricing(self, pricing_event_id: str) -> UtilityPricingEvent:
        return self._load_by_id(
            self.repository.pricing_events(),
            "pricing_event_id",
            pricing_event_id,
        )

    def _occupancy(self, occupancy_id: str) -> OccupancyProfile:
        return self._load_by_id(self.repository.occupancy_profiles(), "occupancy_id", occupancy_id)

    def _case(self, case_id: str):
        return self._load_by_id(self.repository.simulation_cases(), "case_id", case_id)

    def _resolve_building(self, scenario: str) -> BuildingProfile:
        scenario_tokens = _tokens(scenario)
        scored = []
        for building in self.repository.buildings():
            searchable = f"{building.building_id} {building.name} {building.business_type}"
            score = len(scenario_tokens.intersection(_tokens(searchable)))
            scored.append((score, building.name, building))
        score, _, building = max(scored, key=lambda item: (item[0], item[1]))
        if score == 0:
            raise NotFoundError("Could not resolve a building from the scenario.")
        return building

    def _resolve_weather(self, scenario: str) -> WeatherEvent:
        scenario_tokens = _tokens(scenario)
        wants_extreme = bool(
            scenario_tokens.intersection({"extreme", "heat", "dome", "wave", "storm"})
        )
        candidates = self.repository.weather_events()
        if wants_extreme:
            return max(candidates, key=lambda item: (item.heat_risk_level, item.severity))
        return min(candidates, key=lambda item: (item.heat_risk_level, item.outdoor_temp_c))

    def _resolve_pricing(self, scenario: str) -> UtilityPricingEvent:
        scenario_tokens = _tokens(scenario)
        wants_peak = bool(
            scenario_tokens.intersection({"peak", "surge", "demand", "pricing", "price"})
        )
        candidates = self.repository.pricing_events()
        if wants_peak:
            return max(
                candidates,
                key=lambda item: (
                    len(
                        scenario_tokens.intersection(
                            _tokens(f"{item.pricing_event_id} {item.provider} {item.source}")
                        )
                    ),
                    item.demand_response_requested_kw,
                    item.price_multiplier,
                ),
            )
        return min(
            candidates,
            key=lambda item: (item.price_multiplier, item.demand_charge_usd_per_kw),
        )

    def _resolve_occupancy(
        self,
        scenario: str,
        building: BuildingProfile,
    ) -> OccupancyProfile:
        scenario_tokens = _tokens(scenario)
        wants_critical = bool(
            scenario_tokens.intersection({"critical", "vulnerable", "occupant", "occupants"})
        )
        profiles = [
            occupancy
            for occupancy in self.repository.occupancy_profiles()
            if occupancy.building_id == building.building_id
        ]
        if not profiles:
            raise NotFoundError(f"No occupancy profiles found for building: {building.building_id}")
        critical_zones = set(building.critical_zones)
        if wants_critical:
            return max(
                profiles,
                key=lambda item: (
                    item.vulnerable_occupants,
                    len(critical_zones.intersection(item.occupied_zones)),
                    item.business_hours,
                ),
            )
        return min(
            profiles,
            key=lambda item: (
                item.vulnerable_occupants,
                len(critical_zones.intersection(item.occupied_zones)),
                item.business_hours,
            ),
        )

    def _load_shed_decisions(
        self,
        *,
        building: BuildingProfile,
        pricing: UtilityPricingEvent,
        primary: EnergyPriority,
        vulnerable_or_critical: bool,
    ) -> list[LoadShedDecision]:
        eligible_loads = self._eligible_flexible_loads(
            building=building,
            vulnerable_or_critical=vulnerable_or_critical,
        )
        flexible_capacity = sum(load.max_shed_kw for load in eligible_loads)
        if primary == EnergyPriority.safety and vulnerable_or_critical:
            target_kw = pricing.demand_response_requested_kw * 0.45
        elif primary == EnergyPriority.cost:
            target_kw = max(pricing.demand_response_requested_kw, 24.0)
        else:
            target_kw = pricing.demand_response_requested_kw * 0.7

        return self._allocate_load_shed(
            eligible_loads=eligible_loads,
            target_kw=min(flexible_capacity, target_kw),
            primary=primary,
        )

    def _eligible_flexible_loads(
        self,
        *,
        building: BuildingProfile,
        vulnerable_or_critical: bool,
    ) -> list[FlexibleLoad]:
        if not vulnerable_or_critical:
            return building.flexible_loads

        critical_zones = set(building.critical_zones)
        return [
            load
            for load in building.flexible_loads
            if not critical_zones.intersection(load.zones)
        ]

    def _allocate_load_shed(
        self,
        *,
        eligible_loads: list[FlexibleLoad],
        target_kw: float,
        primary: EnergyPriority,
    ) -> list[LoadShedDecision]:
        remaining_kw = round(target_kw, 2)
        decisions: list[LoadShedDecision] = []
        for load in sorted(eligible_loads, key=lambda item: item.load_id):
            if remaining_kw <= 0:
                break
            shed_kw = round(min(load.max_shed_kw, remaining_kw), 2)
            if shed_kw <= 0:
                continue
            remaining_kw = round(remaining_kw - shed_kw, 2)
            decisions.append(
                LoadShedDecision(
                    load_id=load.load_id,
                    shed_kw=shed_kw,
                    reason=(
                        "Selected as a controllable non-critical load before changing "
                        "critical-zone HVAC."
                        if primary == EnergyPriority.safety
                        else "Selected to meet utility demand-response target."
                    ),
                )
            )
        return decisions

    def _estimated_cost_avoidance(
        self,
        shed_kw: float,
        pricing: UtilityPricingEvent,
    ) -> float:
        return round(shed_kw * pricing.demand_charge_usd_per_kw * pricing.price_multiplier, 2)

    def _estimated_co2_avoided(
        self,
        shed_kw: float,
        pricing: UtilityPricingEvent,
    ) -> float:
        kwh_avoided = shed_kw * pricing.duration_hours
        return round(kwh_avoided * pricing.marginal_emissions_kg_per_kwh, 2)

    def _business_risk_avoided(
        self,
        *,
        building: BuildingProfile,
        primary: EnergyPriority,
        vulnerable_or_critical: bool,
    ) -> float:
        if primary != EnergyPriority.safety or not vulnerable_or_critical:
            return 0.0
        return round(
            building.business_value_at_risk_usd_per_hour
            * building.business_risk_protection_factor,
            2,
        )

    def _compliance_notes(
        self,
        building: BuildingProfile,
        weather: WeatherEvent,
        vulnerable_or_critical: bool,
    ) -> list[str]:
        notes = [
            "Do not relax HVAC controls for critical zones before exhausting flexible loads.",
            f"Critical-zone policy: {building.critical_zone_policy}",
        ]
        if weather.heat_risk_level >= 3 or vulnerable_or_critical:
            notes.append(
                "Heat-risk workflow requires occupant safety review before cost optimization."
            )
        return notes

    def _real_world_basis(
        self,
        weather: WeatherEvent,
        pricing: UtilityPricingEvent,
    ) -> list[str]:
        basis = [
            (
                "DOE/NREL grid-interactive efficient buildings: use demand "
                "flexibility from controllable building loads."
            ),
            (
                "OSHA/NIOSH heat stress guidance: workplace heat hazards "
                "require controls that reduce heat exposure."
            ),
        ]
        if weather.heat_risk_level >= 3:
            basis.append(
                "NOAA/NWS HeatRisk: high and extreme heat levels indicate "
                "elevated heat-health risk."
            )
        if pricing.demand_response_requested_kw > 0:
            basis.append(
                "Utility demand response: reduce load during peak events "
                "without violating safety constraints."
            )
        return basis

    def _actions(
        self,
        building: BuildingProfile,
        weather: WeatherEvent,
        pricing: UtilityPricingEvent,
        primary: EnergyPriority,
        source_ids: list[str],
    ) -> list[EnergyAction]:
        actions = [
            EnergyAction(
                action_id=f"action-{_stable_id('setpoint', *source_ids)}",
                title="Set HVAC policy for occupied and critical zones",
                priority=primary,
                explanation=(
                    "Resolve comfort versus cost using explicit safety-first priority rules."
                ),
                source_ids=source_ids,
            )
        ]
        if pricing.demand_response_requested_kw > 0:
            actions.append(
                EnergyAction(
                    action_id=f"action-{_stable_id('shed', *source_ids)}",
                    title="Shed flexible loads without touching critical zones",
                    priority=EnergyPriority.cost
                    if primary != EnergyPriority.safety
                    else EnergyPriority.safety,
                    explanation=(
                        "Use flexible loads for demand response; "
                        "critical HVAC zones remain protected."
                    ),
                    source_ids=[building.building_id, pricing.pricing_event_id],
                )
            )
        if weather.severity in {"high", "extreme"}:
            actions.append(
                EnergyAction(
                    action_id=f"action-{_stable_id('monitor', *source_ids)}",
                    title="Increase weather and grid monitoring cadence",
                    priority=EnergyPriority.resilience,
                    explanation=(
                        "Rare weather events can change grid and comfort constraints quickly."
                    ),
                    source_ids=[weather.event_id],
                )
            )
        return actions
