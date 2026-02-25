#!/usr/bin/env python3
"""
Generate councilmembers.json based on the dates councilmembers sponsored legislation.

This creates a draft that should be manually reviewed and adjusted for accuracy.
"""

from pathlib import Path
import json
from collections import defaultdict

MEETING_DATES_DIR = Path("meeting_dates")
OUTPUT_FILE = Path("councilmembers.json")

def analyze_sponsor_dates():
    """Analyze all legislation to find date ranges for each sponsor."""
    sponsor_dates = defaultdict(lambda: {'first': None, 'last': None, 'count': 0})

    print("Analyzing legislation data...")

    for json_file in sorted(MEETING_DATES_DIR.rglob("*.json")):
        date_str = json_file.stem  # e.g., "1984-01-03"

        try:
            with open(json_file, 'r') as f:
                content = json.load(f)
                data = content.get('data', [])

                for item in data:
                    sponsors = item.get('sponsors', [])
                    for sponsor in sponsors:
                        if sponsor:  # Skip empty sponsors
                            sponsor_dates[sponsor]['count'] += 1

                            # Update first date
                            if sponsor_dates[sponsor]['first'] is None or date_str < sponsor_dates[sponsor]['first']:
                                sponsor_dates[sponsor]['first'] = date_str

                            # Update last date
                            if sponsor_dates[sponsor]['last'] is None or date_str > sponsor_dates[sponsor]['last']:
                                sponsor_dates[sponsor]['last'] = date_str

        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            continue

    return sponsor_dates

def generate_councilmembers_json(sponsor_dates):
    """Generate the councilmembers.json structure."""
    councilmembers = []

    for name in sorted(sponsor_dates.keys()):
        dates = sponsor_dates[name]

        councilmembers.append({
            'name': name,
            'start': dates['first'],
            'end': dates['last'],
            '_count': dates['count'],
            '_note': 'Auto-generated - verify dates manually'
        })

    output = {
        '_note': 'This file was auto-generated based on legislation sponsorship dates. These dates represent when councilmembers SPONSORED legislation, not necessarily their full term in office. Please review and adjust manually for accuracy.',
        '_usage': 'Remove _count and _note fields from individual entries before using in production. Set end to null for current councilmembers.',
        'councilmembers': councilmembers
    }

    return output

def main():
    print("Generating councilmembers.json from legislation data...")
    print()

    # Analyze the data
    sponsor_dates = analyze_sponsor_dates()

    print(f"\nFound {len(sponsor_dates)} unique sponsors")

    # Generate JSON structure
    output = generate_councilmembers_json(sponsor_dates)

    # Write to file
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Generated {OUTPUT_FILE}")
    print()
    print("IMPORTANT: This is a DRAFT based on legislation dates.")
    print("- The 'start' date is the EARLIEST legislation sponsored")
    print("- The 'end' date is the LATEST legislation sponsored")
    print("- These may not match actual term start/end dates")
    print("- Some councilmembers may have served multiple non-consecutive terms")
    print("- Current councilmembers should have 'end' set to null")
    print()
    print("Please review and manually adjust the dates before using in production.")

    # Show some statistics
    print("\nTop 10 sponsors by legislation count:")
    sorted_sponsors = sorted(sponsor_dates.items(), key=lambda x: x[1]['count'], reverse=True)
    for i, (name, data) in enumerate(sorted_sponsors[:10], 1):
        print(f"{i:2}. {name:40} {data['count']:4} items  ({data['first']} to {data['last']})")

if __name__ == "__main__":
    main()
