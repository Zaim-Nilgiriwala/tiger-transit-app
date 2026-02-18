# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-11)

**Core value:** Accurate arrival time predictions for all remaining stops on a bus route, accounting for timepoint holds, schedule adherence, and real-world conditions.
**Current focus:** Baseline rebuild complete -- v1.1 retrained with progress-decile baselines

## Current Position

Phase: 8 of 9 (Training Adaptation)
Plan: 2 of 2 in current phase (+ baseline rebuild)
Status: Baseline rebuild complete, model retrained
Last activity: 2026-02-17 -- Rebuilt segment-sum baseline with progress-decile lookup, retrained v1.1

Progress: [###############     ] 75% (3/4 plans)

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
| **v1.1 Residual (retrained)** | **94.6s** | **204.6s** | **86.7%** | **45** | **274** |

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
- New key: (route_id, last_stop_id, target_stop_id, prog_decile, hour_ct, day_type)
- prog_decile = floor((target_stop_progress - progress) * 10) clipped to [0, 9]
- 4-tier fallback: A (full key, 93.3%), B (drop hour), C (drop prog), D (broadest), then S2S fallback
- Changed blend from 50/50 to 70/30 (seg/s2s) since seg_sum now more accurate
- Baseline rebuild alone dropped model MAE from 102.8s to 94.0s (with old hyperparams)

Phase 8 decisions:
- lateness_now removed from PHASE3_FEATURE_COLS (14 features, down from 15)
- 3 baseline features added: baseline_s2s, baseline_seg_sum, baseline_eta (FEATURE_COLS_V2 = 45)
- TARGET_COL = residual (model learns deviation from blended baseline)
- time_to_arrival_seconds and baseline_eta preserved in KEEP_EXTRA for reconstruction
- Pseudo-Huber loss (reg:pseudohubererror) won over squared error (huber_slope=78.8)
- Gamma (2.29) for conservative splits on zero-centered residual targets
- Deterministic final model: 274 rounds (best_iteration + 1), no early stopping
- Z-score 2.5 trimming removes 1.4% of training data (16,444 samples)

### Blockers/Concerns

- Route 27 still has only 96 test samples and highest MAE (399.2s) -- sparse data issue persists
- Optuna retune (94.6s) didn't improve over old-params run (94.0s) -- old hyperparams were already good for this data shape

## Session Continuity

Last session: 2026-02-17
Stopped at: Rebuilt baselines with progress-decile lookup, retrained v1.1 (94.6s MAE)
Resume file: None
