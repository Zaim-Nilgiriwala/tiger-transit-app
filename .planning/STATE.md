# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-11)

**Core value:** Accurate arrival time predictions for all remaining stops on a bus route, accounting for timepoint holds, schedule adherence, and real-world conditions.
**Current focus:** Phase 8 -- Training Adaptation (v1.1 Model Reapproach)

## Current Position

Phase: 8 of 9 (Training Adaptation)
Plan: 1 of 2 in current phase
Status: In progress
Last activity: 2026-02-17 -- Completed 08-01-PLAN.md (feature pipeline v1.1)

Progress: [##########          ] 50% (2/4 plans)

## Model Performance Tracker

| Model | MAE | RMSE | vs Naive | Features | Rounds |
|-------|-----|------|----------|----------|--------|
| Naive (schedule) | 708.9s | 883.4s | -- | 1 | -- |
| Baseline (P3) | 394.7s | 514.9s | 44.3% | 15 | 2000 |
| Differentiator (P4) | 175.7s | 279.7s | 75.2% | 43 | 3000 |
| Tuned (P5) | 123.1s | 202.8s | 82.6% | 43 | 1239 |
| Asymmetric (P5) | 126.5s | 210.8s | 82.2% | 43 | 2174 |
| v1.1 S2S-only (P7) | 130.0s | -- | 81.7% | 0 | -- |
| v1.1 SegSum-only (P7) | 254.3s | -- | 64.1% | 0 | -- |
| v1.1 Blended (P7) | 179.3s | -- | 74.7% | 0 | -- |
| **v1.1 target** | **< 123.1s** | -- | -- | 45 | TBD |

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
- Equal 50/50 baseline blending weights (optimize per-route in v1.2 if needed)

Phase 7 decisions:
- Segment-sum uses (route, last_stop, stops_away, hour, day_type) median -- stop_sequences order does not match multi-pattern bus routing
- S2S uses mean aggregation; segment-sum uses median (complementary statistics)
- Intermediate baselines (baseline_s2s, baseline_seg_sum) stored in parquets for transparency

Phase 8 decisions:
- lateness_now removed from PHASE3_FEATURE_COLS (14 features, down from 15)
- 3 baseline features added: baseline_s2s, baseline_seg_sum, baseline_eta (FEATURE_COLS_V2 = 45)
- TARGET_COL = residual (model learns deviation from blended baseline)
- time_to_arrival_seconds and baseline_eta preserved in KEEP_EXTRA for reconstruction (final_pred = baseline_eta + predicted_residual)

### Blockers/Concerns

- Route 27 has only 96 test samples and highest blend MAE (527.4s) -- sparse baseline persists
- Blended baseline (179.3s) is worse than v1.0 (123.1s) -- residual model must recover this gap
- S2S alone (130.0s) is close to v1.0 -- residual model may benefit more from S2S-only baseline in v1.2

## Session Continuity

Last session: 2026-02-17
Stopped at: Completed 08-01-PLAN.md (feature pipeline v1.1)
Resume file: None
