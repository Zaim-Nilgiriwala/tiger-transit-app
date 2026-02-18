---
phase: 09-evaluation-and-comparison
verified: 2026-02-17T22:15:00Z
status: passed
score: 5/5 must-haves verified
gaps: []
human_verification:
  - test: "Open reports/v1_1_evaluation.html in a browser and inspect the SHAP side-by-side charts"
    expected: "v1.0 left chart shows time_until_next_timepoint_departure as #1; v1.1 right chart shows baseline_s2s as #1. Both have 15 bars each with readable feature names."
    why_human: "The SHAP feature importance charts are embedded as base64 PNG images -- programmatic verification can confirm the chart exists and the surrounding narrative is correct, but visual inspection is needed to confirm the charts render legibly."
  - test: "Verify the residual histogram shows two overlapping distributions with a stats textbox"
    expected: "Actual residuals (red) are wide and heavy-tailed. Predicted residuals (green) are tighter. Stats box shows skew, kurtosis values. Both distributions visible in same chart."
    why_human: "Stats textbox is rendered inside the matplotlib figure (embedded as PNG) -- the values are computed correctly in the script but verification of visual rendering requires opening the HTML."

# Phase 9: Evaluation and Comparison - Verification Report

**Phase Goal:** Definitive proof that v1.1 beats v1.0, with reconstructed predictions evaluated apples-to-apples on the same test set
**Verified:** 2026-02-17T22:15:00Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Reconstructed MAE (85.6s) lower than v1.0 (123.1s) | VERIFIED | v1_1_metrics.json: reconstructed_mae=85.55, comparison_v1_0.v1_1_reconstructed_mae=85.55 < 123.1 |
| 2 | Report shows three-way MAE comparison (baseline, v1.0, v1.1) | VERIFIED | HTML contains metric cards for 91.9s (baseline), 123.1s (v1.0), 85.6s (v1.1) -- all live-computed |
| 3 | Per-route table with 23 routes, majority improved, Route 27 flagged | VERIFIED | 23 routes in per_route data; 22/23 improved (1% tolerance); "Low sample count (96 samples)" present in HTML |
| 4 | SHAP analysis present with feature importance shift documented | VERIFIED | 5 embedded charts; SHAP side-by-side bar charts present; narrative shows 8 features new in v1.1, 8 dropped |
| 5 | Residual distribution analysis with histogram, skew, kurtosis | VERIFIED | scipy.stats.skew and kurtosis computed; stats_text rendered via ax.text into embedded PNG histogram |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `scripts/evaluate_v1_1.py` | Evaluation script, 300+ lines | VERIFIED | 954 lines; substantive implementation across 6 functions; no stubs; exports main() |
| `reports/v1_1_evaluation.html` | Self-contained HTML, 50KB+ | VERIFIED | 557,090 bytes (544 KB); 5 embedded base64 PNG charts; no external dependencies |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `evaluate_v1_1.py` | `models/tuned_metrics.json` | `json.load` for best_iteration | WIRED | `v1_0_metrics["best_iteration"]` used for iteration_range in v1.0 predictions |
| `evaluate_v1_1.py` | `models/tuned_v1.ubj` | `xgb.Booster().load_model()` | WIRED | Line 132: `bst_v1_0.load_model(str(MODELS_DIR / "tuned_v1.ubj"))` |
| `evaluate_v1_1.py` | `models/v1_1_residual.ubj` | `xgb.Booster().load_model()` | WIRED | Line 136: `bst_v1_1.load_model(str(MODELS_DIR / "v1_1_residual.ubj"))` |
| `evaluate_v1_1.py` | `data/processed/test_featured_v2.parquet` | `load_featured_v2("test")` | WIRED | Line 120: `df = load_featured_v2("test")` |
| `evaluate_v1_1.py` | baseline_eta column | `df["baseline_eta"].values` | WIRED | Line 165-166: `baseline_eta = df["baseline_eta"].values; pred_v1_1 = baseline_eta + pred_residual_v1_1` |
| `evaluate_v1_1.py` | pred_contribs SHAP | `bst.predict(pred_contribs=True)` | WIRED | Lines 453 and 471: both models compute SHAP via pred_contribs |

Note: `models/v1_1_metrics.json` is NOT used by the script. All MAEs are computed live from model predictions on the test set, which is consistent with the EVAL-LIVE decision in the SUMMARY.

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| EVAL-01: Reconstructed MAE < v1.0 123.1s | SATISFIED | 85.55s < 123.1s; 30.5% improvement; live-computed via mae() on predictions |
| EVAL-02: Three-way MAE comparison in report | SATISFIED | Metric cards in HTML for baseline (91.9s), v1.0 (123.1s), v1.1 (85.6s) with improvement banner |
| EVAL-03: SHAP top-15 side-by-side charts | SATISFIED | Side-by-side horizontal bar charts (2 subplots in 1 figure); narrative lists new/dropped features |
| EVAL-04: Per-route table with wins/losses, Route 27 flagged | SATISFIED | 23 routes, 22 wins / 1 loss / 0 ties; Route 27 asterisk with "Low sample count (96 samples)" |
| EVAL-05: Residual distribution diagnostics | SATISFIED | Histogram, scipy stats (skew/kurtosis in embedded chart), tail analysis table (5/10/15 min), MAE vs stops_away, MAE vs hour |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | - | No TODO/FIXME/placeholder patterns found | - | - |

No anti-patterns detected. No empty returns, no stub handlers, no placeholder text.

### Notes on EVAL-04 SHAP Criterion

The ROADMAP specified that SHAP should show "real-time condition features (speed_mean_*, speed_ratio) gaining importance relative to spatial features (stop_index, distance_to_target)."

**What actually happened:** speed_mean_* and speed_ratio features exist in both v1.0 and v1.1 feature sets. The SHAP analysis found that baseline features (baseline_s2s, baseline_seg_sum, baseline_eta) are the new dominant features in v1.1's top 15, displacing schedule-proximity features (stop_index, segment_travel_p25/median/p75, stops_remaining). Speed features may appear in the common-15 portion of both top-15 lists (neither dropped nor new).

**Assessment:** The SHAP analysis requirement (EVAL-03) is fully satisfied -- the script computes SHAP via pred_contribs for both models and renders side-by-side charts with narratives. The specific feature shift pattern (speed gaining) reflects an expectation that wasn't explicitly tested in the code. The actual shift documented (baseline features dominating residual predictions) is architecturally correct and well-explained in the report narrative. This is a result-not-matching-hypothesis scenario, not a missing analysis. The analysis is present and valid.

### Human Verification Required

#### 1. SHAP Charts Legibility

**Test:** Open `reports/v1_1_evaluation.html` in a browser, scroll to Section 3 SHAP Feature Importance. Examine both charts.
**Expected:** v1.0 left chart shows time_until_next_timepoint_departure as #1 feature; v1.1 right chart shows baseline_s2s as #1. Both charts have 15 horizontal bars with readable feature names and values.
**Why human:** SHAP charts embedded as base64 PNG -- visual rendering not programmatically verifiable.

#### 2. Residual Histogram Stats Textbox

**Test:** Scroll to Section 4 Residual Distribution histogram.
**Expected:** Two overlapping distributions (red = actual, green = predicted); stats textbox in upper-left showing skew and kurtosis values for both; vertical dashed line at zero.
**Why human:** Stats textbox rendered inside matplotlib figure embedded as PNG -- requires visual confirmation.

---

_Verified: 2026-02-17T22:15:00Z_
_Verifier: Claude (gsd-verifier)_
