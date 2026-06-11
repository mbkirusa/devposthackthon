# Energy Ops Agent

Track: **Optimize (Existing Agents)**

Energy Ops Agent is an optimized ADK multi-agent system for B2B building energy
operations. The existing agent system has been refactored and stress-tested for
rare real-world conflicts: an extreme weather event happening at the same time a
utility provider issues peak-demand surge pricing.

The optimized system uses:

- ADK root agent plus specialist sub-agents
- MCP tools for grounded building, weather, pricing, and occupancy context
- deterministic conflict-resolution service for safety-critical decisions
- portfolio demand-response optimizer that meets a grid-wide load-shed target
  across multiple buildings while protecting safety-critical sites
- carbon accounting: every plan reports estimated CO2 avoided from grid
  marginal emissions alongside dollar cost avoidance
- 9 synthetic Agent Simulation cases spanning heat dome, cold snap, storm,
  near-miss, and grid-emergency events (safety/comfort/cost/resilience outcomes)
- a six-step observability trace on every plan (context → conflict → priority →
  load-shed → safety check → impact), plus a fleet-level portfolio trace
- runtime safety invariants surfaced as proof on every plan (critical-zone loads
  never shed, setpoints within safe bounds) with fail-closed enforcement
- fail-fast model validation that rejects malformed building/weather/pricing data
- a quantitative evaluation metrics report (pass rate, safety violations,
  priority distribution, decision latency, source-ID preservation)
- instruction optimizer checks for stalled comfort-versus-cost logic
- building-specific controllable-load capacity and B2B financial impact fields
- A2A runtime wrapper for enterprise agent interoperability

## Existing Agents

The current agents live in `startup_ops_agent/agent.py`:

- `energy_ops_agent`: root orchestrator
- `weather_pricing_grounding_agent`: retrieves grounded weather, pricing,
  occupancy, and building context
- `comfort_cost_conflict_agent`: reasons over comfort, safety, and energy cost
  conflicts
- `energy_action_governance_agent`: recommends safe HVAC and flexible-load
  actions without violating critical-zone constraints

## Track 2 Scenario

The hard case is:

```text
Extreme heat dome + peak-demand utility surge + critical building occupancy
```

The optimized behavior is:

1. Detect the conflict between occupant safety and energy cost.
2. Prioritize safety and critical-zone comfort.
3. Shed flexible loads before changing critical-zone HVAC.
4. Return the named non-critical loads selected for demand response.
5. Preserve source IDs from weather, pricing, building, and occupancy records.
6. Emit a trace showing context retrieval and conflict resolution.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Set your Gemini key in `startup_ops_agent/.env`:

```text
GOOGLE_API_KEY="your-key"
```

Do not commit real keys.

## Run The Optimized Energy Plan

Natural-language scenario resolver:

```powershell
python -m startup_ops_agent.cli energy-scenario `
  --scenario "Optimize MedTech HQ during the heat dome and peak-demand surge. Prioritize critical occupants and show the observability trace."
```

Exact IDs:

```powershell
python -m startup_ops_agent.cli energy-plan `
  --building bldg-medtech-hq `
  --weather weather-heat-dome `
  --pricing pricing-peak-surge `
  --occupancy occupancy-business-critical
```

## Run Portfolio Optimization

Meet a grid-wide demand-response target across the whole building portfolio.
Flexible load is shed from lower-business-risk buildings first, and
safety-critical buildings are protected (shed last, non-critical loads only):

```powershell
python -m startup_ops_agent.cli energy-portfolio `
  --weather weather-heat-dome `
  --pricing pricing-grid-emergency
```

The plan reports the fleet load-shed allocation per building, the dollar cost
avoided, and the estimated CO2 avoided, and names the protected critical sites.

## Run Agent Simulation

```powershell
python -m startup_ops_agent.cli simulate-energy
```

## Run Readiness Evaluation

```powershell
python -m startup_ops_agent.cli evaluate --output reports/evaluation.json
```

The readiness evaluation is Track 2-focused: instruction contract, multi-agent
structure, rare-event simulation, B2B business-impact evidence, and portfolio
demand-response that protects critical buildings while reporting cost and CO2
avoidance.

## Run With ADK

```powershell
adk web startup_ops_agent --port 8000 --no-reload
```

Try:

```text
Optimize MedTech HQ during the heat dome and peak-demand surge. Prioritize
critical occupants and explain the observability trace.
```

## A2A Runtime

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

## Submission Assets

- [Architecture](docs/architecture.md)
- [Track 2 optimization plan](docs/track2-optimization.md)
- [Evaluation plan](docs/evaluation-plan.md)
- [Demo script](docs/demo-script.md)
