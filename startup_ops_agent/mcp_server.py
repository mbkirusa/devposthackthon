from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from startup_ops_agent.tools import (
    build_energy_optimization_plan,
    build_energy_plan_from_scenario,
    build_energy_portfolio_plan,
    optimize_energy_agent_instruction,
    run_energy_simulation,
)

mcp = FastMCP("energy-ops-tools")


@mcp.tool()
def energy_optimization_plan(
    building_id: str,
    weather_event_id: str,
    pricing_event_id: str,
    occupancy_id: str,
) -> dict:
    """Return a source-backed plan for weather and utility pricing conflicts."""
    return build_energy_optimization_plan(
        building_id=building_id,
        weather_event_id=weather_event_id,
        pricing_event_id=pricing_event_id,
        occupancy_id=occupancy_id,
    )


@mcp.tool()
def energy_scenario_plan(scenario: str) -> dict:
    """Resolve a natural-language energy operations scenario and return a plan."""
    return build_energy_plan_from_scenario(scenario=scenario)


@mcp.tool()
def energy_portfolio_plan(weather_event_id: str, pricing_event_id: str) -> dict:
    """Meet a grid-wide demand-response target across the whole building portfolio."""
    return build_energy_portfolio_plan(
        weather_event_id=weather_event_id,
        pricing_event_id=pricing_event_id,
    )


@mcp.tool()
def energy_simulation(case_id: str) -> dict:
    """Run a synthetic simulation case and return observability trace steps."""
    return run_energy_simulation(case_id=case_id)


@mcp.tool()
def energy_instruction_optimizer(instruction: str) -> dict:
    """Return optimized conflict-handling clauses for the energy agent instruction."""
    return optimize_energy_agent_instruction(instruction=instruction)


if __name__ == "__main__":
    mcp.run()
