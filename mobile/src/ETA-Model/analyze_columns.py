"""Analyze CSV columns to understand relationships and derived fields."""
import csv
import json
from datetime import datetime
from collections import defaultdict

def analyze_csv(filepath, max_rows=1000):
    """Analyze column relationships in the CSV."""

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = []
        for i, row in enumerate(reader):
            if i >= max_rows:
                break
            rows.append(row)

    print(f"Analyzed {len(rows)} rows\n")

    # Group columns by prefix
    column_groups = defaultdict(list)
    for col in rows[0].keys():
        if '_' in col:
            prefix = col.split('_')[0]
            column_groups[prefix].append(col)
        else:
            column_groups['root'].append(col)

    print("=" * 80)
    print("COLUMN GROUPS")
    print("=" * 80)
    for group, cols in sorted(column_groups.items()):
        print(f"\n{group}: {len(cols)} columns")
        for col in sorted(cols)[:10]:
            print(f"  - {col}")
        if len(cols) > 10:
            print(f"  ... and {len(cols) - 10} more")

    # Analyze timestamp relationships
    print("\n" + "=" * 80)
    print("TIMESTAMP ANALYSIS")
    print("=" * 80)
    for row in rows[:5]:
        t = int(row['t']) if row['t'] else 0
        ts = int(row['ts']) if row['ts'] else 0
        rcvDate = row['rcvDate']
        vid = row['vid']

        t_dt = datetime.fromtimestamp(t / 1000) if t else None
        ts_dt = datetime.fromtimestamp(ts / 1000) if ts else None

        print(f"\n{vid}:")
        print(f"  t (vehicle time):  {t} -> {t_dt}")
        print(f"  ts (server time):  {ts} -> {ts_dt}")
        print(f"  rcvDate:           {rcvDate}")
        print(f"  Diff (ts - t):     {(ts - t) / 1000:.2f} seconds")

    # Analyze ETA relationships
    print("\n" + "=" * 80)
    print("ETA ANALYSIS")
    print("=" * 80)
    for row in rows[:10]:
        if row['eta_eta'] and row['eta_eta'] != '0':
            vid = row['vid']
            eta = row['eta_eta']
            seta = row['eta_seta']
            heta = row['eta_heta']
            onTime = row['eta_onTime']
            stopID = row['eta_stopID']

            print(f"\n{vid} -> Stop {stopID}:")
            print(f"  eta_eta (predicted):   {eta} seconds")
            print(f"  eta_seta (scheduled):  {seta} seconds")
            print(f"  eta_heta (historical): {heta}")
            print(f"  eta_onTime:            {onTime}")
            if seta and eta:
                try:
                    diff = int(seta) - int(eta)
                    print(f"  seta - eta:            {diff} (positive = arriving early)")
                except:
                    pass

    # Analyze lastStop vs eta relationship
    print("\n" + "=" * 80)
    print("LAST STOP vs CURRENT ETA ANALYSIS")
    print("=" * 80)
    for row in rows[:10]:
        if row['lastStop_stopID'] and row['lastStop_stopID'] != '0':
            vid = row['vid']
            lastStopID = row['lastStop_stopID']
            lastStopTime = row['lastStop_time']
            lastStopOnTime = row['lastStop_onTime']
            lastStopSdTime = row['lastStop_sdTime']
            nextStopID = row['eta_stopID']

            print(f"\n{vid}:")
            print(f"  Last stop:        {lastStopID}")
            print(f"  Last stop time:   {lastStopTime}")
            print(f"  Scheduled time:   {lastStopSdTime}")
            print(f"  onTime at stop:   {lastStopOnTime} seconds")
            print(f"  Next stop:        {nextStopID}")

            if lastStopTime and lastStopSdTime:
                try:
                    actual = int(lastStopTime)
                    scheduled = int(lastStopSdTime)
                    diff_seconds = (actual - scheduled) / 1000
                    print(f"  Calculated diff:  {diff_seconds:.0f} seconds")
                except:
                    pass

    # Analyze serviceState_status codes
    print("\n" + "=" * 80)
    print("SERVICE STATE STATUS CODES")
    print("=" * 80)
    status_counts = defaultdict(lambda: {'count': 0, 'examples': []})
    for row in rows:
        status = row['serviceState_status']
        number = row['serviceState_number']
        status_counts[status]['count'] += 1
        if len(status_counts[status]['examples']) < 3:
            status_counts[status]['examples'].append((row['vid'], number))

    for status, data in sorted(status_counts.items()):
        print(f"\nStatus {status}: {data['count']} occurrences")
        for vid, number in data['examples']:
            print(f"  {vid}: {number}")

    # Analyze nextStopPercentProgress
    print("\n" + "=" * 80)
    print("NEXT STOP PERCENT PROGRESS ANALYSIS")
    print("=" * 80)
    for row in rows[:15]:
        progress = row['serviceState_nextStopPercentProgress']
        if progress and progress != '-1':
            vid = row['vid']
            eta = row['eta_eta']
            nextStop = row['eta_stopID']
            print(f"{vid}: {float(progress)*100:.1f}% to stop {nextStop}, ETA: {eta}s")

    # Analyze schedule_stops JSON
    print("\n" + "=" * 80)
    print("SCHEDULE_STOPS ANALYSIS")
    print("=" * 80)
    for row in rows[:5]:
        stops_json = row['schedule_stops']
        if stops_json and stops_json != '[]':
            vid = row['vid']
            t = int(row['t']) if row['t'] else 0
            current_time_minutes = (t / 1000 / 60) % (24 * 60)  # minutes since midnight

            try:
                stops = json.loads(stops_json)
                print(f"\n{vid} (current time: {current_time_minutes:.1f} min since midnight):")
                for stop in stops:
                    stop_id = stop['id']
                    stop_time = int(stop['time'])  # minutes since midnight
                    stop_type = stop['type']
                    minutes_until = stop_time - current_time_minutes
                    print(f"  Stop {stop_id}: scheduled at {stop_time} min ({stop_time//60}:{stop_time%60:02d}), type={stop_type}, in {minutes_until:.1f} min")
            except:
                pass

    # Analyze tisMM (time in service?)
    print("\n" + "=" * 80)
    print("tisMM ANALYSIS (time since last movement in minutes?)")
    print("=" * 80)
    for row in rows[:15]:
        tisMM = row['tisMM']
        v = row['v']  # speed
        vid = row['vid']
        status = row['serviceState_status']
        number = row['serviceState_number']
        print(f"{vid}: tisMM={tisMM}, speed={v}, status={status}, trip={number}")

if __name__ == '__main__':
    analyze_csv(r'C:\Users\ryanp\OneDrive\Desktop\code\Tiger Transit\mobile\src\ETA-Model\live_data\live_2026-01-15.csv')
