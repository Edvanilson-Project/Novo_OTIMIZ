# Product infeasibility and parameter validation report

Date: 2026-04-29

## 1. GROUP_INFEASIBLE modes

`group_infeasibility_mode` is accepted in `cct_params`, `vsp_params`,
`optimization_params`, or `request_metadata`.

- `strict`: default. Preserves the current behavior. A confirmed
  `GROUP_INFEASIBLE` fails the run and returns the diagnostic payload.
- `production`: returns the best audited solution only when the infeasibility is
  exactly a mandatory group preservation failure. It records
  `group_infeasibility_handling`, `relaxed_constraints`, and `affected_groups`.
  The original hard issue remains in `hard_constraint_report.output`; the
  override is explicit in `hard_constraint_report.strict_relaxation_override`.
- `assisted`: fails the run and returns the problematic groups in
  `affected_groups` for manual intervention. No constraint is relaxed.

This does not mask infeasibility: production mode only marks a controlled
relaxation after the group repair path proves that the group cannot be kept
together without violating hard VSP constraints.

## 2. Operational parameters validated

The result now includes `parameter_effect_report` with:

- `active_constraints`: effective values for `min_break`,
  `min_connection_time`, `max_shift_minutes`, `max_driving_minutes`,
  `zero_gap`, and `allow_vehicle_swap`.
- `blocked_connections`: count and samples of candidate connections blocked by
  those parameters.
- `impact`: where the parameter affected the solution across VSP, CSP,
  fallback, and stitching.

`min_connection_time` is supported as a product alias for
`min_layover_minutes`, so the API can receive the operational term directly.

## 3. Real examples covered by tests

- Infeasible group connection: trips `[1, 2]` in group `77` cannot be preserved
  because the connection is physically invalid. `strict` and `assisted` fail;
  `production` returns an audited relaxation with the affected group.
- VSP boundary: two trips with a 5 minute gap and `min_connection_time=10`
  are split into two vehicle blocks and reported under
  `blocked_connections.by_constraint.min_connection_time`.
- CSP boundary: a duty above `max_shift_minutes` and
  `max_driving_minutes` is counted in the parameter report.
- Zero gap: adjacent trips at the same minute with different terminals are
  counted when `strict_zero_gap_validation=true`.
- Vehicle swap: `allow_vehicle_swap=false` is reported as active and linked to
  `OPERATOR_MULTIPLE_VEHICLES` impact.
- Fallback and stitching: report surfaces `group_audit_fallback`,
  scale fallback chunk count, and stitching accepted/rejected counts.

## 4. Validation executed

- `./venv/bin/python -m pytest tests/unit/test_settings_parameter_effects.py -q`
  - 19 passed
- `./venv/bin/python -m pytest tests/unit/test_solver_edge_cases.py tests/unit/test_explainability_and_costs.py -q`
  - 30 passed
- `./venv/bin/python -m py_compile src/api/schemas.py src/api/routes/optimize.py src/domain/models.py src/services/optimizer_service.py`
  - passed

