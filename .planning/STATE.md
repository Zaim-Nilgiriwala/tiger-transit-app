# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-11)

**Core value:** Accurate arrival time predictions for all remaining stops on a bus route, accounting for timepoint holds, schedule adherence, and real-world conditions.
**Current focus:** v1.1 Model Reapproach -- predict residuals instead of raw seconds

## Current Position

Phase: Not started (defining requirements)
Plan: --
Status: Defining requirements
Last activity: 2026-02-11 -- Milestone v1.1 started

Progress: [          ] 0%

## Model Performance Tracker

| Model | MAE | RMSE | vs Naive | Features | Rounds |
|-------|-----|------|----------|----------|--------|
| Naive (schedule) | 708.9s | 883.4s | -- | 1 | -- |
| Baseline (P3) | 394.7s | 514.9s | 44.3% | 15 | 2000 |
| Differentiator (P4) | 175.7s | 279.7s | 75.2% | 43 | 3000 |
| Tuned (P5) | 123.1s | 202.8s | 82.6% | 43 | 1239 |
| Asymmetric (P5) | 126.5s | 210.8s | 82.2% | 43 | 2174 |
| **v1.1 target** | **< 123.1s** | -- | -- | 43 | TBD |

## Accumulated Context

### Decisions

Carried from v1.0:
- lateness_now has zero variance (scheduled_eta == eta in EtaSpot data)
- Quantile monotonicity violations (32.3%) with independent quantile training on subsampled data
- pred_contribs preferred over TreeExplainer for large models
- 6 routes show overprediction bias, 2 underprediction -- consider route-specific calibration

### Blockers/Concerns

- Route 27 has only 96 test samples -- insufficient for reliable evaluation
- Midday overprediction bias (+24.93s) from v1.0 -- may or may not persist with residual target

## Session Continuity

Last session: 2026-02-11
Stopped at: Defining v1.1 requirements
Resume: Continue with requirements definition and roadmap creation
