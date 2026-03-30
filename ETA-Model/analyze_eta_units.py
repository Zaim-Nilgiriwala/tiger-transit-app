"""Analyze whether ETA values are in seconds or minutes."""
import csv
import json

def analyze_eta_units(filepath, max_rows=500):
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)[:max_rows]

    print("=" * 80)
    print("COMPARING eta_seta WITH schedule_stops TIMES")
    print("=" * 80)

    for row in rows[:20]:
        if row['schedule_stops'] and row['schedule_stops'] != '[]' and row['eta_stopID'] != '0':
            vid = row['vid']
            eta_eta = row['eta_eta']
            eta_seta = row['eta_seta']
            eta_stopID = row['eta_stopID']
            eta_psid = row['eta_patternStopID']

            try:
                stops = json.loads(row['schedule_stops'])
                print(f"\n{vid}:")
                print(f"  eta_stopID: {eta_stopID}, eta_patternStopID: {eta_psid}")
                print(f"  eta_eta: {eta_eta}, eta_seta: {eta_seta}")
                print(f"  Schedule stops:")
                for stop in stops:
                    marker = " <-- MATCH" if str(stop['psid']) == eta_psid else ""
                    print(f"    Stop {stop['id']}, psid={stop['psid']}, time={stop['time']} min{marker}")

                # Check if eta_seta matches any schedule time
                for stop in stops:
                    if str(stop['psid']) == eta_psid:
                        sched_time = int(stop['time'])
                        print(f"  --> schedule time: {sched_time} min, eta_seta: {eta_seta}")
                        if str(sched_time) == eta_seta:
                            print(f"      EXACT MATCH! eta_seta is minutes since midnight")
                        else:
                            diff = sched_time - int(eta_seta) if eta_seta else 0
                            print(f"      Difference: {diff} minutes")
            except Exception as e:
                print(f"  Error: {e}")

    print("\n" + "=" * 80)
    print("ETA VALUE DISTRIBUTION")
    print("=" * 80)

    eta_values = []
    for row in rows:
        if row['eta_eta'] and row['eta_eta'] != '0':
            try:
                eta_values.append(int(row['eta_eta']))
            except:
                pass

    if eta_values:
        print(f"Min eta_eta: {min(eta_values)}")
        print(f"Max eta_eta: {max(eta_values)}")
        print(f"Mean eta_eta: {sum(eta_values)/len(eta_values):.1f}")

        print("\nIf these are SECONDS:")
        print(f"  Min: {min(eta_values)} sec = {min(eta_values)/60:.1f} min")
        print(f"  Max: {max(eta_values)} sec = {max(eta_values)/60:.1f} min")

        print("\nIf these are MINUTES:")
        print(f"  Min: {min(eta_values)} min")
        print(f"  Max: {max(eta_values)} min = {max(eta_values)/60:.1f} hours")

    print("\n" + "=" * 80)
    print("CROSS-REFERENCE: eta_seta vs schedule time for matching psid")
    print("=" * 80)

    matches = 0
    mismatches = 0
    for row in rows:
        if row['schedule_stops'] and row['schedule_stops'] != '[]' and row['eta_patternStopID']:
            try:
                stops = json.loads(row['schedule_stops'])
                eta_psid = row['eta_patternStopID']
                eta_seta = row['eta_seta']

                for stop in stops:
                    if str(stop['psid']) == eta_psid:
                        if stop['time'] == eta_seta:
                            matches += 1
                        else:
                            mismatches += 1
                        break
            except:
                pass

    print(f"eta_seta == schedule_stops.time: {matches} matches, {mismatches} mismatches")
    if matches > mismatches:
        print("\n>>> eta_seta appears to be MINUTES SINCE MIDNIGHT (matches schedule times)")
    else:
        print("\n>>> eta_seta does NOT directly match schedule times")

if __name__ == '__main__':
    analyze_eta_units(r'C:\Users\ryanp\OneDrive\Desktop\code\Tiger Transit\mobile\src\ETA-Model\live_data\live_2026-01-15.csv')
