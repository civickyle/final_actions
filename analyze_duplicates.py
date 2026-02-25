#!/usr/bin/env python3
"""
Analyze legislation data for duplicates.
For each unique legislation "number", count how many different "id" values exist.
"""

import json
from pathlib import Path
from collections import defaultdict

def analyze_duplicates():
    """Analyze all JSON files for duplicate legislation entries."""

    # Dictionary to track: number -> set of IDs
    number_to_ids = defaultdict(set)

    # Dictionary to track: number -> list of (date, id) tuples
    number_details = defaultdict(list)

    total_files = 0
    total_items = 0

    # Walk through all JSON files
    meeting_dates_dir = Path("meeting_dates")

    if not meeting_dates_dir.exists():
        print("Error: meeting_dates directory not found")
        return

    for json_file in meeting_dates_dir.rglob("*.json"):
        total_files += 1

        try:
            with open(json_file, 'r') as f:
                content = json.load(f)
                data = content.get('data', [])
                date = content.get('date', 'unknown')

                for item in data:
                    total_items += 1
                    number = item.get('number')
                    item_id = item.get('id')

                    if number and item_id:
                        number_to_ids[number].add(item_id)
                        number_details[number].append((date, item_id))

        except Exception as e:
            print(f"Error processing {json_file}: {e}")

    # Analysis
    print(f"Total files analyzed: {total_files}")
    print(f"Total legislation items: {total_items}")
    print(f"Unique legislation numbers: {len(number_to_ids)}")
    print()

    # Count duplicates
    duplicates = {num: ids for num, ids in number_to_ids.items() if len(ids) > 1}

    if duplicates:
        print(f"Legislation numbers with multiple IDs: {len(duplicates)}")
        print()

        # Show distribution
        duplicate_counts = defaultdict(int)
        for num, ids in duplicates.items():
            duplicate_counts[len(ids)] += 1

        print("Distribution of ID counts per legislation number:")
        for count in sorted(duplicate_counts.keys()):
            print(f"  {count} IDs: {duplicate_counts[count]} legislation numbers")
        print()

        # Show examples of duplicates
        print("Sample duplicates (first 10):")
        for i, (num, ids) in enumerate(list(duplicates.items())[:10]):
            print(f"\n  Legislation: {num}")
            print(f"  Number of unique IDs: {len(ids)}")
            print(f"  IDs: {sorted(ids)}")

            # Show dates where this appears
            dates = [date for date, _ in number_details[num]]
            unique_dates = sorted(set(dates))
            print(f"  Appears on {len(unique_dates)} unique date(s): {', '.join(unique_dates[:5])}")
    else:
        print("No duplicates found - each legislation number has exactly one ID")

    # Overall statistics
    print("\n" + "="*60)
    print("Summary Statistics:")
    print("="*60)

    single_id = sum(1 for ids in number_to_ids.values() if len(ids) == 1)
    multiple_ids = len(duplicates)

    print(f"Legislation numbers with single ID: {single_id}")
    print(f"Legislation numbers with multiple IDs: {multiple_ids}")

    if number_to_ids:
        avg_ids = sum(len(ids) for ids in number_to_ids.values()) / len(number_to_ids)
        max_ids = max(len(ids) for ids in number_to_ids.values())
        max_num = [num for num, ids in number_to_ids.items() if len(ids) == max_ids][0]

        print(f"Average IDs per legislation number: {avg_ids:.2f}")
        print(f"Maximum IDs for a single number: {max_ids} (legislation: {max_num})")

if __name__ == "__main__":
    analyze_duplicates()
