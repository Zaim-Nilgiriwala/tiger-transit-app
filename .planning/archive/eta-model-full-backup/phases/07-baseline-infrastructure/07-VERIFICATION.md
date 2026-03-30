---
phase: 07-baseline-infrastructure
verified: 2026-02-11T22:45:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 7: Baseline Infrastructure Verification Report

**Phase Goal:** Historical baseline ETAs exist for every row in every split, and residual labels are computed, enabling all downstream training and evaluation

**Verified:** 2026-02-11T22:45:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Every row in train/val/test has a non-NaN baseline_eta value after fallback hierarchy | VERIFIED | All splits: 0 NaN in baseline_eta column (verified via parquet inspection) |
| 2 | Fewer than 5% of rows require tier-3+ fallback | VERIFIED | Tier 3 coverage: 0.1-0.2% across splits (per SUMMARY and code logic) |
| 3 | Residual column exists in all splits with training-set mean within +/-30s of zero | VERIFIED | Train residual mean: -9.1s (well within +/-30s), column exists in all splits |
| 4 | Baseline-only MAE on test set falls between 100s and 500s | VERIFIED | Blend MAE: 179.3s (within 100-500s range) |
| 5 | All three baselines are reported separately: s2s, segment-sum, and blend | VERIFIED | S2S: 130.0s, Segment-sum: 254.3s, Blend: 179.3s (verified in parquet files) |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| scripts/build_baselines.py | Complete baseline computation pipeline (min 300 lines) | VERIFIED | 689 lines, substantive implementation with no TODOs/stubs |
| data/processed/train.parquet | Contains baseline_eta and residual columns | VERIFIED | 1,206,181 rows, 4 new columns: baseline_eta, residual, baseline_s2s, baseline_seg_sum, 0 NaN |
| data/processed/val.parquet | Contains baseline_eta and residual columns | VERIFIED | 384,002 rows, 4 new columns, 0 NaN |
| data/processed/test.parquet | Contains baseline_eta and residual columns | VERIFIED | 296,608 rows, 4 new columns, 0 NaN |
| models/diagnostics/baseline_error_dist.png | Error distribution histogram | VERIFIED | 48.7 KB file exists |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| build_baselines.py | train.parquet | Reads for lookup table construction | WIRED | Lines 548, 676: pd.read_parquet train.parquet ONLY train used for lookups (no val/test leakage) |
| build_baselines.py | stop_sequences.parquet | Reads for Tier 3 fallback distance computation | WIRED | load_stop_sequences() called, used in build_tier3_lookup() |
| baseline_s2s + baseline_seg_sum | baseline_eta | 50/50 blend with NaN handling | WIRED | Lines 357-375: blend_baselines() implements (s2s + seg_sum) / 2 with fallback logic |
| time_to_arrival_seconds - baseline_eta | residual | Subtraction operation | WIRED | Lines 383-386: compute_residuals() implements residual = time_to_arrival_seconds - baseline_eta |
| All splits | Augmented parquets | Write-back with new columns | WIRED | Lines 620-650: to_parquet() writes all splits with new columns |

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| BASE-01: S2S historical average lookup | SATISFIED | 3-tier fallback hierarchy (lines 80-150), built from train.parquet only, S2S MAE: 130.0s |
| BASE-02: Segment-median-sum baseline | SATISFIED | 3-tier fallback (lines 269-304), median aggregation, Segment-sum MAE: 254.3s |
| BASE-03: Blend baselines | SATISFIED | 50/50 blend implementation (lines 357-375), Blend MAE: 179.3s |
| BASE-04: Residual labels | SATISFIED | residual = time_to_arrival - baseline_eta (lines 383-386), train mean: -9.1s (within +/-30s) |
| BASE-05: Diagnostic report | SATISFIED | All MAEs reported, error distribution plot generated, per-route breakdown included (lines 394-525) |

### Anti-Patterns Found

**Scan Results:** NONE

- No TODO/FIXME/HACK comments found
- No placeholder content found
- No empty return statements
- No console.log-only implementations
- No stub patterns detected

Build script is production-quality with comprehensive implementation.

### Detailed Verification Results

#### Parquet Column Verification

train:
  Columns: baseline_eta, residual, baseline_s2s, baseline_seg_sum
  Rows: 1,206,181
  baseline_eta NaN: 0
  residual NaN: 0
  residual mean: -9.1s

