---
phase: 01-data-foundation
plan: 03
subsystem: data-pipeline
tags: [timepoints, schedule, mapping, fuzzy-matching, parquet]
depends_on: []
provides: [timepoint-mapping, timepoints-parquet]
affects: [02-01, 03-01, 04-01]
tech_stack:
  added: []
  patterns: [human-in-the-loop-verification, manual-override-mapping, dynamic-column-detection]
key_files:
  created:
    - scripts/generate_timepoint_mapping.py
    - scripts/parse_timepoints.py
    - data/processed/timepoint_mapping.json
    - data/processed/timepoints.parquet
  modified: []
decisions:
  - id: timepoint-fuzzy-matching
    decision: "Use difflib.get_close_matches with cutoff=0.5 for draft mapping, require human review for all fuzzy/unmatched entries"
  - id: sheet-to-route-manual-overrides
    decision: "Manual override table maps 8 sheet names to GTFS route long names where naming conventions differ"
  - id: outdated-stops-skip
    decision: "Marathon Gas Station has no GTFS match (outdated stop); skip with warning, do not halt pipeline"
  - id: route-id-first-segment
    decision: "Extract first numeric segment from compound GTFS route IDs (consistent with 01-02 arrivals approach)"
metrics:
  duration: ~8 minutes
  completed: 2026-02-03
---

# Phase 01 Plan 03: Timepoint Mapping & Parsing Summary

**Map timepoint Excel stop names to GTFS stop IDs via fuzzy matching + human review, then parse all 23 schedule sheets into structured tuples.**

## One-liner

Fuzzy-matched 28 timepoint names to GTFS stop IDs (27/28 matched after user review), then parsed 23 Excel sheets into 1,958 schedule tuples with dynamic column group detection.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Generate timepoint-to-GTFS mapping draft | d941f81 | scripts/generate_timepoint_mapping.py, data/processed/timepoint_mapping.json |
| 2 | Checkpoint: human-verify | APPROVED | User corrected 4 mappings in timepoint_mapping.json |
| 3 | Create timepoint parser script | 48a1ec5 | scripts/parse_timepoints.py |

## Key Results

### Timepoint Mapping (data/processed/timepoint_mapping.json)
- **28 unique timepoint names** extracted from 23 Excel sheets
- **6 exact matches**, 17 fuzzy matches, 4 manual corrections, 1 unmatched
- **27/28 mapped** to GTFS stop IDs after user review
- **1 unmatched:** Marathon Gas Station (outdated stop, no GTFS equivalent)
- **User corrections:** Student Center->47, Savannah Square->148, HUB->153, Museum->105

### Timepoints Parquet (data/processed/timepoints.parquet)
- **1,958 schedule tuples** parsed from all 23 sheets
- **22 unique routes**, 24 unique stops
- **Columns:** route_id (int), route_name, stop_id (int), stop_name, scheduled_time (HH:MM:SS)
- **Top routes by entries:** West Glenn (145), West Campus (127), P&R (125), College Loop (122)
- **File size:** 6.6 KB

### Sheet-to-Route Mapping
- 8 manual overrides needed (Glenn Harper->Glenn-Harper, Old Row->Old Row - West Parking, etc.)
- All 23 sheets successfully matched to GTFS route IDs
- SQ-FA and South Quad both map to route 226 (South Quad/Fine Arts)

## Deviations from Plan

None - plan executed exactly as written. The human-in-the-loop checkpoint worked as designed, with user providing corrections for 4 ambiguous mappings.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Fuzzy matching with human review | Only 6/28 exact matches; fuzzy draft + user verification ensures accuracy |
| 8 manual sheet-to-route overrides | Sheet names use informal names (e.g., "P&R" vs "Park & Ride") |
| Skip Marathon Gas Station | Outdated stop with no GTFS match; 1 of 2 Wire Road timepoints still captured |
| First numeric segment for route IDs | Consistent with 01-02 arrivals parser convention |

## Verification Results

- All 23 sheets processed without errors
- Marathon Gas Station skipped with warning (did not crash)
- Parquet has correct schema: route_id (int64), stop_id (int64), scheduled_time (string)
- Route IDs are numeric GTFS IDs
- Both scripts run independently from project root

## Next Phase Readiness

- Timepoints parquet ready for schedule adherence features (Phase 4: hold detection at timepoints)
- Mapping file is reusable if Excel is updated in future semesters
- All Phase 1 data artifacts now complete: telemetry, weather, GTFS stops, arrivals, timepoints
- No blockers for Phase 2 (row explosion / label generation)
