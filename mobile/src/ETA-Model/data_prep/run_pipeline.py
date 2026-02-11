#!/usr/bin/env python3
"""
Entry point for running the GBDT ETA model data preparation pipeline.

Usage:
    python -m data_prep.run_pipeline [options]

Examples:
    # Run with default paths
    python -m data_prep.run_pipeline

    # Specify custom telemetry directory
    python -m data_prep.run_pipeline --telemetry-dir ./my_data

    # Specify custom output directory
    python -m data_prep.run_pipeline --output-dir ./output_v2
"""

import argparse
import sys
from pathlib import Path

from .pipeline import DataPipeline
from .config import DATA_PATHS


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Run GBDT ETA model data preparation pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m data_prep.run_pipeline
  python -m data_prep.run_pipeline --telemetry-dir ./live_data
  python -m data_prep.run_pipeline --output-dir ./output_v2 --no-progress
        """
    )

    parser.add_argument(
        '--telemetry-dir',
        type=Path,
        default=None,
        help='Directory containing JSONL telemetry files (default: live_data/)'
    )

    parser.add_argument(
        '--output-dir',
        type=Path,
        default=None,
        help='Directory for output Parquet files (default: data_prep/output/)'
    )

    parser.add_argument(
        '--gtfs-dir',
        type=Path,
        default=None,
        help='Directory containing GTFS files (default: gtfs_data/)'
    )

    parser.add_argument(
        '--weather-file',
        type=Path,
        default=None,
        help='Path to weather CSV file (default: raw_data/weather_data.csv)'
    )

    parser.add_argument(
        '--arrivals-files',
        type=Path,
        nargs='+',
        default=None,
        help='Paths to arrivals CSV files'
    )

    parser.add_argument(
        '--no-progress',
        action='store_true',
        help='Disable progress bars'
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    print("\n" + "=" * 60)
    print("GBDT ETA Model - Data Preparation Pipeline")
    print("=" * 60)

    # Show configuration
    print("\nConfiguration:")
    print(f"  Telemetry dir: {args.telemetry_dir or DATA_PATHS['telemetry_dir']}")
    print(f"  Output dir: {args.output_dir or DATA_PATHS['output_dir']}")
    print(f"  GTFS dir: {args.gtfs_dir or DATA_PATHS['gtfs_dir']}")
    print(f"  Weather file: {args.weather_file or DATA_PATHS['weather_file']}")

    # Create and run pipeline
    pipeline = DataPipeline(
        telemetry_dir=args.telemetry_dir,
        arrivals_files=args.arrivals_files,
        weather_file=args.weather_file,
        output_dir=args.output_dir,
        gtfs_dir=args.gtfs_dir,
    )

    try:
        output_paths = pipeline.run(show_progress=not args.no_progress)

        print("\n" + "=" * 60)
        print("Output files:")
        for name, path in output_paths.items():
            print(f"  {name}: {path}")
        print("=" * 60)

        return 0

    except Exception as e:
        print(f"\nERROR: Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
