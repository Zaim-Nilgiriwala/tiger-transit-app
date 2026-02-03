# Phase 1: Data Foundation - Research

**Researched:** 2026-02-03
**Domain:** Data ingestion, cleaning, and joining for transit ETA prediction
**Confidence:** HIGH

## Summary

This phase involves parsing five raw data sources (telemetry JSONL, arrivals CSV, GTFS static files, timepoint Excel, weather CSV) into clean DataFrames ready for feature engineering. The project already has substantial existing code in `mobile/src/ETA-Model/data_prep/` that handles much of this pipeline, but the user's CONTEXT.md specifies a fresh, modular approach with independent scripts per data source writing to `data/processed/`.

Key findings from examining the actual data:
- **Telemetry**: 52 JSONL files (2025-11-06 to 2026-01-07), ~850K records/day, flat JSON format with fields: t, vid, lat, lon, heading, speed, load, routeId, patternId, progress, lastStopId, nextStopId, etaSeconds, scheduledEta, isDelayed.
- **Arrivals**: 297K records across 2 CSV files, 40 routes, 155 unique station names. Station names match stops.json almost perfectly (154/155 exact match; only "Recruitment Stop" is unmatched).
- **Timepoint Excel**: 23 sheets, 28 unique timepoint stop names -- only 6/28 match stops.json exactly. The rest are abbreviated (e.g., "Peachtree Apts" vs "Peachtree Apartments"). All have obvious close matches via fuzzy matching.
- **Weather**: 1,680 hourly records (complete, no nulls) covering 2025-11-06 to 2026-01-14. Columns: time, precipitation, precipitation_probability, temperature_2m.
- **GTFS**: Complete with shape_dist_traveled in both shapes.txt (16K points, 130 shapes) and stop_times.txt (8,269 entries, no nulls).

**Primary recommendation:** Build 5 independent Python scripts using pandas + openpyxl + pyarrow (all already installed). Output separate parquet files per source to `data/processed/`. The timepoint-to-GTFS mapping requires a manual JSON mapping file since only 6/28 names match exactly.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 2.3.3 | DataFrame operations, CSV/JSONL parsing, joins | Already installed, standard for tabular data |
| openpyxl | 3.1.5 | Excel parsing (timepoint spreadsheet) | Already installed, reads .xlsx with `data_only=True` for computed values |
| pyarrow | 23.0.0 | Parquet file output | Already installed, fast columnar storage |
| numpy | 2.2.6 | Numeric operations, bounding box checks | Already installed, pandas dependency |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pathlib | stdlib | File path handling | All scripts |
| json | stdlib | JSONL line parsing | Telemetry parser |
| difflib | stdlib | Fuzzy string matching | Timepoint mapping generation |
| logging | stdlib | Warning/info output | All scripts for validation stats |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| openpyxl | xlrd | xlrd only reads .xls (old format), not .xlsx |
| Line-by-line JSON | pd.read_json(lines=True) | pd.read_json is simpler but less control over malformed lines |
| parquet | CSV output | Parquet preserves dtypes, is smaller, and faster to read |

**Installation:** No new packages needed. All are already installed.

## Architecture Patterns

### Recommended Project Structure
```
data/
  processed/
    telemetry.parquet          # Cleaned telemetry (all days merged)
    arrivals.parquet           # Cleaned arrivals with GTFS stop_ids
    gtfs_stops.parquet         # Stop metadata (id, name, lat, lon)
    gtfs_stop_times.parquet    # Schedule with shape_dist_traveled
    gtfs_shapes.parquet        # Shape points for distance calc
    timepoints.parquet         # (route_id, stop_id, scheduled_time) tuples
    weather.parquet            # Hourly weather (temp + precip only)
    timepoint_mapping.json     # Manual mapping: timepoint name -> GTFS stop_id
scripts/
  parse_telemetry.py           # DATA-01
  parse_arrivals.py            # DATA-02
  parse_gtfs.py                # DATA-03
  parse_timepoints.py          # DATA-04
  parse_weather.py             # DATA-05
  generate_timepoint_mapping.py  # Helper: draft mapping for review
```

