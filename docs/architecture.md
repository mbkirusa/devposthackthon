# Architecture

Submission-ready diagram assets:

- `docs/architecture-diagram.png`
- `docs/architecture-diagram.svg`
- `docs/architecture-diagram.dot`

![Energy Ops Agent architecture](architecture-diagram.svg)

```mermaid
flowchart LR
    User["Facilities / Energy Operator"] --> ADK["building_energy_ops_agent"]
    ADK --> Weather["weather_grounding_agent"]
    ADK --> Pricing["utility_pricing_agent"]
    ADK --> Comfort["comfort_safety_agent"]
    ADK --> Optimizer["energy_optimization_agent"]
    Weather --> MCP["MCP tools"]
    Pricing --> MCP
    Comfort --> MCP
    Optimizer --> MCP
    MCP --> EnergyService["EnergyOptimizationService"]
    EnergyService --> Data["Building, weather, pricing, occupancy data"]
    EnergyService --> Trace["Observability trace"]
    Simulator["Agent Simulation"] --> EnergyService
    Optimizer["Agent Optimizer"] --> Instructions["System instructions"]
```

## Runtime Boundaries

The Gemini-backed ADK agents are responsible for conversation planning, tool
selection, agent handoff, and final explanation. The diagram uses judge-friendly
role labels. In code, these responsibilities are implemented by
`energy_ops_agent`, `weather_pricing_grounding_agent`,
`comfort_cost_conflict_agent`, and `energy_action_governance_agent`.
Deterministic services own safety-versus-cost conflict resolution for edge cases.

The energy service owns business rules:

- extreme weather detection
- peak pricing detection
- critical-zone safety priority
- flexible-load shedding
- source preservation
- observability trace generation

## Data Flow

1. A facilities operator asks for an energy plan.
2. The grounding agent retrieves weather, utility pricing, building, and
   occupancy context.
3. The conflict agent evaluates comfort versus cost.
4. The deterministic energy service resolves the conflict.
5. The governance agent recommends safe HVAC and load-shedding actions.
6. The simulator verifies rare cases and records trace steps.

## Production Upgrade Path

The JSON repository can be replaced by adapters for weather providers, utility
tariffs, building-management systems, occupancy sensors, or Vertex AI Search.

For Google Cloud:

- deploy the ADK A2A app to Agent Engine Runtime or Cloud Run
- move durable state to Firestore or Cloud SQL
- export structured logs to Cloud Logging
- trace MCP tool latency with Cloud Trace
- store secrets in Secret Manager
