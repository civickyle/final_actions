#!/usr/bin/env python3
"""
Analyze legislation descriptions to identify sponsor patterns.
"""

import json
from pathlib import Path
import re
from collections import Counter

def analyze_sponsor_patterns():
    """Analyze descriptions for sponsor patterns."""
    meeting_dates_dir = Path("meeting_dates")

    # Track different patterns
    sponsor_keywords = Counter()
    sponsor_examples = []
    items_with_sponsors = 0
    total_items = 0

    # Common sponsor keywords to search for
    keywords = [
        r'SPONSOR(?:ED)?\s*BY',
        r'SPONSOR(?:S)?:',
        r'INTRODUCED BY',
        r'COUNCILMEMBER',
        r'COUNCIL\s*MEMBER',
        r'CM\.',
        r'CO-SPONSOR',
    ]

    for json_file in meeting_dates_dir.rglob("*.json"):
        try:
            with open(json_file, 'r') as f:
                content = json.load(f)
                data = content.get('data', [])

                for item in data:
                    total_items += 1
                    description = item.get('description', '')

                    if not description:
                        continue

                    # Check for sponsor keywords
                    found_pattern = False
                    for keyword in keywords:
                        if re.search(keyword, description, re.IGNORECASE):
                            sponsor_keywords[keyword] += 1
                            found_pattern = True

                            # Save examples (limit to 50 per pattern)
                            pattern_examples = [ex for ex in sponsor_examples if ex['pattern'] == keyword]
                            if len(pattern_examples) < 50:
                                sponsor_examples.append({
                                    'pattern': keyword,
                                    'description': description,
                                    'number': item.get('number', ''),
                                    'date': json_file.stem
                                })

                    if found_pattern:
                        items_with_sponsors += 1

        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            continue

    # Report results
    print("=" * 80)
    print("SPONSOR PATTERN ANALYSIS")
    print("=" * 80)
    print(f"\nTotal items analyzed: {total_items:,}")
    print(f"Items with sponsor patterns: {items_with_sponsors:,} ({items_with_sponsors/total_items*100:.2f}%)")

    print(f"\nPattern frequencies:")
    print("-" * 80)
    for pattern, count in sponsor_keywords.most_common():
        percentage = (count / total_items) * 100
        print(f"{pattern:30s} {count:8,} ({percentage:5.2f}%)")

    # Show examples for each pattern
    print("\n" + "=" * 80)
    print("EXAMPLE DESCRIPTIONS BY PATTERN")
    print("=" * 80)

    patterns_shown = set()
    for example in sponsor_examples[:100]:  # Show first 100 examples
        pattern = example['pattern']
        if pattern not in patterns_shown or len([e for e in sponsor_examples if e['pattern'] == pattern and e in sponsor_examples[:100]]) <= 5:
            if pattern not in patterns_shown:
                print(f"\n{'-'*80}")
                print(f"Pattern: {pattern}")
                print(f"{'-'*80}")
                patterns_shown.add(pattern)

            print(f"\n{example['number']} ({example['date']}):")
            # Truncate long descriptions
            desc = example['description']
            if len(desc) > 300:
                desc = desc[:300] + "..."
            print(f"  {desc}")

if __name__ == "__main__":
    analyze_sponsor_patterns()
