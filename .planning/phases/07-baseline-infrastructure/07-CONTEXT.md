# Phase 7: Baseline Infrastructure - Context

**Gathered:** 2026-02-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Compute historical baseline ETAs for every row in train/val/test splits and derive residual labels (actual - baseline). Two baseline methods (stop-to-stop average, segment-median-sum) are blended 50/50. This phase produces augmented parquets with baseline_eta and residual columns, plus a diagnostic report. Training and evaluation are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Fallback hierarchy
- Tier 1: Full grouping (route_id, from_stop_id, target_stop_id, hour, day_type) — minimum 5 observations required
- Tier 2: Drop hour — use (route_id, from_stop_id, target_stop_id, day_type) across all hours — minimum 5 observations
- Tier 3: Drop stop granularity — route-level average travel time, scaled by distance to target
- If a tier has fewer than 5 observations, fall to the next tier
- No fallback_tier column needed — baseline is baseline, model doesn't need to know how it was computed

### Sparse route handling
- Not a concern at the route level — training data is large
- Sparse-data risk exists at the stop-pair + hour + day_type grouping level, handled by the fallback hierarchy above
- Route 27's 96 test samples may cause noisy per-route evaluation — that's a Phase 9 concern, not Phase 7

### Fail-fast checkpoint report
- Full diagnostic: overall MAE, per-route breakdown table, error distribution histogram, breakdown by time-of-day
- Show all three baselines separately: stop-to-stop alone, segment-median-sum alone, and the 50/50 blend — informs future blend optimization
- Report as notebook cell output (no separate file)
- No auto-stop if MAE is outside 150-500s range — report the number, user decides whether to proceed

### Claude's Discretion
- day_type definition (weekday/weekend vs finer granularity)
- Exact distance-scaling method for tier-3 route-level fallback
- Histogram bin sizing and visualization details
- How to handle the segment-median-sum when stop_sequences has gaps

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 07-baseline-infrastructure*
*Context gathered: 2026-02-11*
