"""
Split labeled dataset into temporal train/val/test sets.

Reads:  data/processed/labeled.parquet
Writes: data/processed/train.parquet, data/processed/val.parquet, data/processed/test.parquet

Temporal splits (Nov 6 - Dec 20):
  Train: Nov 6 - Dec 1  (26 days)
  Gap:   Dec 2           (1 day, discarded)
  Val:   Dec 3 - Dec 8   (6 days)
  Gap:   Dec 9           (1 day, discarded)
  Test:  Dec 10 - Dec 20 (11 days)
"""

import datetime
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
LABELED_PATH = OUTPUT_DIR / "labeled.parquet"

# Temporal split boundaries
TRAIN_START = datetime.date(2025, 11, 6)
TRAIN_END = datetime.date(2025, 12, 1)  # inclusive
GAP1 = datetime.date(2025, 12, 2)
VAL_START = datetime.date(2025, 12, 3)
VAL_END = datetime.date(2025, 12, 8)    # inclusive
GAP2 = datetime.date(2025, 12, 9)
TEST_START = datetime.date(2025, 12, 10)
TEST_END = datetime.date(2025, 12, 20)  # inclusive


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    print("=" * 60)
    print("Temporal Train/Val/Test Split")
    print("=" * 60)

    # ── Step 1: Load labeled data ────────────────────────────
    print("\n[1] Loading labeled data...")
    df = pd.read_parquet(LABELED_PATH)
    total_rows = len(df)
    print(f"  Total rows: {total_rows:,}")

    # ── Step 2: Extract date column ──────────────────────────
    print("\n[2] Extracting date column...")
    df["date"] = df["timestamp"].dt.date
    date_range = df["date"].unique()
    date_min, date_max = min(date_range), max(date_range)
    print(f"  Date range in data: {date_min} to {date_max}")
    print(f"  Unique dates: {len(date_range)}")

    # ── Step 3: Define and display splits ────────────────────
    print("\n[3] Temporal split boundaries:")
    print(f"  Train: {TRAIN_START} to {TRAIN_END} (inclusive)")
    print(f"  Gap 1: {GAP1}")
    print(f"  Val:   {VAL_START} to {VAL_END} (inclusive)")
    print(f"  Gap 2: {GAP2}")
    print(f"  Test:  {TEST_START} to {TEST_END} (inclusive)")

    # ── Step 4: Assign splits ────────────────────────────────
    print("\n[4] Assigning splits...")

    def assign_split(d: datetime.date) -> str:
        if TRAIN_START <= d <= TRAIN_END:
            return "train"
        elif VAL_START <= d <= VAL_END:
            return "val"
        elif TEST_START <= d <= TEST_END:
            return "test"
        else:
            return "gap"

    df["_split"] = df["date"].apply(assign_split)

    split_counts = df["_split"].value_counts()
    for s in ["train", "val", "test", "gap"]:
        count = split_counts.get(s, 0)
        pct = count / total_rows * 100
        print(f"  {s:>5}: {count:>10,} rows ({pct:.1f}%)")

    # ── Step 5: Add is_weekday flag ──────────────────────────
    print("\n[5] Adding is_weekday flag...")
    df["is_weekday"] = pd.to_datetime(df["date"]).dt.dayofweek < 5
    weekday_pct = df["is_weekday"].mean() * 100
    print(f"  Weekday rows: {weekday_pct:.1f}%")

    # ── Step 6: Validate no trip leakage ─────────────────────
    print("\n[6] Trip leakage check...")
    # No explicit trip_id column exists in the data.
    # The 1-day gap between splits prevents any trip from spanning split boundaries,
    # since transit trips are at most a few hours long.
    print("  No explicit trip_id column. Temporal gaps (1 day each) prevent")
    print("  leakage by design -- transit trips are at most a few hours.")

    # ── Step 7: Write splits ─────────────────────────────────
    print("\n[7] Writing split files...")

    train_df = df[df["_split"] == "train"].drop(columns=["_split"]).copy()
    val_df = df[df["_split"] == "val"].drop(columns=["_split"]).copy()
    test_df = df[df["_split"] == "test"].drop(columns=["_split"]).copy()

    for name, split_df in [("train", train_df), ("val", val_df), ("test", test_df)]:
        out_path = OUTPUT_DIR / f"{name}.parquet"
        split_df.to_parquet(out_path, index=False)
        size_mb = out_path.stat().st_size / 1024 / 1024
        print(f"  {name}.parquet: {len(split_df):,} rows, {size_mb:.1f} MB")

    # ── Step 8: Comprehensive summary ────────────────────────
    elapsed = time.time() - t0
    gap_count = split_counts.get("gap", 0)

    print(f"\n{'=' * 60}")
    print("Temporal Split Summary")
    print(f"{'=' * 60}")
    print(f"  Total labeled rows:         {total_rows:>10,}")
    print(f"  Train rows:                 {len(train_df):>10,} ({len(train_df)/total_rows*100:.1f}%)")
    print(f"  Val rows:                   {len(val_df):>10,} ({len(val_df)/total_rows*100:.1f}%)")
    print(f"  Test rows:                  {len(test_df):>10,} ({len(test_df)/total_rows*100:.1f}%)")
    print(f"  Gap/discarded rows:         {gap_count:>10,} ({gap_count/total_rows*100:.1f}%)")
    print(f"  Sum check:                  {len(train_df)+len(val_df)+len(test_df)+gap_count:>10,}")
    print()

    # Date ranges per split
    for name, split_df in [("Train", train_df), ("Val", val_df), ("Test", test_df)]:
        dates = split_df["date"]
        n_days = dates.nunique()
        print(f"  {name}: {min(dates)} to {max(dates)} ({n_days} days)")

    print()

    # Label distribution per split
    print("  Label distribution per split:")
    print(f"  {'Split':<7} {'Mean':>8} {'Median':>8} {'Std':>8} {'Min':>8} {'Max':>8}")
    for name, split_df in [("Train", train_df), ("Val", val_df), ("Test", test_df)]:
        lbl = split_df["time_to_arrival_seconds"]
        print(f"  {name:<7} {lbl.mean():>8.0f} {lbl.median():>8.0f} {lbl.std():>8.0f} {lbl.min():>8.0f} {lbl.max():>8.0f}")

    print()

    # Routes per split
    for name, split_df in [("Train", train_df), ("Val", val_df), ("Test", test_df)]:
        n_routes = split_df["route_id"].nunique()
        print(f"  {name} routes: {n_routes}")

    print()

    # is_weekday breakdown per split
    print("  is_weekday breakdown:")
    for name, split_df in [("Train", train_df), ("Val", val_df), ("Test", test_df)]:
        wd_pct = split_df["is_weekday"].mean() * 100
        print(f"  {name:<7} weekday: {wd_pct:.1f}%")

    print()
    print(f"  Elapsed: {elapsed:.1f}s")

    # ── Assertions ───────────────────────────────────────────
    assert len(train_df) + len(val_df) + len(test_df) + gap_count == total_rows, "Row count mismatch!"
    assert len(train_df) > len(val_df), "Train should be larger than val!"
    assert len(train_df) > len(test_df), "Train should be larger than test!"
    assert max(train_df["date"]) < min(val_df["date"]), "Train/val date overlap!"
    assert max(val_df["date"]) < min(test_df["date"]), "Val/test date overlap!"

    # Verify gap exists
    train_max = max(train_df["date"])
    val_min = min(val_df["date"])
    val_max = max(val_df["date"])
    test_min = min(test_df["date"])
    assert (val_min - train_max).days >= 2, "No gap between train and val!"
    assert (test_min - val_max).days >= 2, "No gap between val and test!"

    print("All assertions passed.")
    print("Done.")


if __name__ == "__main__":
    main()
