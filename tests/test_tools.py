from __future__ import annotations

import shutil
from pathlib import Path

from startup_ops_agent.config import default_data_dir
from startup_ops_agent.tools import (
    build_account_brief,
    build_energy_optimization_plan,
    build_energy_plan_from_scenario,
    create_task_draft,
    explain_operating_policy,
    run_energy_simulation,
)


def _copy_data_dir(tmp_path: Path) -> Path:
    for path in default_data_dir().iterdir():
        if path.is_file():
            shutil.copy(path, tmp_path / path.name)
    return tmp_path


def test_tool_returns_safe_error_for_unknown_role(tmp_path: Path, monkeypatch) -> None:
    data_dir = _copy_data_dir(tmp_path)
    monkeypatch.setenv("STARTUP_OPS_DATA_DIR", str(data_dir))

    result = build_account_brief("acme-robotics", "actor-1", "admin")

    assert result["status"] == "error"
    assert result["error_type"] == "PermissionDeniedError"


def test_task_tool_returns_draft_note(tmp_path: Path, monkeypatch) -> None:
    data_dir = _copy_data_dir(tmp_path)
    monkeypatch.setenv("STARTUP_OPS_DATA_DIR", str(data_dir))

    result = create_task_draft(
        account_id="acme-robotics",
        actor_id="founder-001",
        actor_role="founder",
        title="Escalate unresolved customer support risk",
        action_type="create_task",
        source_ids=["sup-acme-sso"],
    )

    assert result["status"] == "success"
    assert result["task"]["status"] == "draft"
    assert "draft-only" in result["note"]


def test_policy_tool_reports_approval_actions() -> None:
    result = explain_operating_policy("operator")

    assert result["status"] == "success"
    assert result["capabilities"] == ["create_task", "draft_email"]
    assert "update_stage" in result["approval_required"]


def test_energy_plan_tool_handles_extreme_weather_peak_pricing(tmp_path: Path, monkeypatch) -> None:
    data_dir = _copy_data_dir(tmp_path)
    monkeypatch.setenv("STARTUP_OPS_DATA_DIR", str(data_dir))

    result = build_energy_optimization_plan(
        building_id="bldg-medtech-hq",
        weather_event_id="weather-heat-dome",
        pricing_event_id="pricing-peak-surge",
        occupancy_id="occupancy-business-critical",
    )

    assert result["status"] == "success"
    assert result["plan"]["primary_priority"] == "safety"


def test_energy_scenario_tool_resolves_demo_prompt(tmp_path: Path, monkeypatch) -> None:
    data_dir = _copy_data_dir(tmp_path)
    monkeypatch.setenv("STARTUP_OPS_DATA_DIR", str(data_dir))

    result = build_energy_plan_from_scenario(
        "Optimize MedTech HQ during the heat dome and peak-demand surge. "
        "Prioritize critical occupants and show the observability trace."
    )

    assert result["status"] == "success"
    assert result["resolved_inputs"]["building_id"] == "bldg-medtech-hq"
    assert result["resolved_inputs"]["weather_event_id"] == "weather-heat-dome"
    assert result["resolved_inputs"]["pricing_event_id"] == "pricing-peak-surge"
    assert result["resolved_inputs"]["occupancy_id"] == "occupancy-business-critical"
    assert result["plan"]["primary_priority"] == "safety"


def test_energy_simulation_tool_returns_trace(tmp_path: Path, monkeypatch) -> None:
    data_dir = _copy_data_dir(tmp_path)
    monkeypatch.setenv("STARTUP_OPS_DATA_DIR", str(data_dir))

    result = run_energy_simulation("heat-dome-peak-price-critical-occupancy")

    assert result["status"] == "success"
    assert result["result"]["passed"] is True
    assert [step["step"] for step in result["result"]["trace"]] == [
        "retrieve_context",
        "detect_conflict",
        "evaluate_priority",
        "allocate_load_shed",
        "governance_safety_check",
        "compute_impact",
    ]
