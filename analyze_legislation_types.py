#!/usr/bin/env python3
"""
Analyze legislation numbers to identify all unique types.
Pattern: YY-[TYPE]-####
"""

import json
from pathlib import Path
from collections import Counter
import re

def extract_type(number):
    """
    Extract type from legislation number.
    Pattern: YY-[TYPE]-####

    Returns the TYPE portion or None if pattern doesn't match.
    """
    if not number:
        return None

    # Pattern: two digits, dash, letters, dash, numbers
    match = re.match(r'^\d{2}-([A-Z]+)-\d+$', number.strip())
    if match:
        return match.group(1)

    return None

def main():
    """Analyze all legislation numbers."""
    meeting_dates_dir = Path("meeting_dates")

    if not meeting_dates_dir.exists():
        print("meeting_dates directory not found")
        return

    type_counter = Counter()
    no_type_examples = []
    total_items = 0

    for json_file in meeting_dates_dir.rglob("*.json"):
        try:
            with open(json_file, 'r') as f:
                content = json.load(f)
                data = content.get('data', [])

                for item in data:
                    total_items += 1
                    number = item.get('number', '')
                    leg_type = extract_type(number)

                    if leg_type:
                        type_counter[leg_type] += 1
                    else:
                        # Keep some examples of items without extractable type
                        if len(no_type_examples) < 20:
                            no_type_examples.append({
                                'number': number,
                                'date': json_file.stem
                            })

        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            continue

    # Report results
    print("=" * 80)
    print("LEGISLATION TYPE ANALYSIS")
    print("=" * 80)
    print(f"\nTotal items analyzed: {total_items:,}")
    print(f"Items with extractable type: {sum(type_counter.values()):,}")
    print(f"Items without extractable type: {total_items - sum(type_counter.values()):,}")

    print(f"\nFound {len(type_counter)} unique legislation types:")
    print("-" * 80)

    # Sort by frequency
    for leg_type, count in type_counter.most_common():
        percentage = (count / total_items) * 100
        print(f"{leg_type:15s} {count:8,} ({percentage:5.2f}%)")

    if no_type_examples:
        print("\n" + "=" * 80)
        print("EXAMPLES OF ITEMS WITHOUT EXTRACTABLE TYPE")
        print("=" * 80)
        for example in no_type_examples[:10]:
            print(f"Number: '{example['number']}' (Date: {example['date']})")

if __name__ == "__main__":
    main()
