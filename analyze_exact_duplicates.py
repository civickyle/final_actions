#!/usr/bin/env python3
"""
Analyze legislation data for exact duplicates.
Find items that are identical in all fields except the "id" field.
"""

import json
from pathlib import Path
from collections import defaultdict
import hashlib

def create_fingerprint(item):
    """
    Create a fingerprint of an item excluding the 'id' field.
    Returns a hash of all other fields.
    """
    # Create a copy without the 'id' field
    item_without_id = {k: v for k, v in item.items() if k != 'id'}

    # Convert to a sorted JSON string for consistent hashing
    fingerprint_str = json.dumps(item_without_id, sort_keys=True)

    # Return hash
    return hashlib.md5(fingerprint_str.encode()).hexdigest()

def analyze_exact_duplicates():
    """Analyze all JSON files for exact duplicate legislation entries."""

    # Dictionary to track: fingerprint -> list of (id, date, item) tuples
    fingerprint_to_items = defaultdict(list)

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
                    item_id = item.get('id')
                    fingerprint = create_fingerprint(item)

                    fingerprint_to_items[fingerprint].append({
                        'id': item_id,
                        'date': date,
                        'item': item
                    })

        except Exception as e:
            print(f"Error processing {json_file}: {e}")

    # Analysis
    print(f"Total files analyzed: {total_files}")
    print(f"Total legislation items: {total_items}")
    print(f"Unique legislation (excluding ID): {len(fingerprint_to_items)}")
    print()

    # Find exact duplicates
    exact_duplicates = {fp: items for fp, items in fingerprint_to_items.items() if len(items) > 1}

    if exact_duplicates:
        print(f"Legislation with exact duplicates: {len(exact_duplicates)}")
        print()

        # Count total duplicate items
        total_duplicate_items = sum(len(items) for items in exact_duplicates.values())
        unique_items = len(fingerprint_to_items)

        print(f"Total items: {total_items}")
        print(f"Unique items (after deduplication): {unique_items}")
        print(f"Duplicate items that could be removed: {total_items - unique_items}")
        print()

        # Show distribution
        duplicate_counts = defaultdict(int)
        for items in exact_duplicates.values():
            duplicate_counts[len(items)] += 1

        print("Distribution of duplicate counts:")
        for count in sorted(duplicate_counts.keys()):
            print(f"  {count} copies: {duplicate_counts[count]} unique legislation")
        print()

        # Show examples
        print("Sample exact duplicates (first 5):")
        for i, (fp, items) in enumerate(list(exact_duplicates.items())[:5]):
            print(f"\n  Example {i+1}:")
            print(f"  Number of copies: {len(items)}")

            # Show the first item's data (without id)
            first_item = items[0]['item']
            print(f"  Legislation Number: {first_item.get('number', 'N/A')}")
            print(f"  Description: {first_item.get('description', 'N/A')[:100]}...")
            print(f"  Legislation Date: {first_item.get('legislationDate', 'N/A')}")

            # Show all the different IDs and dates
            print(f"  IDs found:")
            for item_info in items[:10]:  # Show first 10
                print(f"    - ID {item_info['id']} on {item_info['date']}")
            if len(items) > 10:
                print(f"    ... and {len(items) - 10} more")
    else:
        print("No exact duplicates found!")

    print("\n" + "="*60)
    print("Summary Statistics:")
    print("="*60)

    unique_count = len(fingerprint_to_items)
    duplicate_count = len(exact_duplicates)

    print(f"Unique legislation: {unique_count}")
    print(f"Legislation with exact duplicates: {duplicate_count}")
    print(f"Percentage with duplicates: {(duplicate_count/unique_count*100):.1f}%")

    if exact_duplicates:
        avg_copies = sum(len(items) for items in exact_duplicates.values()) / len(exact_duplicates)
        max_copies = max(len(items) for items in exact_duplicates.values())
        max_fp = [fp for fp, items in exact_duplicates.items() if len(items) == max_copies][0]
        max_item = exact_duplicates[max_fp][0]['item']

        print(f"Average copies per duplicated legislation: {avg_copies:.2f}")
        print(f"Maximum copies: {max_copies}")
        print(f"  Number: {max_item.get('number', 'N/A')}")
        print(f"  Description: {max_item.get('description', 'N/A')[:80]}...")

if __name__ == "__main__":
    analyze_exact_duplicates()
