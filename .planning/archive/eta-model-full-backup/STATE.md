# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-11)

**Core value:** Accurate arrival time predictions for all remaining stops on a bus route, accounting for timepoint holds, schedule adherence, and real-world conditions.
**Current focus:** Mobile app UX improvements (quick tasks)

## Current Position

Phase: 9 of 9 (Evaluation and Comparison)
Plan: 1 of 1 in current phase
Status: Complete
Last activity: 2026-02-18 -- Completed quick-001 (smooth vehicle marker interpolation)

Progress: [####################] 100% (17/18 plans complete, all phases done)

## Model Performance Tracker

| Model | MAE | RMSE | vs Naive | Features | Rounds |
|-------|-----|------|----------|----------|--------|
| Naive (schedule) | 708.9s | 883.4s | -- | 1 | -- |
| Baseline (P3) | 394.7s | 514.9s | 44.3% | 15 | 2000 |
| Differentiator (P4) | 175.7s | 279.7s | 75.2% | 43 | 3000 |
| Tuned (P5) | 123.1s | 202.8s | 82.6% | 43 | 1239 |
| Asymmetric (P5) | 126.5s | 210.8s | 82.2% | 43 | 2174 |
| v1.1 S2S-only (P7) | 130.0s | -- | 81.7% | 0 | -- |
| v1.1 SegSum-old (P7, stops_away) | 254.3s | -- | 64.1% | 0 | -- |
| v1.1 Blended-old (P7, 50/50) | 179.3s | -- | 74.7% | 0 | -- |
| v1.1 Residual-old (P8) | 102.8s | 208.9s | 85.5% | 45 | 656 |
| v1.1 SegSum-new (prog-decile) | 109.4s | -- | 84.6% | 0 | -- |
| v1.1 Blended-new (70/30) | 111.1s | -- | 84.3% | 0 | -- |
| v1.1 Residual (prog-decile) | 94.6s | 204.6s | 86.7% | 45 | 274 |
| v1.1 SegSum-4D (baseline) | 91.9s | -- | 87.0% | 0 | -- |
| **v1.1 Residual (4D baselines)** | **85.6s** | **186.8s** | **87.9%** | **45** | **274** |

## Accumulated Context

### Decisions

Carried from v1.0:
- lateness_now has zero variance (scheduled_eta == eta in EtaSpot data)
- pred_contribs preferred over TreeExplainer for large models
- 6 routes show overprediction bias, 2 underprediction

v1.1 decisions:
- Residual target over raw seconds (model learns deviation from baseline)
- Modify v1.0 scripts in place (v1.0 preserved in git history)
- Symmetric loss first (asymmetric deferred -- sign semantics change with residuals)

Phase 7 decisions:
- S2S uses mean aggregation; segment-sum uses median (complementary statistics)
- Intermediate baselines (baseline_s2s, baseline_seg_sum) stored in parquets for transparency

Baseline rebuild decisions:
- Replaced stops_away lookup (254.3s MAE) with progress-decile destination-specific lookup (109.4s MAE)
- Then replaced prog-decile with 4D tiered approach: (elapsed_decile, segment_decile, is_stopped, on_time_bin)
- 4D SegSum baseline MAE: 91.9s (best baseline yet); S2S: 129.0s
- baseline_eta = SegSum only (no S2S blend -- SegSum dominates at every stops_away)
- 6-tier fallback: A (all 4 dims) through F (route+stops only), then S2S final fallback
- No day_type (99% weekday -- halves cell counts for no benefit)
- Model retrained on 4D baselines: 85.6s MAE (was 94.6s on prog-decile baselines)

Phase 8 decisions:
- lateness_now removed from PHASE3_FEATURE_COLS (14 features, down from 15)
- 3 baseline features added: baseline_s2s, baseline_seg_sum, baseline_eta (FEATURE_COLS_V2 = 45)
- TARGET_COL = residual (model learns deviation from blended baseline)
- time_to_arrival_seconds and baseline_eta preserved in KEEP_EXTRA for reconstruction
- Pseudo-Huber loss (reg:pseudohubererror) won over squared error (huber_slope=78.8)
- Gamma (2.29) for conservative splits on zero-centered residual targets
- Deterministic final model: 274 rounds (best_iteration + 1), no early stopping
- Z-score 2.5 trimming removes 1.4% of training data (16,444 samples)

Phase 9 decisions:
- All v1.1 metrics computed live from model + test data (no saved JSON workarounds)
- Self-contained HTML report with base64 embedded charts (no external dependencies)
- v1.0 DMatrix reconstructed with lateness_now=0.0 for feature compatibility

Quick task decisions:
- Q001: AnimatedRegion + MarkerAnimated for smooth bus marker transitions (1000ms duration)
- Q001: Shortest-path heading wraparound via delta normalization to [-180, 180]

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 001 | Smooth vehicle marker interpolation (AnimatedRegion) | 2026-02-18 | 8f70d87 | [001-smooth-vehicle-marker-interpolation](./quick/001-smooth-vehicle-marker-interpolation/) |

### Blockers/Concerns

- Route 27 still has only 96 test samples and highest MAE (386.5s) -- sparse data issue persists
- Data sync issue RESOLVED: model trained on same 4D baselines in featured_v2 parquets
- v1.1 evaluation complete: 85.6s MAE, 30.5% improvement over v1.0

## Session Continuity

Last session: 2026-02-18
Stopped at: Completed quick-001 (smooth vehicle marker interpolation)
Resume file: None