### Pattern 1: Independent Script with Validation Summary
**What:** Each script loads raw data, cleans it, writes parquet, prints summary stats.
**When to use:** Every parse_*.py script.
**Example:**
```python
def main():
    print("=" * 60)
    print("TELEMETRY PARSER")
    print("=" * 60)

    # Load
    df = load_all_telemetry(RAW_DATA_DIR)
    print(f"Loaded: {len(df):,} rows from {len(files)} files")

    # Filter
    df = apply_filters(df)
    print(f"After filtering: {len(df):,} rows")

    # Validate & summarize
    print(f"\n--- Validation Summary ---")
    print(f"Rows: {len(df):,}")
    print(f"Null rates: {df.isnull().mean().to_dict()}")
    print(f"Routes: {sorted(df['route_id'].unique())}")
    print(f"Vehicles: {df['vid'].nunique()}")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

    # Write
    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"\nWritten to {OUTPUT_PATH}")
```

### Pattern 2: Bounding Box + Speed Filter (Telemetry)
**What:** Vectorized filtering of GPS coordinates and speed.
**When to use:** parse_telemetry.py
**Example:**
```python
# Auburn bounding box (from existing config, verified against data)
LAT_MIN, LAT_MAX = 32.5, 32.7
LON_MIN, LON_MAX = -85.6, -85.4
MAX_SPEED_MPH = 65

def filter_telemetry(df: pd.DataFrame) -> pd.DataFrame:
    mask = (
        (df['lat'] >= LAT_MIN) & (df['lat'] <= LAT_MAX) &
        (df['lon'] >= LON_MIN) & (df['lon'] <= LON_MAX) &
        (df['speed'] <= MAX_SPEED_MPH)
    )
    # Exclude jAUnt, Shuttle, and empty vid
    vid_exclude = df['vid'].str.contains('jAUnt|Shuttle', case=False, na=True)
    mask = mask & ~vid_exclude

    # Exclude inactive: patternId=9998 means NIS (Not In Service)
    mask = mask & (df['patternId'] != 9998)

    # Exclude routeId 777 (appears to be a staging/test route)
    mask = mask & (df['routeId'] != 777)

    return df[mask].copy()
```

### Pattern 3: Weather Join by Floor-to-Hour
**What:** Join telemetry timestamps to hourly weather by flooring to the containing hour.
**When to use:** parse_weather.py or downstream join
**Example:**
```python
def join_weather(telemetry_df: pd.DataFrame, weather_df: pd.DataFrame) -> pd.DataFrame:
    # Floor telemetry timestamp to hour
    telemetry_df['_hour'] = pd.to_datetime(
        telemetry_df['t'], unit='ms'
    ).dt.floor('h')

    # Weather hour column
    weather_df['_hour'] = pd.to_datetime(weather_df['time']).dt.tz_localize(None).dt.floor('h')

    result = telemetry_df.merge(
        weather_df[['_hour', 'temperature_c', 'precipitation_mm']],
        on='_hour', how='left'
    )
    result.drop(columns=['_hour'], inplace=True)
    return result
```

### Anti-Patterns to Avoid
- **Loading all JSONL files into memory at once:** With ~850K rows/day * 52 days = ~44M rows, process in chunks or use concat carefully. Each file is ~100-200MB of JSON text.
- **Using read_only=False for openpyxl:** The timepoint Excel has formulas; `data_only=True` is required to get computed time values instead of formula strings.
- **Imputing weather gaps:** Decision says to re-fetch using getWeatherData.ts, not impute. Current data has zero nulls anyway.
- **Trying to join timepoint names programmatically without review:** Decision requires a manual mapping file that user reviews.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parquet I/O | Custom binary format | `df.to_parquet()` / `pd.read_parquet()` | pyarrow handles compression, dtypes, schema |
| Excel formula evaluation | Parse formula strings | `openpyxl.load_workbook(data_only=True)` | openpyxl reads cached computed values |
| Fuzzy string matching | Levenshtein from scratch | `difflib.get_close_matches()` | Stdlib, handles the 22 unmatched timepoint names well |
| Timestamp conversions | Manual epoch math | `pd.to_datetime(col, unit='ms')` | Handles edge cases, vectorized |
| GPS bounding box | Haversine distance from center | Simple lat/lon range check | Auburn campus is small enough that rectangular bbox works |

