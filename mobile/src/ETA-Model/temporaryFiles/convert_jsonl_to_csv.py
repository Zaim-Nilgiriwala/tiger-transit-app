import json
import csv
import sys

def flatten_dict(d, parent_key='', sep='_'):
    """Flatten a nested dictionary."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def convert_jsonl_to_csv(input_file, output_file):
    # First pass: collect all unique keys
    print("First pass: collecting all column headers...")
    all_keys = set()
    line_count = 0

    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                flat = flatten_dict(data)
                all_keys.update(flat.keys())
                line_count += 1
                if line_count % 100000 == 0:
                    print(f"  Scanned {line_count} lines...")

    print(f"Found {len(all_keys)} columns across {line_count} records")

    # Sort keys for consistent column order
    sorted_keys = sorted(all_keys)

    # Second pass: write CSV
    print("Second pass: writing CSV...")
    with open(input_file, 'r', encoding='utf-8') as infile, \
         open(output_file, 'w', newline='', encoding='utf-8') as outfile:

        writer = csv.DictWriter(outfile, fieldnames=sorted_keys, extrasaction='ignore')
        writer.writeheader()

        line_count = 0
        for line in infile:
            if line.strip():
                data = json.loads(line)
                flat = flatten_dict(data)
                writer.writerow(flat)
                line_count += 1
                if line_count % 100000 == 0:
                    print(f"  Written {line_count} rows...")

    print(f"Done! Converted {line_count} records to {output_file}")

if __name__ == "__main__":
    input_file = "raw_data/raw_data_2025-10-20.jsonl"
    output_file = "raw_data/raw_data_2025-10-20.csv"
    convert_jsonl_to_csv(input_file, output_file)
