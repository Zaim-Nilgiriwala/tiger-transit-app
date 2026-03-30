# Phase 2: Row Explosion & Labels - Context

**Gathered:** 2026-02-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Explode each telemetry observation into per-stop rows (one per remaining stop), join against actual arrivals to create `time_to_arrival_seconds` ground truth labels, and split data temporally into train/val/test sets. This phase does NOT do feature engineering beyond what's needed for the label join.

</domain>

<decisions>
## Implementation Decisions

### Row explosion scope
- Explode each telemetry ping into rows for the **next 8 stops** only (not all remaining stops on route)
- Determines "remaining" stops using **shape distance projection** — project GPS onto GTFS route shape via `shape_dist_traveled`, then select the next 8 stops by shape distance
- **Downsample telemetry to ~60s intervals** before explosion to keep dataset manageable (~18M exploded rows vs 100M+ at full resolution)
- Memory safety is critical — must use chunked-by-day processing throughout, peak memory must stay within available RAM

### Claude's Discretion
- Label join tolerances and `merge_asof` window size
- Filtering thresholds (min/max label values, outlier removal)
- Temporal split date ranges and gap period size
- Handling of idle vehicles, layovers, and end-of-route edge cases
- Specific chunking strategy for memory management
- How to handle missing or ambiguous arrival matches

</decisions>

<specifics>
## Specific Ideas

- User explicitly flagged memory safety — ensure chunked processing and monitor peak memory usage
- 60s downsampling chosen to balance dataset size against information retention

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-row-explosion-labels*
*Context gathered: 2026-02-03*