**Key insight:** The raw data is remarkably clean (no nulls in weather, 154/155 arrival stations match exactly). The main complexity is the timepoint Excel parsing (irregular layout, multiple sub-tables per sheet) and the timepoint-to-GTFS name mapping (22/28 need manual mapping).

## Common Pitfalls

### Pitfall 1: Timepoint Excel Has Irregular Layout
**What goes wrong:** Each sheet has multiple "sub-routes" side by side separated by blank columns. Row 0 is a description string, row 1 has stop names, row 2+ has times. Some cells are datetime.time objects, some are None.
**Why it happens:** This is a human-maintained schedule spreadsheet, not a database export.
**How to avoid:** Parse each sheet by detecting column groups (separated by None columns). Row 0 contains route variant info (e.g., "South Donahue 1 starts at 7:00 ends at 20:00 Stages at The Mill"). Row 1 has the two timepoint stop names for that variant.
**Warning signs:** Getting formula strings instead of time values (forgot `data_only=True`), or getting None for all computed cells (file was never opened in Excel to compute values -- but testing shows values ARE cached).

### Pitfall 2: Two Different Telemetry JSONL Formats
**What goes wrong:** `raw_data/*.jsonl` has a flat simplified format (`t, vid, lat, lon, speed, routeId...`), while `live_data/*.jsonl` and `sysRpt_*.jsonl` have a rich nested format from the ETA SPOT IRM API (`serviceState.rID, lastStop.stopID, eta.stopID, schedule.stops[...]`).
**Why it happens:** `raw_data` was collected by `batchCollector.js` which flattens the API response; `live_data` stores raw API responses.
**How to avoid:** Use `raw_data/*.jsonl` files exclusively for Phase 1. These are the 52 daily files (2025-11-06 to 2026-01-07) with the flat format. The existing `data_prep/config.py` references `live_data` but this phase's scripts should reference `raw_data`.
**Warning signs:** KeyError on nested fields like `serviceState_rID` when parsing raw_data format.

### Pitfall 3: Route ID Mismatch Between Data Sources
**What goes wrong:** Telemetry uses numeric `routeId` (e.g., 24), arrivals use route long names (e.g., "North Ross"), GTFS uses string route_id (e.g., "24"), and timepoint Excel uses informal names (e.g., "North Ross").
**Why it happens:** Different data sources use different identifiers for the same route.
**How to avoid:** Build a route lookup table from GTFS `routes.txt` that maps: route_id <-> route_short_name <-> route_long_name. Use this to normalize all sources to numeric route_id.
**Warning signs:** Empty joins when trying to match arrivals Route name to telemetry routeId without the lookup.

### Pitfall 4: Telemetry Timestamps Are in Milliseconds (UTC)
**What goes wrong:** Timestamps like `1762430400000` are Unix epoch milliseconds. Weather times are ISO strings in UTC. Arrivals have date + time-of-day strings.
**Why it happens:** Different systems use different timestamp formats.
**How to avoid:** Normalize all timestamps early: `pd.to_datetime(df['t'], unit='ms', utc=True).dt.tz_convert('America/Chicago')` for local time. Weather CSV times are already UTC ISO strings.
**Warning signs:** Weather join produces all nulls because of timezone mismatch. Arrivals times like "0:03:46" wrapping past midnight.

### Pitfall 5: Arrivals CSV Has a Header Row Before the Actual Header
**What goes wrong:** Line 1 is `Start Date:11/06/2025 12:00 AM End Date:01/14/2026 12:00 AM,,,,,,,,,,,`. Line 2 is the actual column header.
**Why it happens:** ETA SPOT export format.
**How to avoid:** Use `pd.read_csv(path, skiprows=1)` to skip the metadata row.
**Warning signs:** Column names become "Start Date:..." instead of "DATE, Vehicle ID, Number, Route..."