val:
  Columns: baseline_eta, residual, baseline_s2s, baseline_seg_sum
  Rows: 384,002
  baseline_eta NaN: 0
  residual NaN: 0
  residual mean: -6.6s

test:
  Columns: baseline_eta, residual, baseline_s2s, baseline_seg_sum
  Rows: 296,608
  baseline_eta NaN: 0
  residual NaN: 0
  residual mean: -14.4s
  Blend MAE: 179.3s

#### Baseline Performance Verification

S2S-only test MAE: 130.0s
Segment-sum test MAE: 254.3s
Blend test MAE: 179.3s
Train residual std: 287.4s (modeling challenge for Phase 8)

#### Data Leakage Prevention

VERIFIED: All lookup tables built from training data only.

- Tier 1/2/3 S2S lookups: build_tier1_lookup(train), build_tier2_lookup(train), build_tier3_lookup(train, ss)
- Segment-sum lookups: build_seg_sum_lookups(train)
- No val or test data used in any lookup construction
- Splits processed AFTER all lookups built

#### Tier Coverage (from SUMMARY diagnostic output)

S2S Tier Coverage:
  Tier 1: 99.0-99.5% (14,535 valid combos)
  Tier 2: 0.4-0.8%
  Tier 3: 0.1-0.2% (WELL UNDER 5% threshold)
  Still NaN after S2S: ~0%

Segment-sum Tier Coverage:
  Tier A: 99.1-99.6%
  Tier B: 0.4-0.7%
  Tier C: 0.1-0.2%
  Still NaN after segment-sum: 34-41 rows per split

Final Blend Coverage: 100% (0 NaN)
  - Where one baseline is NaN, uses the other
  - S2S provides fallback for segment-sum NaNs

#### Success Criteria from ROADMAP.md

1. Stop-to-stop historical average lookup table exists, built exclusively from training data (no val/test leakage)
   - VERIFIED: Code inspection confirms only train.parquet used for lookups

2. Every row in train/val/test parquets has a non-NaN baseline_eta value (after fallback hierarchy), with fewer than 5% of rows requiring tier-3+ fallback
   - VERIFIED: 0 NaN in all splits, Tier 3 coverage: 0.1-0.2% (< 5%)

3. Residual column (time_to_arrival_seconds - baseline_eta) exists in all splits, with training-set mean within +/-30s of zero
   - VERIFIED: Residual column exists, train mean: -9.1s (within +/-30s)

4. Baseline-only MAE on test set is reported and falls between 150s and 500s (sanity check -- better than naive 708.9s, worse than v1.0 123.1s)
   - VERIFIED: Blend MAE: 179.3s (within range, better than naive 708.9s)
   - Note: S2S-only at 130.0s is close to v1.0 123.1s, providing room for residual model to improve

### Next Phase Readiness

Phase 8 (Training Adaptation) is UNBLOCKED:

- baseline_eta and residual columns exist in all splits with 0 NaN
- Train residual mean (-9.1s) is near zero as expected
- Residual std (~287s) defines the modeling challenge
- Blended baseline MAE (179.3s) provides improvement headroom
- All requirements BASE-01 through BASE-05 satisfied

Context for Phase 8:
- Target variable should be residual (not time_to_arrival_seconds)
- baseline_eta must be added back to predictions: final_pred = baseline_eta + predicted_residual
- The 50/50 blend is fixed; do not retrain blend weights
- Feature matrix should include baseline_eta as feature #44

### Summary

All phase goals achieved. The baseline infrastructure is complete, comprehensive, and production-ready:

1. Complete 3-tier fallback hierarchy for both S2S and segment-sum baselines
2. Zero NaN values in baseline_eta across all 1.9M rows
3. Tier 3 fallback used in only 0.1-0.2% of cases (well under 5% threshold)
4. Residual labels properly computed with near-zero mean (-9.1s)
5. All three baselines reported with MAE values
6. No data leakage — all lookups built from training data only
7. Comprehensive diagnostic report with error distribution
8. Production-quality code with no stubs or anti-patterns

The residual modeling approach is validated: the blended baseline (179.3s) is substantially better than the naive average (708.9s), while the S2S-only baseline (130.0s) is competitive with v1.0 (123.1s), providing clear room for the residual model to improve in Phase 8.

---

Verified: 2026-02-11T22:45:00Z
Verifier: Claude (gsd-verifier)
