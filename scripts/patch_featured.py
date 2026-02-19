"""Patch featured_v2 parquets with rebuilt baseline columns.

Replaces baseline_s2s, baseline_seg_sum, baseline_eta, and residual in each
{split}_featured_v2.parquet from the corresponding {split}.parquet (which must
have been rebuilt by build_baselines.py first).

Usage:
    python scripts/patch_featured.py
"""

from pathlib import Path
import pandas as pd

DATA_DIR = Path("data/processed")
SPLITS = ["train", "val", "test"]
PATCH_COLS = ["baseline_s2s", "baseline_seg_sum", "baseline_eta", "residual"]


def main():
    for split in SPLITS:
        base_path = DATA_DIR / f"{split}.parquet"
        feat_path = DATA_DIR / f"{split}_featured_v2.parquet"

        print(f"Patching {feat_path.name} ...")
        base = pd.read_parquet(base_path, columns=PATCH_COLS)
        feat = pd.read_parquet(feat_path)

        assert len(base) == len(feat), (
            f"Row count mismatch: {split}.parquet={len(base)}, "
            f"{split}_featured_v2.parquet={len(feat)}"
        )

        for col in PATCH_COLS:
            feat[col] = base[col].values

        feat.to_parquet(feat_path)
        print(f"  {feat_path.name}: {len(feat):,} rows, patched {PATCH_COLS}")

    print("\nDone.")


if __name__ == "__main__":
    main()
