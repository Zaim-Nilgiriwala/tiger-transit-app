# Phase 1: Data Foundation - Context

**Gathered:** 2026-02-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Parse all raw data sources (telemetry, arrivals, GTFS shapes, timepoint Excel, weather) into clean, joined DataFrames ready for feature engineering. No modeling, no feature engineering — just reliable, validated data pipelines that downstream phases can consume without touching raw files.

</domain>

<decisions>
## Implementation Decisions

### Filtering & cleaning rules
- Drop rows with GPS coordinates outside a reasonable Auburn bounding box (no flagging — just remove)
- Filter out telemetry with speeds above 65 mph (GPS jump artifacts)
- Exclude jAUnt, Shuttle, and inactive vehicles per roadmap; Claude examines data to identify any additional exclusions needed
- Zero-speed (idle) pings: Claude's discretion on whether to keep all or deduplicate based on what's useful for downstream modeling

### Timepoint-to-GTFS matching
- Use a manual mapping file approach: Claude drafts a proposed mapping from the timepoint Excel human-readable names to GTFS stop IDs, user reviews and approves
- Unmatched timepoint stops are skipped with a logged warning (pipeline does not halt)
- Parse all 23 sheets from the timepoint Excel — treat all as relevant

### Data output format
- Processed files go to `data/processed/`
- File structure (separate per source vs. pre-joined): Claude's discretion based on what's cleanest for downstream use
- Independent scripts per data source (parse_telemetry.py, parse_arrivals.py, etc.) — each runnable individually
- Each script prints summary validation stats after processing (row counts, null rates, key distributions)

### Weather join strategy
- Weather data is already fetched and stored; if gaps are discovered, re-fetch using existing `getWeatherData.ts` (do not impute)
- Keep only temperature and precipitation columns — no wind, humidity, or other features
- Join by flooring telemetry timestamp to containing hour (3:45pm gets 3:00pm weather)

### Claude's Discretion
- Additional route/vehicle exclusions beyond jAUnt, Shuttle, and inactive
- Zero-speed ping handling (keep all vs. deduplicate)
- Output file structure (separate parquets per source vs. pre-joined)
- Column naming conventions
- Exact Auburn bounding box coordinates

</decisions>

<specifics>
## Specific Ideas

- Weather gap handling: use the existing `getWeatherData.ts` to re-fetch rather than imputing — data should be complete
- Timepoint mapping is a review checkpoint: Claude generates the draft, user verifies before pipeline uses it

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-data-foundation*
*Context gathered: 2026-02-03*
