# Energy Operations Reliability Platform

Energy Operations Reliability Platform helps facilities and energy teams make
safe, auditable building-control decisions during rare grid and weather events.
It is designed for B2B operators responsible for occupant safety, critical-zone
continuity, and demand-response cost control.

The reference scenario is a medical-technology headquarters facing an extreme
heat event at the same time as a utility peak-demand pricing surge. The system
resolves the conflict by protecting critical occupants first, preserving
critical-zone comfort, and shedding named non-critical loads before touching
HVAC constraints.

## Business Use Case

B2B facilities teams often need to reduce demand charges, but a cost-only
response can create unacceptable operational risk. This project gives operators
a repeatable way to answer:

- Which building controls can be adjusted safely?
- Which loads should be shed first?
- What financial impact is expected?
- Which policy, weather, pricing, and occupancy records support the decision?
- How did the system resolve the comfort-versus-cost conflict?

## Operating Outcome

For the heat-dome plus peak-pricing scenario, the system returns:

- primary priority: `safety`
- critical-zone setpoint: `23.0 C`
- expected non-critical load shed: `21.6 kW`
- selected loads: `cafeteria-cooling`, `conference-preconditioning`
- estimated demand-response cost avoidance: `$3,447.36`
- estimated protected business risk: `$9,000.00`
- conflict detected: `extreme_weather_peak_pricing`
- trace steps: `retrieve_context`, `resolve_conflict`

## Core Capabilities

- Source-backed scenario resolution from business language to internal records.
- Safety-first conflict resolution for extreme weather and peak pricing.
- Load-level demand-response planning using building-specific capacity data.
- Critical-zone policy enforcement before HVAC setpoint relaxation.
- Simulation coverage for normal-day and rare-event operating cases.
- Readiness evaluation for instruction coverage, orchestration, simulation, and
  B2B business-impact evidence.
- Cloud Run and A2A-ready runtime packaging for enterprise integration.

## System Components

The production logic is intentionally split by responsibility:

- `EnergyOptimizationService`: deterministic business rules and calculations.
- `EnergyJsonRepository`: local source-backed building, weather, pricing, and
  occupancy records.
- `energy_scenario_plan`: resolves natural-language scenarios into known
  records and returns a complete energy plan.
- `energy_optimization_plan`: builds a plan when exact record IDs are provided.
- `energy_simulation`: runs synthetic rare-event simulations and returns trace
  steps.

The current ADK runtime lives in `startup_ops_agent/agent.py` and coordinates:

- `energy_ops_agent`
- `weather_pricing_grounding_agent`
- `comfort_cost_conflict_agent`
- `energy_action_governance_agent`

## Architecture

Submission-ready diagram assets are available in:

- `docs/architecture-diagram.png`
- `docs/architecture-diagram.svg`
- `docs/architecture-diagram.dot`

See `docs/architecture.md` for the full architecture notes.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Create `startup_ops_agent/.env` from `startup_ops_agent/.env.example` and add
your local Google credentials. Do not commit real keys.

## Run A Business Scenario

Natural-language scenario:

```powershell
python -m startup_ops_agent.cli energy-scenario `
  --scenario "Optimize MedTech HQ during the heat dome and peak-demand surge. Prioritize critical occupants and show the observability trace."
```

Exact record IDs:

```powershell
python -m startup_ops_agent.cli energy-plan `
  --building bldg-medtech-hq `
  --weather weather-heat-dome `
  --pricing pricing-peak-surge `
  --occupancy occupancy-business-critical
```

## Run Reliability Checks

```powershell
python -m startup_ops_agent.cli simulate-energy
python -m startup_ops_agent.cli evaluate --output reports/evaluation.json
```

Expected readiness result:

```json
{
  "total": 4,
  "passed": 4,
  "failed": 0
}
```

## Run Local Web Demo

```powershell
adk web startup_ops_agent --port 8000 --no-reload
```

Open `http://127.0.0.1:8000` and test:

```text
Optimize MedTech HQ during the heat dome and peak-demand surge. Prioritize critical occupants and show the observability trace.
```

## Run A2A Runtime

```powershell
uvicorn startup_ops_agent.a2a_app:a2a_app --host 127.0.0.1 --port 8081
```

Agent card:

```text
http://localhost:8081/.well-known/agent-card.json
```

## Test

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
pytest
ruff check .
```

## Submission References

- `docs/submission.md`
- `docs/architecture.md`
- `docs/track2-optimization.md`
- `docs/evaluation-plan.md`
- `docs/demo-script.md`
