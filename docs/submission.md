# Submission Brief

## Project Name

Energy Ops Agent

## Theme

Optimize (Existing Agents)

## Region

AMERS

## One-Liner

An existing ADK multi-agent energy operations agent optimized with simulation,
observability traces, and instruction optimization for the rare collision of
extreme weather and utility peak-demand pricing.

## Problem

B2B facilities and energy teams need to reduce demand charges, but real
buildings cannot optimize for cost alone. During extreme weather, the same
controls that reduce energy spend can endanger occupants or critical zones. The
agent worked on normal days but needed rigorous optimization for this rare,
multi-variable conflict.

## Solution

Energy Ops Agent now uses synthetic Agent Simulation cases, observability trace
steps, and optimizer checks to handle the conflict deterministically:

- extreme heat dome
- peak-demand pricing surge
- critical building occupancy
- vulnerable occupants

The optimized decision rule prioritizes safety, preserves critical-zone comfort,
sheds named non-critical flexible loads first, estimates demand-response cost
avoidance, estimates business risk avoided, and returns source-backed traceable
recommendations.

## Technical Implementation

- Google ADK root agent with Gemini model configuration.
- ADK sub-agents for weather/pricing grounding, comfort-cost conflict analysis,
  and energy action governance.
- MCP tools exposing energy optimization, simulation, and instruction optimizer
  capabilities.
- Deterministic `EnergyOptimizationService` for safety-critical conflict
  resolution.
- B2B impact fields for demand-response cost avoidance, protected business risk,
  and load-level shed decisions.
- Synthetic simulation cases under `sample_data/`.
- Observability trace records for context retrieval and conflict resolution.
- Regression tests for the rare heat-dome plus peak-pricing case.
- A2A runtime for enterprise interoperability.

## Architecture Diagram

Use `docs/architecture-diagram.png` as the uploadable architecture diagram for
submission. The editable source is `docs/architecture-diagram.dot`, and the SVG
version is `docs/architecture-diagram.svg`.

## Business Impact

The agent helps B2B building operators avoid unsafe energy decisions while still
responding to utility peak-demand events. It turns a brittle normal-day agent
into a robust assistant for high-impact rare events.

## Differentiators

- Tests the edge case directly instead of relying on prompt hope.
- Separates Gemini orchestration from deterministic safety logic.
- Emits trace steps that explain why safety outranked cost.
- Uses building-specific controllable-load capacity rather than hardcoded load
  assumptions.
- Programmatically checks and refines missing instruction clauses.

## Demo Access

Run the rare-event plan:

```powershell
python -m startup_ops_agent.cli energy-plan --building bldg-medtech-hq --weather weather-heat-dome --pricing pricing-peak-surge --occupancy occupancy-business-critical
```

Run simulation:

```powershell
python -m startup_ops_agent.cli simulate-energy
```

## Testing

```powershell
pytest
ruff check .
python -m startup_ops_agent.cli evaluate
```