### Pitfall 6: Empty Vehicle IDs in Telemetry
**What goes wrong:** Some telemetry records have `"vid": ""` (empty string). These are likely ghost/phantom pings.
**Why it happens:** ETA SPOT API sometimes returns entries with no vehicle ID.
**How to avoid:** Filter out rows where vid is empty/null as part of the cleaning step.
**Warning signs:** Empty string in vehicle ID column causes issues with groupby operations.

## Code Examples

### Loading All Telemetry JSONL Files
```python
import json
import pandas as pd
from pathlib import Path

def load_telemetry(raw_data_dir: Path) -> pd.DataFrame:
    """Load all raw_data JSONL files into a single DataFrame."""
    frames = []
    for f in sorted(raw_data_dir.glob("raw_data_*.jsonl")):
        records = []
        with open(f, 'r') as fh:
            for line in fh:
                try:
                    records.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        if records:
            frames.append(pd.DataFrame(records))
        print(f"  {f.name}: {len(records):,} records")

    df = pd.concat(frames, ignore_index=True)
    # Convert timestamp
    df['timestamp'] = pd.to_datetime(df['t'], unit='ms', utc=True)
    return df
```

### Parsing Timepoint Excel
```python
import openpyxl
from datetime import time as dt_time

def parse_timepoint_sheet(ws, sheet_name: str) -> list[dict]:
    """Parse one sheet of the timepoint Excel into schedule tuples."""
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 3:
        return []

    # Row 0: descriptions (route variant info)
    # Row 1: stop names (timepoint pairs)
    # Row 2+: scheduled times
    descriptions = rows[0]
    stop_names = rows[1]

    # Identify column groups (separated by None columns)
    groups = []
    current_group = []
    for col_idx, name in enumerate(stop_names):
        if name is not None and isinstance(name, str) and name.strip():
            current_group.append((col_idx, name.strip()))
        else:
            if current_group:
                groups.append(current_group)
                current_group = []
    if current_group:
        groups.append(current_group)

    # Parse times for each group
    results = []
    for group in groups:
        for row_idx in range(2, len(rows)):
            for col_idx, stop_name in group:
                val = rows[row_idx][col_idx] if col_idx < len(rows[row_idx]) else None
                if isinstance(val, dt_time):
                    results.append({
                        'sheet_name': sheet_name,
                        'stop_name': stop_name,
                        'scheduled_time': val,
                    })
    return results
```

### Building Route Lookup from GTFS
```python
def build_route_lookup(gtfs_dir: Path) -> pd.DataFrame:
    """Build route ID/name lookup from GTFS routes.txt."""
    routes = pd.read_csv(gtfs_dir / 'routes.txt')
    # route_id is string in GTFS but numeric in telemetry
    routes['route_id_num'] = pd.to_numeric(
        routes['route_id'].str.split('_').str[0], errors='coerce'
    )
    return routes[['route_id', 'route_id_num', 'route_short_name', 'route_long_name']]
```

### Arrivals Station-to-StopID Mapping
```python
def map_arrivals_stations(arrivals_df: pd.DataFrame, stops_json_path: Path) -> pd.DataFrame:
    """Map arrival station names to numeric GTFS stop IDs."""
    with open(stops_json_path) as f:
        stops = json.load(f)

    name_to_id = {}
    for s in stops:
        name = s['name'].strip()
        if name not in name_to_id:
            name_to_id[name] = int(s['id'])

    arrivals_df['stop_id'] = arrivals_df['Station'].str.strip().map(name_to_id)

    unmatched = arrivals_df[arrivals_df['stop_id'].isna()]['Station'].unique()
    if len(unmatched) > 0:
        print(f"WARNING: {len(unmatched)} unmatched stations: {unmatched}")

    return arrivals_df
```

## Data Inventory (Verified)

