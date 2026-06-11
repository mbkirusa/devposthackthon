from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from startup_ops_agent.config import load_settings
from startup_ops_agent.energy_models import EnergyOptimizationPlan, PortfolioOptimizationPlan
from startup_ops_agent.energy_repository import EnergyJsonRepository
from startup_ops_agent.energy_service import EnergyOptimizationService
from startup_ops_agent.evaluation import run_evaluations
from startup_ops_agent.logging_config import configure_logging
from startup_ops_agent.models import AccountBrief
from startup_ops_agent.policy import PermissionDeniedError, parse_actor
from startup_ops_agent.repository import DataAccessError, JsonRepository
from startup_ops_agent.service import NotFoundError, StartupOpsService

configure_logging()

app = FastAPI(
    title="Energy Ops Agent API",
    version="0.1.0",
    description="Cloud Run-ready control plane for the ADK Track 2 Energy Ops Agent.",
)


class AccountBriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    actor_id: str = "founder-001"
    actor_role: str = "founder"


class EnergyPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    building_id: str
    weather_event_id: str
    pricing_event_id: str
    occupancy_id: str


class EnergyPortfolioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weather_event_id: str
    pricing_event_id: str


class EvaluationResponse(BaseModel):
    total: int
    passed: int
    failed: int
    results: list[dict[str, object]]


class EnterpriseManifest(BaseModel):
    name: str
    display_name: str
    track: str
    deployment_target: str
    health_endpoint: str
    primary_endpoint: str
    readiness_endpoint: str
    controls: list[str]
    a2a_agent_card: str
    agent_runtime_target: str
    intelligence: str
    orchestration: str


def _service() -> StartupOpsService:
    return StartupOpsService(JsonRepository(load_settings().data_dir))


def _energy_service() -> EnergyOptimizationService:
    return EnergyOptimizationService(EnergyJsonRepository(load_settings().data_dir))


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/enterprise-manifest", response_model=EnterpriseManifest)
def enterprise_manifest() -> dict[str, object]:
    return {
        "name": "energy-ops-agent",
        "display_name": "Energy Ops Agent",
        "track": "Optimize (Existing Agents)",
        "deployment_target": "Google Cloud Run",
        "health_endpoint": "/healthz",
        "primary_endpoint": "/v1/energy-plan",
        "readiness_endpoint": "/v1/evaluations",
        "a2a_agent_card": "/.well-known/agent-card.json",
        "agent_runtime_target": "ADK Web, A2A runtime, or Agent Engine",
        "intelligence": "Gemini API via Google ADK",
        "orchestration": "Google Agent Development Kit multi-agent system",
        "controls": [
            "source ID preservation",
            "deterministic safety-first conflict resolution",
            "load-level demand-response decisions",
            "portfolio-wide demand-response allocation that protects critical buildings",
            "cost and CO2 avoidance accounting",
            "observability trace evaluation",
            "instruction optimization quality gate",
        ],
    }


@app.post("/v1/account-brief", response_model=AccountBrief)
def account_brief(request: AccountBriefRequest) -> AccountBrief:
    try:
        actor = parse_actor(request.actor_id, request.actor_role)
        return _service().build_account_brief(
            account_id=request.account_id,
            actor=actor,
            today=date.today(),
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DataAccessError as exc:
        raise HTTPException(status_code=500, detail="Data access failed.") from exc


@app.post("/v1/energy-plan", response_model=EnergyOptimizationPlan)
def energy_plan(request: EnergyPlanRequest) -> EnergyOptimizationPlan:
    try:
        return _energy_service().build_optimization_plan(
            building_id=request.building_id,
            weather_event_id=request.weather_event_id,
            pricing_event_id=request.pricing_event_id,
            occupancy_id=request.occupancy_id,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DataAccessError as exc:
        raise HTTPException(status_code=500, detail="Data access failed.") from exc


@app.post("/v1/energy-portfolio", response_model=PortfolioOptimizationPlan)
def energy_portfolio(request: EnergyPortfolioRequest) -> PortfolioOptimizationPlan:
    try:
        return _energy_service().build_portfolio_plan(
            weather_event_id=request.weather_event_id,
            pricing_event_id=request.pricing_event_id,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DataAccessError as exc:
        raise HTTPException(status_code=500, detail="Data access failed.") from exc


@app.get("/v1/evaluations", response_model=EvaluationResponse)
def evaluations() -> dict[str, object]:
    return run_evaluations().to_dict()
