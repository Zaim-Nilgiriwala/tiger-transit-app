"""
run_optuna_batches.py - Run Optuna tuning in batches via subprocess.

Each batch invokes train_advanced.py with --batch N --tuning-only,
allowing SQLite persistence across invocations. This avoids
timeout issues with long-running single processes.

Usage:
    python scripts/run_optuna_batches.py
"""

import subprocess
import sys
import time
from pathlib import Path


TARGET_TRIALS = 100
BATCH_SIZE = 25  # trials per invocation


def count_trials():
    """Count completed trials in the SQLite database."""
    try:
        import optuna
        storage = optuna.storages.RDBStorage(url="sqlite:///models/optuna_study.db")
        study = optuna.load_study(study_name="v1_1_residual_tuning", storage=storage)
        return len(study.trials)
    except Exception:
        return 0


def main():
    start = time.time()
    script = Path(__file__).resolve().parent / "train_advanced.py"

    while True:
        done = count_trials()
        remaining = TARGET_TRIALS - done
        if remaining <= 0:
            print(f"\nAll {TARGET_TRIALS} trials complete!")
            break

        batch = min(BATCH_SIZE, remaining)
        print(f"\n{'='*60}")
        print(f"Starting batch: {batch} trials ({done}/{TARGET_TRIALS} done)")
        print(f"{'='*60}")

        result = subprocess.run(
            [sys.executable, str(script), "--batch", str(batch), "--tuning-only"],
            cwd=str(script.parent.parent),
        )

        if result.returncode != 0:
            print(f"\nBatch failed with return code {result.returncode}")
            break

        elapsed = (time.time() - start) / 60
        new_done = count_trials()
        rate = new_done / elapsed if elapsed > 0 else 0
        eta = (TARGET_TRIALS - new_done) / rate if rate > 0 else 0
        print(f"\n  Progress: {new_done}/{TARGET_TRIALS} ({elapsed:.1f} min elapsed, ~{eta:.0f} min remaining)")

    elapsed = (time.time() - start) / 60
    total = count_trials()
    print(f"\n{'='*60}")
    print(f"Batch runner complete: {total} trials in {elapsed:.1f} min")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
