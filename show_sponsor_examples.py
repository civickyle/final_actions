#!/usr/bin/env python3
"""
Show detailed examples of sponsor patterns.
"""

import json
from pathlib import Path
import re

def show_examples():
    """Show examples of different sponsor patterns."""
    meeting_dates_dir = Path("meeting_dates")

    examples = {
        'BY COUNCILMEMBER': [],
        'BY COUNCIL MEMBER': [],
        'SPONSORED BY': [],
        'CO-SPONSOR': [],
        'INTRODUCED BY': [],
    }

    for json_file in meeting_dates_dir.rglob("*.json"):
        try:
            with open(json_file, 'r') as f:
                content = json.load(f)
                data = content.get('data', [])

                for item in data:
                    description = item.get('description', '')

                    if not description:
                        continue

                    # Check for different patterns
                    if 'BY COUNCILMEMBER' in description and len(examples['BY COUNCILMEMBER']) < 10:
                        examples['BY COUNCILMEMBER'].append({
                            'number': item.get('number', ''),
                            'description': description,
                            'date': json_file.stem
                        })

                    if 'BY COUNCIL MEMBER' in description and len(examples['BY COUNCIL MEMBER']) < 10:
                        examples['BY COUNCIL MEMBER'].append({
                            'number': item.get('number', ''),
                            'description': description,
                            'date': json_file.stem
                        })

                    if 'SPONSORED BY' in description and len(examples['SPONSORED BY']) < 10:
                        examples['SPONSORED BY'].append({
                            'number': item.get('number', ''),
                            'description': description,
                            'date': json_file.stem
                        })

                    if 'CO-SPONSOR' in description and len(examples['CO-SPONSOR']) < 10:
                        examples['CO-SPONSOR'].append({
                            'number': item.get('number', ''),
                            'description': description,
                            'date': json_file.stem
                        })

                    if 'INTRODUCED BY' in description and len(examples['INTRODUCED BY']) < 10:
                        examples['INTRODUCED BY'].append({
                            'number': item.get('number', ''),
                            'description': description,
                            'date': json_file.stem
                        })

                    # Stop if we have enough examples
                    if all(len(ex) >= 10 for ex in examples.values()):
                        break

        except Exception as e:
            print(f"Error: {e}")
            continue

        if all(len(ex) >= 10 for ex in examples.values()):
            break

    # Print examples
    for pattern, ex_list in examples.items():
        print(f"\n{'='*80}")
        print(f"PATTERN: {pattern}")
        print(f"{'='*80}\n")

        for ex in ex_list[:5]:  # Show 5 examples per pattern
            print(f"{ex['number']} ({ex['date']}):")
            print(f"{ex['description'][:500]}")
            print()

if __name__ == "__main__":
    show_examples()