### Telemetry JSONL (`raw_data/raw_data_YYYY-MM-DD.jsonl`)
| Field | Type | Notes |
|-------|------|-------|
| t | int (ms epoch) | Unix timestamp in milliseconds |
| vid | string | Vehicle ID, e.g., "21-155", "jAUnt 9", "" (empty) |
| lat | float | GPS latitude |
| lon | float | GPS longitude |
| heading | int | Degrees 0-360 |
| speed | int | Speed in mph |
| load | int | Passenger count |
| routeId | int | Numeric route ID (matches GTFS route_id for most) |
| patternId | int | 9998 = Not In Service (NIS) |
| progress | float | -1 when inactive, 0-1 when active |
| lastStopId | int | 0 when inactive |
| lastStopTime | int/null | Epoch ms or null |
| lastStopOnTime | int | Delay in minutes (?) |
| nextStopId | int | 0 when inactive |
| etaSeconds | int | ETA to next stop in seconds |
| scheduledEta | int | Scheduled ETA in seconds |
| isDelayed | bool | Whether vehicle is delayed |

**Files:** 52 daily files, ~850K records/day, ~44M total records
**Date range:** 2025-11-06 to 2026-01-07

### Arrivals CSV
| Field | Type | Notes |
|-------|------|-------|
| DATE | string | "11/6/2025" format |
| Vehicle ID | string | e.g., "21-155", "jAUnt 2" |
| Number | string | Trip number or "NIS" |
| Route | string | Route long name, e.g., "North Ross" |
| Station | string | Stop name (154/155 match stops.json exactly) |
| ARRIVAL | string | Time "H:MM:SS" format |
| DEPARTURE | string | Time "H:MM:SS" format |
| Dwell (sec) | int | Dwell time at stop |
| APC Boardings/Alightings | int | Passenger counts |

**Files:** 2 CSV files (Nov-Jan and Jan), 297K total records, skiprows=1 required

### Weather CSV
| Field | Type | Notes |
|-------|------|-------|
| time | ISO string | UTC, hourly "2025-11-06T00:00:00.000Z" |
| precipitation | float | mm, zero nulls |
| precipitation_probability | float | 0-100, zero nulls |
| temperature_2m | float | Celsius, zero nulls |

**Coverage:** 1,680 hours (2025-11-06 to 2026-01-14), complete

### GTFS Static Files
- **stops.txt**: 179 stops with lat/lon
- **stop_times.txt**: 8,269 entries with shape_dist_traveled (no nulls)
- **trips.txt**: 1,041 trips mapping route_id to shape_id
- **shapes.txt**: 16,638 points across 130 shapes with shape_dist_traveled
- **routes.txt**: 39 routes

### Timepoint Excel
- **Sheets:** 23 (one per route)
- **Structure:** Multiple sub-tables per sheet (route variants), separated by blank columns
- **Row 0:** Description string ("South Donahue 1 starts at 7:00 ends at 20:00...")
- **Row 1:** Timepoint stop names (2 stops per sub-table)
- **Row 2+:** Scheduled times as datetime.time objects (with `data_only=True`)
- **Unique timepoint names:** 28, of which only 6 match stops.json exactly

## Discretion Recommendations

### Zero-Speed Ping Handling
**Recommendation: Keep all zero-speed pings.** Idle/dwell time at stops is meaningful signal for ETA prediction (vehicles hold at timepoints). Deduplicating would lose dwell information. Downstream feature engineering can compute dwell-related features from these pings.

### Output File Structure
**Recommendation: Separate parquet files per source** (as shown in Architecture Patterns). Reasons:
1. Each script is independently runnable (per user decision)
2. Downstream phases can load only what they need
3. Pre-joining would create coupling between scripts
4. Parquet files are fast to load and join later

### Column Naming Conventions
**Recommendation: snake_case throughout.** Rename raw fields to descriptive snake_case:
- `t` -> `timestamp_ms`
- `vid` -> `vehicle_id`
- `routeId` -> `route_id`
- `patternId` -> `pattern_id`
- `lastStopId` -> `last_stop_id`
- `nextStopId` -> `next_stop_id`
- `etaSeconds` -> `eta_seconds`
- `scheduledEta` -> `scheduled_eta_seconds`
- `isDelayed` -> `is_delayed`
- `lastStopTime` -> `last_stop_time_ms`
- `lastStopOnTime` -> `last_stop_on_time`

