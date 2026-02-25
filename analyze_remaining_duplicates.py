#!/usr/bin/env python3
"""
Analyze remaining duplicates after initial deduplication.
Identify types of differences that could potentially be normalized.
"""

import json
from pathlib import Path
from collections import defaultdict, Counter
import re

def normalize_whitespace(text):
    """Normalize whitespace in text."""
    if not isinstance(text, str):
        return text
    return ' '.join(text.split())

def normalize_quotes(text):
    """Normalize smart quotes to regular quotes."""
    if not isinstance(text, str):
        return text
    # Replace smart quotes with regular quotes
    replacements = {
        '\u2018': "'",  # Left single quotation mark
        '\u2019': "'",  # Right single quotation mark
        '\u201c': '"',  # Left double quotation mark
        '\u201d': '"',  # Right double quotation mark
        '\u2013': '-',  # En dash
        '\u2014': '-',  # Em dash
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

def has_only_quote_differences(str1, str2):
    """Check if two strings differ only in quote characters."""
    if not isinstance(str1, str) or not isinstance(str2, str):
        return False
    return normalize_quotes(str1) == normalize_quotes(str2)

def has_only_whitespace_differences(str1, str2):
    """Check if two strings differ only in whitespace."""
    if not isinstance(str1, str) or not isinstance(str2, str):
        return False
    return normalize_whitespace(str1) == normalize_whitespace(str2)

def analyze_field_difference(val1, val2, field_name):
    """
    Analyze the type of difference between two field values.
    Returns a category string.
    """
    if val1 == val2:
        return "identical"

    if type(val1) != type(val2):
        return "type_difference"

    if isinstance(val1, str) and isinstance(val2, str):
        # Check for quote differences
        if has_only_quote_differences(val1, val2):
            return "quote_difference"

        # Check for whitespace differences
        if has_only_whitespace_differences(val1, val2):
            return "whitespace_difference"

        # Check for case differences
        if val1.lower() == val2.lower():
            return "case_difference"

        # Check if one is substring of another
        if val1 in val2 or val2 in val1:
            return "substring_difference"

        # Generic text difference
        return "text_difference"

    # For non-string types
    return "value_difference"

def analyze_remaining_duplicates():
    """Analyze all remaining duplicates to categorize differences."""

    meeting_dates_dir = Path("meeting_dates")

    if not meeting_dates_dir.exists():
        print("Error: meeting_dates directory not found")
        return

    # Track duplicates by legislation number
    number_to_items = defaultdict(list)

    # Statistics
    total_files = 0
    total_items = 0

    # Read all files
    print("Reading all JSON files...")
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
                    if number:
                        number_to_items[number].append({
                            'item': item,
                            'date': date,
                            'file': str(json_file)
                        })
        except Exception as e:
            print(f"Error processing {json_file}: {e}")

    print(f"Processed {total_files} files, {total_items} items")
    print()

    # Find duplicates
    duplicates = {num: items for num, items in number_to_items.items() if len(items) > 1}

    print(f"Legislation numbers with multiple entries: {len(duplicates)}")
    print()

    # Analyze each duplicate
    difference_categories = Counter()
    field_difference_types = defaultdict(Counter)

    examples_by_category = defaultdict(list)

    for number, items in duplicates.items():
        # Compare all pairs
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                item1 = items[i]['item']
                item2 = items[j]['item']

                # Get all fields
                all_fields = set(item1.keys()) | set(item2.keys())
                all_fields.discard('id')  # Ignore ID field

                differences = {}
                for field in all_fields:
                    val1 = item1.get(field)
                    val2 = item2.get(field)

                    if val1 != val2:
                        diff_type = analyze_field_difference(val1, val2, field)
                        differences[field] = diff_type
                        field_difference_types[field][diff_type] += 1

                # Categorize this duplicate pair
                if not differences:
                    category = "no_differences"
                elif len(differences) == 1:
                    field, diff_type = list(differences.items())[0]
                    category = f"{field}_{diff_type}"
                else:
                    category = "multiple_fields"

                difference_categories[category] += 1

                # Save examples (limit to 3 per category)
                if len(examples_by_category[category]) < 3:
                    examples_by_category[category].append({
                        'number': number,
                        'ids': [item1.get('id'), item2.get('id')],
                        'differences': differences,
                        'item1': item1,
                        'item2': item2
                    })

    # Report results
    print("="*60)
    print("ANALYSIS RESULTS")
    print("="*60)
    print()

    print("Categories of duplicate pairs:")
    for category, count in difference_categories.most_common(20):
        print(f"  {category}: {count} pairs")
    print()

    print("="*60)
    print("FIELD-SPECIFIC DIFFERENCES")
    print("="*60)
    print()

    for field in sorted(field_difference_types.keys()):
        print(f"\nField: {field}")
        for diff_type, count in field_difference_types[field].most_common():
            print(f"  {diff_type}: {count}")

    print()
    print("="*60)
    print("EXAMPLES BY CATEGORY")
    print("="*60)

    for category in sorted(examples_by_category.keys()):
        if examples_by_category[category]:
            print(f"\n{category.upper()}:")
            print("-" * 60)

            for i, example in enumerate(examples_by_category[category][:2], 1):
                print(f"\nExample {i}:")
                print(f"  Legislation: {example['number']}")
                print(f"  IDs: {example['ids']}")
                print(f"  Differences: {example['differences']}")

                # Show the actual differences
                for field, diff_type in example['differences'].items():
                    val1 = example['item1'].get(field)
                    val2 = example['item2'].get(field)

                    print(f"\n  Field '{field}' ({diff_type}):")
                    if isinstance(val1, str) and isinstance(val2, str):
                        # Show first 100 chars for readability
                        print(f"    Value 1: {repr(val1[:100])}{'...' if len(val1) > 100 else ''}")
                        print(f"    Value 2: {repr(val2[:100])}{'...' if len(val2) > 100 else ''}")
                    else:
                        print(f"    Value 1: {val1}")
                        print(f"    Value 2: {val2}")

    # Summary recommendations
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)

    quote_diffs = sum(counts['quote_difference'] for counts in field_difference_types.values())
    ws_diffs = sum(counts['whitespace_difference'] for counts in field_difference_types.values())

    print(f"\n1. Quote normalization could resolve: {quote_diffs} field differences")
    print(f"2. Whitespace normalization could resolve: {ws_diffs} field differences")

    print("\nFields most commonly affected:")
    total_by_field = {field: sum(counts.values()) for field, counts in field_difference_types.items()}
    for field, count in sorted(total_by_field.items(), key=lambda x: x[1], reverse=True):
        print(f"  {field}: {count} differences")

if __name__ == "__main__":
    analyze_remaining_duplicates()
