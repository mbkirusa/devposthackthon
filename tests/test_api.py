import shutil
from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from startup_ops_agent.api import app
from startup_ops_agent.config import default_data_dir


def _isolated_data_dir(tmp_path: Path, monkeypatch: MonkeyPatch) -> Path:
    for path in default_data_dir().iterdir():
        if path.is_file():
            shutil.copy(path, tmp_path / path.name)
    monkeypatch.setenv("STARTUP_OPS_DATA_DIR", str(tmp_path))
    return tmp_path


def test_healthz() -> None:
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_account_brief_endpoint_returns_source_backed_risks(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    _isolated_data_dir(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/v1/account-brief",
        json={
            "account_id": "acme-robotics",
            "actor_id": "founder-001",
            "actor_role": "founder",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["account"]["account_id"] == "acme-robotics"
    assert {risk["category"] for risk in payload["risk_signals"]} >= {"renewal", "support"}


def test_energy_plan_endpoint_returns_b2b_conflict_plan(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    _isolated_data_dir(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/v1/energy-plan",
        json={
            "building_id": "bldg-medtech-hq",
            "weather_event_id": "weather-heat-dome",
            "pricing_event_id": "pricing-peak-surge",
            "occupancy_id": "occupancy-business-critical",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["primary_priority"] == "safety"
    assert payload["conflicts"] == ["extreme_weather_peak_pricing"]
    assert {decision["load_id"] for decision in payload["load_shed"]} == {
        "cafeteria-cooling",
        "conference-preconditioning",
    }
    assert payload["safety_invariants_passed"] is True
    assert payload["safety_violations"] == []
    assert [step["step"] for step in payload["trace"]][0] == "retrieve_context"


def test_energy_portfolio_endpoint_protects_critical_building(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    _isolated_data_dir(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.post(
        "/v1/energy-portfolio",
        json={
            "weather_event_id": "weather-heat-dome",
            "pricing_event_id": "pricing-grid-emergency",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["target_met"] is True
    assert payload["protected_buildings"] == ["bldg-medtech-hq"]
    assert payload["total_co2_avoided_kg"] > 0
    assert payload["total_cost_avoidance_usd"] > 0


def test_evaluations_endpoint_reports_passing_quality_gate(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    _isolated_data_dir(tmp_path, monkeypatch)
    client = TestClient(app)

    response = client.get("/v1/evaluations")

    assert response.status_code == 200
    payload = response.json()
    assert payload["failed"] == 0
    assert payload["passed"] == payload["total"]


def test_enterprise_manifest_endpoint_is_track2_focused() -> None:
    client = TestClient(app)

    response = client.get("/v1/enterprise-manifest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["display_name"] == "Energy Ops Agent"
    assert payload["track"] == "Optimize (Existing Agents)"
    assert payload["deployment_target"] == "Google Cloud Run"
    assert payload["primary_endpoint"] == "/v1/energy-plan"
    assert payload["a2a_agent_card"] == "/.well-known/agent-card.json"
    assert "deterministic safety-first conflict resolution" in payload["controls"]
