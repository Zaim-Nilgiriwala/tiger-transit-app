"""
Parse weather CSV into a clean parquet file.

Reads weather_data.csv from the raw data directory, keeps only
temperature and precipitation columns, and writes to
data/processed/weather.parquet.
"""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "mobile" / "src" / "ETA-Model" / "raw_data"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_PATH = OUTPUT_DIR / "weather.parquet"

INPUT_PATH = RAW_DATA_DIR / "weather_data.csv"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load
    print(f"Loading {INPUT_PATH}")
    df = pd.read_csv(INPUT_PATH)
    print(f"Raw rows: {len(df):,}")
    print(f"Raw columns: {list(df.columns)}")

    # Parse and rename columns
    df["timestamp"] = pd.to_datetime(df["time"], utc=True)
    df["hour"] = df["timestamp"].dt.floor("h")
    df = df.rename(columns={
        "temperature_2m": "temperature_c",
        "precipitation": "precipitation_mm",
    })

    # Keep only the columns we need
    df = df[["timestamp", "hour", "temperature_c", "precipitation_mm"]].copy()

    # Validate: no nulls
    null_counts = df.isnull().sum()
    if null_counts.any():
        print("\nWARNING: Nulls found!")
        print(null_counts[null_counts > 0])
    else:
        print("\nNull check: zero nulls (all columns clean)")

    assert not df["temperature_c"].isnull().any(), "Nulls in temperature_c!"
    assert not df["precipitation_mm"].isnull().any(), "Nulls in precipitation_mm!"

    # Validation summary
    print(f"\n--- Validation Summary ---")
    print(f"Rows: {len(df):,}")
    print(f"Columns: {list(df.columns)}")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"\nTemperature (C):")
    print(f"  Min: {df['temperature_c'].min():.1f}")
    print(f"  Max: {df['temperature_c'].max():.1f}")
    print(f"  Mean: {df['temperature_c'].mean():.1f}")
    print(f"\nPrecipitation (mm):")
    print(f"  Min: {df['precipitation_mm'].min():.2f}")
    print(f"  Max: {df['precipitation_mm'].max():.2f}")
    print(f"  Hours with precip > 0: {(df['precipitation_mm'] > 0).sum()}")

    # Write parquet
    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"\nWritten to: {OUTPUT_PATH}")
    print(f"File size: {OUTPUT_PATH.stat().st_size / 1024:.1f} KB")
    print("Done.")


if __name__ == "__main__":
    main()
