#!/usr/bin/env python3
"""Extract and deduplicate all 'number' fields from JSON files in meeting_dates folder."""

import json
import os
from pathlib import Path
from typing import Set

def extract_numbers_from_json(file_path: Path) -> Set[str]:
    """Extract all 'number' values from a JSON file."""
    numbers = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if 'data' in data and isinstance(data['data'], list):
                for item in data['data']:
                    if 'number' in item:
                        numbers.add(item['number'])
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
    return numbers

def main():
    # Find all JSON files in meeting_dates folder
    base_path = Path(__file__).parent / 'meeting_dates'
    json_files = list(base_path.rglob('*.json'))

    print(f"Found {len(json_files)} JSON files")

    # Extract all numbers
    all_numbers = set()
    for json_file in json_files:
        numbers = extract_numbers_from_json(json_file)
        all_numbers.update(numbers)

    # Sort the numbers for better readability
    sorted_numbers = sorted(all_numbers)

    print(f"\nTotal unique numbers: {len(sorted_numbers)}")

    # Save to file
    output_file = Path(__file__).parent / 'deduplicated_numbers.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        for number in sorted_numbers:
            f.write(f"{number}\n")

    print(f"\nResults saved to: {output_file}")

    # Also save as JSON
    output_json = Path(__file__).parent / 'deduplicated_numbers.json'
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(sorted_numbers, f, indent=2)

    print(f"JSON results saved to: {output_json}")

    # Print first 10 as sample
    print("\nFirst 10 numbers (sample):")
    for number in sorted_numbers[:10]:
        print(f"  {number}")

if __name__ == '__main__':
    main()
