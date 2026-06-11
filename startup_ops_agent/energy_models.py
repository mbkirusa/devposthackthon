from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EnergyPriority(StrEnum):
    safety = "safety"
    comfort = "comfort"
    cost = "cost"
    resilience = "resilience"


class FlexibleLoad(BaseModel):
    model_config = ConfigDict(extra="forbid")

    load_id: str
    description: str
    zones: list[str]
    max_shed_kw: float = Field(ge=0)


class BuildingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    building_id: str
    name: str
    tenant_id: str
    business_type: str
    hvac_zones: list[str]
    critical_zones: list[str]
    flexible_loads: list[FlexibleLoad]
    normal_setpoint_c: float
    max_safe_setpoint_c: float
    min_safe_setpoint_c: float
    business_value_at_risk_usd_per_hour: float = Field(ge=0)
    business_risk_protection_factor: float = Field(ge=0, le=1)
    critical_zone_policy: str

    @model_validator(mode="after")
    def _check_building_consistency(self) -> BuildingProfile:
        if not self.min_safe_setpoint_c <= self.normal_setpoint_c <= self.max_safe_setpoint_c:
            raise ValueError(
                "Setpoints must satisfy min_safe <= normal <= max_safe for "
                f"building {self.building_id}."
            )
        unknown_critical = set(self.critical_zones) - set(self.hvac_zones)
        if unknown_critical:
            raise ValueError(
                f"Critical zones {sorted(unknown_critical)} are not declared HVAC zones "
                f"for building {self.building_id}."
            )
        load_ids = [load.load_id for load in self.flexible_loads]
        if len(load_ids) != len(set(load_ids)):
            raise ValueError(f"Flexible load IDs must be unique for building {self.building_id}.")
        return self


class WeatherEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    kind: Literal["normal", "heat_wave", "cold_snap", "storm"]
    severity: Literal["low", "medium", "high", "extreme"]
    forecast_start: datetime
    forecast_end: datetime
    outdoor_temp_c: float
    heat_risk_level: int = Field(ge=0, le=4)
    grid_risk: Literal["low", "medium", "high"]
    source: str

    @model_validator(mode="after")
    def _check_window(self) -> WeatherEvent:
        if self.forecast_end < self.forecast_start:
            raise ValueError(f"forecast_end precedes forecast_start for weather {self.event_id}.")
        return self


class UtilityPricingEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pricing_event_id: str
    provider: str
    starts_at: datetime
    ends_at: datetime
    price_multiplier: float = Field(ge=1.0)
    demand_response_requested_kw: float = Field(ge=0)
    demand_charge_usd_per_kw: float = Field(ge=0)
    marginal_emissions_kg_per_kwh: float = Field(default=0.42, ge=0)
    source: str

    @property
    def duration_hours(self) -> float:
        return max((self.ends_at - self.starts_at).total_seconds() / 3600.0, 0.0)

    @model_validator(mode="after")
    def _check_window(self) -> UtilityPricingEvent:
        if self.ends_at < self.starts_at:
            raise ValueError(f"ends_at precedes starts_at for pricing {self.pricing_event_id}.")
        return self


class OccupancyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occupancy_id: str
    building_id: str
    occupied_zones: list[str]
    vulnerable_occupants: bool
    business_hours: bool


class EnergyAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    title: str
    priority: EnergyPriority
    explanation: str
    source_ids: list[str]


class LoadShedDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    load_id: str
    shed_kw: float = Field(ge=0)
    reason: str


class TraceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: str
    decision: str
    reason: str
    source_ids: list[str]


class SafetyViolation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    detail: str
    source_ids: list[str]


class EnergyOptimizationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    building_id: str
    decision: str
    primary_priority: EnergyPriority
    setpoint_c: float
    expected_load_shed_kw: float
    load_shed: list[LoadShedDecision]
    estimated_cost_avoidance_usd: float
    estimated_co2_avoided_kg: float
    estimated_business_risk_avoided_usd: float
    actions: list[EnergyAction]
    conflicts: list[str]
    compliance_notes: list[str]
    real_world_basis: list[str]
    trace: list[TraceStep]
    safety_invariants_passed: bool
    safety_violations: list[SafetyViolation]
    source_ids: list[str]


class SimulationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    building_id: str
    weather_event_id: str
    pricing_event_id: str
    occupancy_id: str
    expected_primary_priority: EnergyPriority
    expected_conflict: bool
    expected_setpoint_c: float | None = None
    expect_no_critical_load_shed: bool = True


class SimulationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    passed: bool
    plan: EnergyOptimizationPlan
    trace: list[TraceStep]
    failure_reason: str | None = None


class BuildingContribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    building_id: str
    name: str
    primary_priority: EnergyPriority
    sheddable_capacity_kw: float = Field(ge=0)
    allocated_shed_kw: float = Field(ge=0)
    load_shed: list[LoadShedDecision]
    estimated_cost_avoidance_usd: float
    estimated_co2_avoided_kg: float
    business_value_at_risk_usd_per_hour: float = Field(ge=0)
    protected: bool
    reason: str
    source_ids: list[str]


class PortfolioOptimizationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolio_plan_id: str
    weather_event_id: str
    pricing_event_id: str
    fleet_demand_response_target_kw: float = Field(ge=0)
    total_allocated_shed_kw: float = Field(ge=0)
    target_met: bool
    unmet_shed_kw: float = Field(ge=0)
    total_cost_avoidance_usd: float
    total_co2_avoided_kg: float
    total_business_risk_avoided_usd: float
    protected_buildings: list[str]
    contributions: list[BuildingContribution]
    allocation_notes: list[str]
    trace: list[TraceStep]
    source_ids: list[str]
