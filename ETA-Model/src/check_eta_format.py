"""
Check the format of etaSeconds field.

Hypothesis: etaSeconds is minutes since midnight (local time),
not seconds until arrival.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

def check_eta_format(telemetry_path: str):
    """Check if etaSeconds is minutes since midnight."""

    print("=" * 70)
    print("CHECKING etaSeconds FORMAT")
    print("=" * 70)

    # Load some telemetry records
    records = []
    with open(telemetry_path, 'r') as f:
        for i, line in enumerate(f):
            if i >= 100:  # Just check first 100
                break
            if line.strip():
                try:
                    records.append(json.loads(line))
                except:
                    continue

    print(f"\nAnalyzing {len(records)} telemetry records...\n")
    print(f"{'Timestamp (UTC)':<20} {'Local Time':<15} {'etaSeconds':<12} {'As Time':<12} {'Diff (min)':<10}")
    print("-" * 75)

    for rec in records[:20]:
        ts_ms = rec.get('t', 0)
        eta_val = rec.get('etaSeconds')

        if not eta_val or eta_val == 0:
            continue

        # Convert timestamp to datetime
        dt_utc = datetime.utcfromtimestamp(ts_ms / 1000)

        # Convert to Central Time (UTC - 6 for Nov/Dec)
        dt_local = dt_utc - timedelta(hours=6)

        # Current time as minutes since midnight
        current_minutes = dt_local.hour * 60 + dt_local.minute

        # If etaSeconds is minutes since midnight, convert to time
        eta_hour = int(eta_val) // 60
        eta_min = int(eta_val) % 60
        eta_as_time = f"{eta_hour:02d}:{eta_min:02d}"

        # Difference between eta time and current time
        diff_min = int(eta_val) - current_minutes

        print(f"{dt_utc.strftime('%Y-%m-%d %H:%M:%S'):<20} "
              f"{dt_local.strftime('%H:%M:%S'):<15} "
              f"{eta_val:<12} "
              f"{eta_as_time:<12} "
              f"{diff_min:<10}")

    print("\n" + "=" * 70)
    print("INTERPRETATION")
    print("=" * 70)
    print("""
If etaSeconds = 420:
  - As seconds: 420s = 7 minutes until arrival
  - As minutes since midnight: 420min = 7:00 AM (scheduled arrival time)

If etaSeconds = 500:
  - As seconds: 500s = 8.3 minutes until arrival
  - As minutes since midnight: 500min = 8:20 AM (scheduled arrival time)

The 'Diff (min)' column shows how many minutes until the scheduled
arrival time IF etaSeconds is minutes since midnight.
""")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        check_eta_format(sys.argv[1])
    else:
        print("Usage: python check_eta_format.py <telemetry.jsonl>")
