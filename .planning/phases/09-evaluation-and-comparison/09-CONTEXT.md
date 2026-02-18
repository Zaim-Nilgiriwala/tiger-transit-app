# Phase 9: Evaluation and Comparison - Context

**Gathered:** 2026-02-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Definitive proof that v1.1 beats v1.0, with reconstructed predictions (baseline_eta + predicted_residual) evaluated apples-to-apples on the same test set. Includes side-by-side comparison, per-route breakdown, SHAP analysis, and residual diagnostics. No model changes — this phase is evaluation only.

</domain>

<decisions>
## Implementation Decisions

### Report structure
- Single evaluation script that prints key metrics to console AND saves a detailed report to disk
- Report format: HTML with embedded plots/charts
- Visualizations: matplotlib/seaborn charts embedded in the HTML (bar charts, histograms, SHAP plots)
- Output location: `reports/` top-level directory

### Per-route analysis depth
- Full table of all routes: v1.0 MAE, v1.1 MAE, v1.0 RMSE, v1.1 RMSE, delta, % improvement — sorted by improvement
- Narrative highlights section calling out biggest winners, biggest losers, and outliers
- Sparse routes (e.g., Route 27 with 96 samples): flag with asterisk/note indicating low sample count, but include in table and aggregates
- Grouped bar chart: v1.0 vs v1.1 MAE side-by-side per route

### SHAP analysis scope
- Global importance only — no per-route SHAP breakdowns
- Side-by-side horizontal bar charts: v1.0 top 15 features vs v1.1 top 15 features
- No explicit feature-group aggregation — the visual comparison is sufficient for readers to see if real-time features gained importance
- Computation method: pred_contribs (fast, consistent with v1.0 analysis)

### Residual diagnostics
- Histogram of predicted residuals with overlaid actual residuals, plus summary stats (skew, kurtosis, mean, std)
- Explicit tail analysis: % of predictions >5min off, >10min off, etc.
- Breakdown by stops_away: line chart showing MAE vs stops_away
- Breakdown by time_of_day: line chart showing MAE vs hour
- v1.1 only for residual analysis (v1.0 comparison covered in per-route section)

### Claude's Discretion
- Exact HTML template and styling
- Plot color scheme and sizing
- Histogram bin count
- How to bucket stops_away and hour for the breakdown charts
- Console output formatting and verbosity

</decisions>

<specifics>
## Specific Ideas

- The three-model comparison (baseline-only, v1.0 raw 123.1s, v1.1 final) should be the headline of the report
- Route 27 has been a known concern throughout — call it out specifically in the narrative highlights
- pred_contribs was already validated during v1.0 (preferred over TreeExplainer for large models)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-evaluation-and-comparison*
*Context gathered: 2026-02-17*
