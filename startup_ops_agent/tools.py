from __future__ import annotations

from datetime import date

from startup_ops_agent.config import load_settings
from startup_ops_agent.energy_repository import EnergyJsonRepository
from startup_ops_agent.energy_service import EnergyOptimizationService
from startup_ops_agent.logging_config import configure_logging
from startup_ops_agent.models import ActionType
from startup_ops_agent.optimizer import optimize_energy_instructions
from startup_ops_agent.policy import PermissionDeniedError, parse_actor
from startup_ops_agent.repository import DataAccessError, JsonRepository
from startup_ops_agent.service import NotFoundError, StartupOpsService

configure_logging()


def _service() -> StartupOpsService:
    settings = load_settings()
    return StartupOpsService(JsonRepository(settings.data_dir))


def _energy_service() -> EnergyOptimizationService:
    settings = load_settings()
    return EnergyOptimizationService(EnergyJsonRepository(settings.data_dir))


def build_account_brief(account_id: str, actor_id: str, actor_role: str) -> dict:
    """Build a source-backed account brief with risk signals and recommended actions."""
    try:
        actor = parse_actor(actor_id, actor_role)
        brief = _service().build_account_brief(account_id=account_id, actor=actor)
        return {"status": "success", "brief": brief.model_dump(mode="json")}
    except (DataAccessError, NotFoundError, PermissionDeniedError, ValueError) as exc:
        return {"status": "error", "error_type": exc.__class__.__name__, "message": str(exc)}


def create_task_draft(
    account_id: str,
    actor_id: str,
    actor_role: str,
    title: str,
    action_type: str,
    source_ids: list[str],
) -> dict:
    """Create or reuse an idempotent draft task for a recommended account action."""
    try:
        actor = parse_actor(actor_id, actor_role)
        task = _service().create_task_draft(
            account_id=account_id,
            actor=actor,
            title=title,
            action_type=ActionType(action_type),
            source_ids=source_ids,
        )
        return {
            "status": "success",
            "task": task.model_dump(mode="json"),
            "note": "External side effects remain draft-only until a human approves them.",
        }
    except (DataAccessError, NotFoundError, PermissionDeniedError, ValueError) as exc:
        return {"status": "error", "error_type": exc.__class__.__name__, "message": str(exc)}


def explain_operating_policy(actor_role: str) -> dict:
    """Explain what the configured role can do and what requires approval."""
    try:
        actor = parse_actor("policy-preview", actor_role)
    except PermissionDeniedError as exc:
        return {"status": "error", "error_type": exc.__class__.__name__, "message": str(exc)}

    capabilities = {
        "founder": ["create_task", "draft_email", "update_stage"],
        "operator": ["create_task", "draft_email"],
        "viewer": [],
    }[actor.role.value]
    return {
        "status": "success",
        "role": actor.role.value,
        "capabilities": capabilities,
        "approval_required": ["draft_email", "update_stage"],
        "policy_date": date.today().isoformat(),
    }


def build_energy_optimization_plan(
    building_id: str,
    weather_event_id: str,
    pricing_event_id: str,
    occupancy_id: str,
) -> dict:
    """Build a source-backed building energy plan for weather and utility pricing conflicts."""
    try:
        plan = _energy_service().build_optimization_plan(
            building_id=building_id,
            weather_event_id=weather_event_id,
            pricing_event_id=pricing_event_id,
            occupancy_id=occupancy_id,
        )
        return {"status": "success", "plan": plan.model_dump(mode="json")}
    except (DataAccessError, NotFoundError, ValueError) as exc:
        return {"status": "error", "error_type": exc.__class__.__name__, "message": str(exc)}


def build_energy_portfolio_plan(weather_event_id: str, pricing_event_id: str) -> dict:
    """Meet a grid-wide demand-response target across the whole building portfolio.

    Sheds flexible load from lower-business-risk buildings first and protects
    safety-critical buildings. Reports fleet cost and CO2 avoidance.
    """
    try:
        plan = _energy_service().build_portfolio_plan(
            weather_event_id=weather_event_id,
            pricing_event_id=pricing_event_id,
        )
        return {"status": "success", "portfolio_plan": plan.model_dump(mode="json")}
    except (DataAccessError, NotFoundError, ValueError) as exc:
        return {"status": "error", "error_type": exc.__class__.__name__, "message": str(exc)}


def build_energy_plan_from_scenario(scenario: str) -> dict:
    """Resolve a natural-language B2B energy scenario and build a source-backed plan."""
    try:
        result = _energy_service().build_plan_from_scenario(scenario)
        return {
            "status": "success",
            "resolved_inputs": result["resolved_inputs"],
            "resolution_notes": result["resolution_notes"],
            "plan": result["plan"].model_dump(mode="json"),
        }
    except (DataAccessError, NotFoundError, ValueError) as exc:
        return {"status": "error", "error_type": exc.__class__.__name__, "message": str(exc)}


def run_energy_simulation(case_id: str) -> dict:
    """Run a synthetic Track 2 simulation case and return the observability trace."""
    try:
        result = _energy_service().run_simulation_case(case_id)
        return {"status": "success", "result": result.model_dump(mode="json")}
    except (DataAccessError, NotFoundError, ValueError) as exc:
        return {"status": "error", "error_type": exc.__class__.__name__, "message": str(exc)}


def optimize_energy_agent_instruction(instruction: str) -> dict:
    """Programmatically refine instructions for rare weather and peak-pricing conflicts."""
    return {"status": "success", "optimization": optimize_energy_instructions(instruction)}