### Auburn Bounding Box
**Recommendation:** Use the values from the existing `data_prep/config.py` which are already validated:
- Latitude: 32.5 to 32.7
- Longitude: -85.6 to -85.4

This covers all of Auburn and its transit routes generously.

### Additional Route/Vehicle Exclusions
**Recommendation:** Beyond jAUnt (routeId=232) and Shuttle vehicles, also exclude:
- **routeId=777**: Appears in data, not in GTFS routes.txt. Likely a staging/internal route.
- **routeId=230 (Charter)**: Not a regular transit route.
- **routeId=231 (University Express/Vans)**: Not a regular bus route.
- **Empty vid** (`""`): Ghost pings with no vehicle identification.
- **All GDS routes** (216-228): Game Day Shuttle routes -- different operating patterns, not useful for regular ETA prediction.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| CSV output files | Parquet files | pandas 1.0+ (2020) | 5-10x faster I/O, type preservation |
| Manual JSON parsing | `pd.read_json(lines=True)` | pandas 0.21+ | Simpler but less error control |
| xlrd for Excel | openpyxl | xlrd dropped xlsx support in 2.0 (2020) | openpyxl is the only option for .xlsx |

## Open Questions

1. **Timepoint mapping completeness**
   - What we know: 6/28 timepoint names match exactly, 22 have obvious fuzzy matches
   - What's unclear: Some like "HUB" and "Museum" have no close fuzzy match -- need domain knowledge to identify the correct GTFS stop
   - Recommendation: generate_timepoint_mapping.py drafts the mapping using fuzzy matching, user fills in the blanks before parse_timepoints.py runs

2. **Arrivals time format and midnight wrapping**
   - What we know: Arrival times are in "H:MM:SS" format (e.g., "0:03:46"), combined with DATE column
   - What's unclear: Whether times past midnight (e.g., "0:03:46" on 11/6) mean late night 11/5 or early morning 11/6
   - Recommendation: Combine DATE + ARRIVAL into full datetime, handle edge cases during parse

3. **Route ID format inconsistency in GTFS**
   - What we know: Some GTFS route_ids are compound strings like "215_202_201_156" (South Auburn) or "226_32" (South Quad/Fine Arts)
   - What's unclear: Telemetry routeId=215 -- does this match GTFS "215_202_201_156"?
   - Recommendation: Build mapping that handles both exact match and prefix match for compound IDs

4. **Weather data coverage gap after Jan 7**
   - What we know: Telemetry goes to Jan 7, weather goes to Jan 14, but there's also a second arrivals file through Jan 23
   - What's unclear: Whether additional telemetry data (beyond Jan 7) will be added
   - Recommendation: Weather is sufficient for current telemetry range; extend via getWeatherData.ts if new telemetry is added

## Sources

### Primary (HIGH confidence)
- Direct examination of all data files in the repository
- `mobile/src/ETA-Model/raw_data/` - telemetry JSONL, arrivals CSV, weather CSV, timepoint Excel
- `gtfs_data/` - all GTFS static files
- `mobile/src/ETA-Model/stops.json` - stop metadata
- `mobile/src/ETA-Model/data_prep/config.py` - existing config with validated constants
- Verified: pandas 2.3.3, openpyxl 3.1.5, pyarrow 23.0.0, numpy 2.2.6 all installed

### Secondary (MEDIUM confidence)
- `mobile/src/ETA-Model/data_prep/` - existing pipeline code patterns (reference, not reuse)
- `mobile/src/ETA-Model/CLAUDE.md` - project architecture documentation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already installed and verified
- Architecture: HIGH - based on direct examination of all data files and their formats
- Data inventory: HIGH - every field, file count, and match rate verified by running code
- Pitfalls: HIGH - discovered by actually parsing the data and finding the issues
- Timepoint mapping: MEDIUM - fuzzy matching works for 22/28, but 2 names ("HUB", "Museum") need domain knowledge

**Research date:** 2026-02-03
**Valid until:** 2026-03-03 (data files are static historical data, unlikely to change)
