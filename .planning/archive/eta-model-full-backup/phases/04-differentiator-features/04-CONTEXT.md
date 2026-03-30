# Phase 4: Differentiator Features - Context

**Gathered:** 2026-02-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Engineer Auburn-specific and advanced features (timepoint holds, rolling speeds, historical segment/dwell times) that demonstrably improve model accuracy over the Phase 3 baseline (394.7s MAE). Features are added to the existing feature matrix and model is retrained to measure improvement.

</domain>

<decisions>
## Implementation Decisions

### Rolling Speed Windows
- Compute all four rolling windows: 30s, 60s, 120s, 180s
- Speed derived from GPS positions (haversine distance / time delta), NOT EtaSpot speed field
- Minimum time delta between pings: 5 seconds (filter closer pings to avoid GPS jitter)
- Cap maximum GPS-derived speed at 65 mph (anything above is GPS error)
- Also compute acceleration (speed change rate) as a feature
- Add speed variance (std dev) within each rolling window to capture stop-and-go vs smooth cruising
- Add idle detection: binary is_idle flag + seconds_idle duration
- Compute speed relative to segment historical average (ratio feature: current_speed / historical_avg_speed_for_segment_hour)

### Timepoint Feature Design
- is_timepoint binary flag AND scheduled_departure_seconds for target stop
- timepoints_remaining (count between current position and target stop)
- time_until_next_timepoint_departure (seconds to next timepoint's scheduled departure)
- Timepoint adherence: seconds early/late at the most recent timepoint the bus passed
- Routes without timepoints: set all timepoint features to NaN (XGBoost handles missing natively)

### Historical Aggregates
- Segment travel time aggregated at: route + segment + hour + day_type (weekday vs weekend)
- Dwell time at stops: separate feature from segment travel time, also broken down by time of day
- Use median only (not mean) for robustness to outliers
- Sparse combos (too few observations): set to NaN rather than falling back to coarser granularity
- Historical aggregates computed from training data only (no leakage from val/test dates)

### Auburn-Specific Signals
- Skip class schedule proxy features (hour-of-day captures temporal patterns implicitly)
- Skip campus zone features (route_id + stop_index encode location implicitly)
- Skip semester position features (only 5 weeks of data, too little variation)
- Timepoint features ARE the main Auburn-specific signal for this phase

### Claude's Discretion
- Gap handling strategy for rolling speed windows (NaN vs forward-fill when telemetry is sparse)
- Minimum observation threshold for historical aggregate NaN cutoff
- Exact idle speed threshold (e.g., < 2 mph vs < 3 mph)
- Whether to add percentile features (p25, p75) alongside median for historical aggregates if data supports it

</decisions>

<specifics>
## Specific Ideas

- Speed should be GPS-derived (haversine) rather than device-reported, with 5s min delta and 65 mph cap
- Historical dwell times should be time-of-day aware (not just overall averages)
- Timepoint adherence captures what lateness_now couldn't (lateness_now had zero variance in Phase 3 due to EtaSpot data characteristics)
- Normalized speed ratio (current vs historical segment average) is a key differentiator feature

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-differentiator-features*
*Context gathered: 2026-02-04*
