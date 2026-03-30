"""Convert JSONL file to CSV with sensible flattening (arrays kept as JSON)."""
import json
import csv
from pathlib import Path


def flatten_dict(d, parent_key='', sep='_', max_depth=2, current_depth=0):
    """Flatten a nested dictionary up to max_depth, keeping arrays as JSON strings."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict) and current_depth < max_depth:
            items.extend(flatten_dict(v, new_key, sep=sep, max_depth=max_depth,
                                      current_depth=current_depth + 1).items())
        elif isinstance(v, list):
            # Keep arrays as JSON strings
            items.append((new_key, json.dumps(v)))
        elif isinstance(v, dict):
            # Keep deep dicts as JSON strings
            items.append((new_key, json.dumps(v)))
        else:
            items.append((new_key, v))
    return dict(items)


def convert_jsonl_to_csv(input_path, output_path):
    """Convert JSONL to CSV."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    # First pass: collect all unique keys
    all_keys = set()
    row_count = 0

    print(f"Scanning {input_path} to collect all fields...")
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    record = json.loads(line)
                    flat = flatten_dict(record)
                    all_keys.update(flat.keys())
                    row_count += 1
                    if row_count % 100000 == 0:
                        print(f"  Scanned {row_count:,} records...")
                except json.JSONDecodeError:
                    continue

    print(f"Found {len(all_keys)} unique fields across {row_count:,} records")

    # Sort keys for consistent column order
    sorted_keys = sorted(all_keys)

    # Second pass: write CSV
    print(f"Writing CSV to {output_path}...")
    with open(input_path, 'r', encoding='utf-8') as infile, \
         open(output_path, 'w', encoding='utf-8', newline='') as outfile:

        writer = csv.DictWriter(outfile, fieldnames=sorted_keys, extrasaction='ignore')
        writer.writeheader()

        row_count = 0
        for line in infile:
            if line.strip():
                try:
                    record = json.loads(line)
                    flat = flatten_dict(record)
                    writer.writerow(flat)
                    row_count += 1
                    if row_count % 100000 == 0:
                        print(f"  Written {row_count:,} records...")
                except json.JSONDecodeError:
                    continue

    print(f"Done! Wrote {row_count:,} records to {output_path}")


if __name__ == '__main__':
    input_file = Path(__file__).parent / 'live_data' / 'live_2026-01-15.jsonl'
    output_file = Path(__file__).parent / 'live_data' / 'live_2026-01-15.csv'
    convert_jsonl_to_csv(input_file, output_file)
