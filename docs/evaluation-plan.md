# Track 2 Evaluation Plan

## Success Criteria

- The agent retrieves grounded building, weather, pricing, and occupancy data.
- Extreme weather plus peak-demand surge is detected as a conflict.
- Critical occupancy makes safety outrank energy cost.
- Flexible-load capacity comes from building data, not fixed prompt assumptions.
- Non-critical loads are selected before critical-zone comfort is changed.
- Cost avoidance and protected business risk are returned from deterministic fields.
- Every plan (not just simulations) emits a six-step observability trace.
- Safety invariants hold on every plan: critical-zone loads are never shed,
  setpoints stay within safe bounds, and shed never exceeds capacity.
- Instruction optimizer detects and adds missing conflict-handling rules.

## Quantitative Metrics

`evaluate` reports a `metrics` block for baseline comparison:

- `simulation_pass_rate` (target 1.0)
- `safety_violations_total` (target 0)
- `priority_distribution` across the 9-case suite
- `avg_decision_latency_ms`
- `source_id_preservation_rate` (target 1.0)

## Automated Tests

The current test suite covers:

- rare-event simulation (9 multivariable cases, all passing)
- safety-versus-cost priority
- six-step observability trace shape
- safety invariants (no critical-zone shed; setpoint bounds) and fail-fast
  model validation
- quantitative evaluation metrics block
- load-level demand-response allocation
- portfolio (fleet) demand-response allocation
- B2B cost, CO2, and business-risk impact fields
- instruction optimizer behavior
- legacy account-risk tests remain in the test suite as regression coverage, but
  the default readiness evaluation is Track 2 energy-focused

Run:

```powershell
pytest
python -m startup_ops_agent.cli evaluate --output reports/evaluation.json
```
