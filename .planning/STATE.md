# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-11)

**Core value:** Accurate arrival time predictions for all remaining stops on a bus route, accounting for timepoint holds, schedule adherence, and real-world conditions.
**Current focus:** Phase 7 -- Baseline Infrastructure (v1.1 Model Reapproach)

## Current Position

Phase: 7 of 9 (Baseline Infrastructure)
Plan: 0 of 1 in current phase
Status: Ready to plan
Last activity: 2026-02-11 -- Roadmap created for v1.1 milestone

Progress: [                    ] 0% (0/4 plans)

## Model Performance Tracker

| Model | MAE | RMSE | vs Naive | Features | Rounds |
|-------|-----|------|----------|----------|--------|
| Naive (schedule) | 708.9s | 883.4s | -- | 1 | -- |
| Baseline (P3) | 394.7s | 514.9s | 44.3% | 15 | 2000 |
| Differentiator (P4) | 175.7s | 279.7s | 75.2% | 43 | 3000 |
| Tuned (P5) | 123.1s | 202.8s | 82.6% | 43 | 1239 |
| Asymmetric (P5) | 126.5s | 210.8s | 82.2% | 43 | 2174 |
| v1.1 Baseline-only (P7) | TBD | -- | -- | 0 | -- |
| **v1.1 target** | **< 123.1s** | -- | -- | 44 | TBD |

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

### Blockers/Concerns

- Route 27 has only 96 test samples -- sparse baseline coverage risk
- Baseline quality unknowable until Phase 7 delivers (fail-fast checkpoint: if baseline MAE > 300s, residual model faces uphill battle)

## Session Continuity

Last session: 2026-02-11
Stopped at: Roadmap created for v1.1 milestone (3 phases, 4 plans)
Resume: Plan Phase 7 (baseline infrastructure)
