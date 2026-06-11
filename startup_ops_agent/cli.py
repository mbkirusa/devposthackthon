from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from startup_ops_agent.config import default_data_dir
from startup_ops_agent.energy_repository import EnergyJsonRepository
from startup_ops_agent.energy_service import EnergyOptimizationService
from startup_ops_agent.evaluation import run_evaluations, write_report
from startup_ops_agent.logging_config import configure_logging
from startup_ops_agent.optimizer import optimize_energy_instructions
from startup_ops_agent.policy import parse_actor
from startup_ops_agent.repository import JsonRepository
from startup_ops_agent.service import StartupOpsService


def weekly_plan(account_id: str, actor_id: str, role: str, data_dir: Path) -> dict:
    actor = parse_actor(actor_id, role)
    service = StartupOpsService(JsonRepository(data_dir))
    brief = service.build_account_brief(account_id=account_id, actor=actor, today=date.today())
    created_tasks = []
    for action in brief.recommended_actions:
        if action.action_type.value == "create_task":
            task = service.create_task_draft(
                account_id=account_id,
                actor=actor,
                title=action.title,
                action_type=action.action_type,
                source_ids=action.source_ids,
            )
            created_tasks.append(task.model_dump(mode="json"))
    return {
        "account": brief.account.model_dump(mode="json"),
        "risk_signals": [risk.model_dump(mode="json") for risk in brief.risk_signals],
        "recommended_actions": [
            action.model_dump(mode="json") for action in brief.recommended_actions
        ],
        "draft_tasks_created_or_reused": created_tasks,
    }


def energy_plan(
    building_id: str,
    weather_event_id: str,
    pricing_event_id: str,
    occupancy_id: str,
    data_dir: Path,
) -> dict:
    service = EnergyOptimizationService(EnergyJsonRepository(data_dir))
    plan = service.build_optimization_plan(
        building_id=building_id,
        weather_event_id=weather_event_id,
        pricing_event_id=pricing_event_id,
        occupancy_id=occupancy_id,
    )
    return plan.model_dump(mode="json")


def energy_scenario(scenario: str, data_dir: Path) -> dict:
    service = EnergyOptimizationService(EnergyJsonRepository(data_dir))
    result = service.build_plan_from_scenario(scenario)
    return {
        "resolved_inputs": result["resolved_inputs"],
        "resolution_notes": result["resolution_notes"],
        "plan": result["plan"].model_dump(mode="json"),
    }


def energy_portfolio(weather_event_id: str, pricing_event_id: str, data_dir: Path) -> dict:
    service = EnergyOptimizationService(EnergyJsonRepository(data_dir))
    plan = service.build_portfolio_plan(
        weather_event_id=weather_event_id,
        pricing_event_id=pricing_event_id,
    )
    return plan.model_dump(mode="json")


def energy_simulations(data_dir: Path) -> dict:
    service = EnergyOptimizationService(EnergyJsonRepository(data_dir))
    results = service.run_all_simulations()
    return {
        "total": len(results),
        "passed": sum(1 for result in results if result.passed),
        "failed": sum(1 for result in results if not result.passed),
        "results": [result.model_dump(mode="json") for result in results],
    }


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Startup Ops Agent deterministic demo CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    weekly = subparsers.add_parser("weekly-plan")
    weekly.add_argument("--account", required=True)
    weekly.add_argument("--actor-id", default="founder-001")
    weekly.add_argument("--role", default="founder", choices=["founder", "operator", "viewer"])
    weekly.add_argument("--data-dir", type=Path, default=default_data_dir())

    energy = subparsers.add_parser("energy-plan")
    energy.add_argument("--building", required=True)
    energy.add_argument("--weather", required=True)
    energy.add_argument("--pricing", required=True)
    energy.add_argument("--occupancy", required=True)
    energy.add_argument("--data-dir", type=Path, default=default_data_dir())

    scenario = subparsers.add_parser("energy-scenario")
    scenario.add_argument("--scenario", required=True)
    scenario.add_argument("--data-dir", type=Path, default=default_data_dir())

    portfolio = subparsers.add_parser("energy-portfolio")
    portfolio.add_argument("--weather", required=True)
    portfolio.add_argument("--pricing", required=True)
    portfolio.add_argument("--data-dir", type=Path, default=default_data_dir())

    simulate = subparsers.add_parser("simulate-energy")
    simulate.add_argument("--data-dir", type=Path, default=default_data_dir())

    optimize = subparsers.add_parser("optimize-energy-instruction")
    optimize.add_argument("--instruction", required=True)

    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--data-dir", type=Path, default=default_data_dir())
    evaluate.add_argument("--output", type=Path)

    args = parser.parse_args()
    if args.command == "weekly-plan":
        result = weekly_plan(
            account_id=args.account,
            actor_id=args.actor_id,
            role=args.role,
            data_dir=args.data_dir.resolve(),
        )
        print(json.dumps(result, indent=2))
    elif args.command == "evaluate":
        report = run_evaluations(data_dir=args.data_dir.resolve())
        if args.output:
            write_report(args.output.resolve(), report)
        print(json.dumps(report.to_dict(), indent=2))
        if report.failed:
            raise SystemExit(1)
    elif args.command == "energy-plan":
        result = energy_plan(
            building_id=args.building,
            weather_event_id=args.weather,
            pricing_event_id=args.pricing,
            occupancy_id=args.occupancy,
            data_dir=args.data_dir.resolve(),
        )
        print(json.dumps(result, indent=2))
    elif args.command == "energy-scenario":
        result = energy_scenario(
            scenario=args.scenario,
            data_dir=args.data_dir.resolve(),
        )
        print(json.dumps(result, indent=2))
    elif args.command == "energy-portfolio":
        result = energy_portfolio(
            weather_event_id=args.weather,
            pricing_event_id=args.pricing,
            data_dir=args.data_dir.resolve(),
        )
        print(json.dumps(result, indent=2))
    elif args.command == "simulate-energy":
        result = energy_simulations(data_dir=args.data_dir.resolve())
        print(json.dumps(result, indent=2))
        if result["failed"]:
            raise SystemExit(1)
    elif args.command == "optimize-energy-instruction":
        print(json.dumps(optimize_energy_instructions(args.instruction), indent=2))



if __name__ == "__main__":
    main()
