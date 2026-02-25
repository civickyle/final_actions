#!/usr/bin/env python3
"""
Identify and assign committee sponsors to legislation based on description patterns.
Looks for patterns like "A RESOLUTION BY X COMMITTEE" or "AN ORDINANCE BY X COMMITTEE"
"""

import json
import re
from pathlib import Path
from collections import defaultdict

# Load committees
COMMITTEES_FILE = Path('committees.json')
MEETING_DATES_DIR = Path('meeting_dates')

def load_committees():
    """Load committee names from committees.json"""
    with open(COMMITTEES_FILE, 'r') as f:
        data = json.load(f)
    return [c['name'] for c in data['committees']]

def extract_committee_from_description(description, known_committees):
    """
    Extract committee name from description patterns like:
    - "A RESOLUTION BY X COMMITTEE"
    - "AN ORDINANCE BY X COMMITTEE"
    - "A RESOLUTION BY THE X COMMITTEE"
    """
    if not description:
        return None

    # Pattern: starts with "A RESOLUTION BY" or "AN ORDINANCE BY" followed by committee name
    # Case insensitive, capture everything up to semicolon, period, or "THAT"
    patterns = [
        r'^AN?\s+(?:RESOLUTION|ORDINANCE)\s+BY\s+(?:THE\s+)?([^;.]+?COMMITTEE)',
    ]

    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            committee_text = match.group(1).strip()

            # Clean up common variations
            committee_text = re.sub(r'\s+', ' ', committee_text)  # normalize whitespace

            # Check if this matches any known committee (case-insensitive)
            for known_committee in known_committees:
                if committee_text.upper() == known_committee.upper():
                    return known_committee

            # Return the extracted text even if not in known committees
            # (for review purposes)
            return committee_text

    return None

def analyze_files(dry_run=True):
    """
    Analyze all JSON files and identify committee papers.

    Args:
        dry_run: If True, only report what would be changed without modifying files

    Returns:
        dict with statistics and changes
    """
    committees = load_committees()

    stats = {
        'files_checked': 0,
        'items_checked': 0,
        'committees_added': 0,
        'files_modified': 0,
        'unknown_committees': defaultdict(int),
        'known_committees_added': defaultdict(int),
        'changes': []
    }

    # Iterate through all JSON files
    for json_file in sorted(MEETING_DATES_DIR.rglob('*.json')):
        if '.bak' in json_file.name:
            continue

        stats['files_checked'] += 1

        with open(json_file, 'r') as f:
            data = json.load(f)

        file_modified = False

        for item in data.get('data', []):
            stats['items_checked'] += 1

            description = item.get('description', '')
            current_sponsors = item.get('sponsors', [])

            # Extract committee from description
            committee = extract_committee_from_description(description, committees)

            if committee:
                # Check if committee is already in sponsors
                if committee not in current_sponsors:
                    stats['committees_added'] += 1

                    if committee in committees:
                        stats['known_committees_added'][committee] += 1
                    else:
                        stats['unknown_committees'][committee] += 1

                    change = {
                        'file': str(json_file),
                        'item_id': item.get('id'),
                        'number': item.get('number'),
                        'committee': committee,
                        'current_sponsors': current_sponsors.copy(),
                        'new_sponsors': current_sponsors + [committee],
                        'description_preview': description[:150]
                    }
                    stats['changes'].append(change)

                    # Apply change if not dry run
                    if not dry_run:
                        item['sponsors'] = current_sponsors + [committee]
                        item['sponsorConfidence'] = 'auto-committee'
                        file_modified = True

        # Save file if modified
        if file_modified:
            stats['files_modified'] += 1
            with open(json_file, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    return stats

def print_report(stats):
    """Print a human-readable report of the analysis"""
    print("\n" + "="*80)
    print("COMMITTEE PAPER IDENTIFICATION REPORT")
    print("="*80)

    print(f"\nFiles checked: {stats['files_checked']:,}")
    print(f"Items checked: {stats['items_checked']:,}")
    print(f"Committees to be added: {stats['committees_added']:,}")
    print(f"Files to be modified: {stats['files_modified']:,}")

    if stats['known_committees_added']:
        print("\n" + "-"*80)
        print("KNOWN COMMITTEES TO BE ADDED:")
        print("-"*80)
        for committee, count in sorted(stats['known_committees_added'].items(),
                                       key=lambda x: x[1], reverse=True):
            print(f"  {committee}: {count:,} items")

    if stats['unknown_committees']:
        print("\n" + "-"*80)
        print("UNKNOWN COMMITTEES FOUND (not in committees.json):")
        print("-"*80)
        for committee, count in sorted(stats['unknown_committees'].items(),
                                       key=lambda x: x[1], reverse=True):
            print(f"  {committee}: {count:,} items")
        print("\nNote: Add these to committees.json if they are valid committees")

    # Show sample changes
    if stats['changes']:
        print("\n" + "-"*80)
        print("SAMPLE CHANGES (first 10):")
        print("-"*80)
        for change in stats['changes'][:10]:
            print(f"\nFile: {change['file']}")
            print(f"  Number: {change['number']}")
            print(f"  Committee found: {change['committee']}")
            print(f"  Current sponsors: {change['current_sponsors']}")
            print(f"  New sponsors: {change['new_sponsors']}")
            print(f"  Description: {change['description_preview']}...")

    print("\n" + "="*80)

if __name__ == '__main__':
    import sys

    dry_run = '--apply' not in sys.argv

    if dry_run:
        print("\n🔍 DRY RUN MODE - No files will be modified")
        print("Run with --apply to actually update the files\n")
    else:
        print("\n⚠️  APPLYING CHANGES - Files will be modified!")
        print("Make sure you have backups!\n")
        response = input("Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            sys.exit(0)

    stats = analyze_files(dry_run=dry_run)
    print_report(stats)

    if dry_run:
        print("\n💡 To apply these changes, run: python identify_committee_papers.py --apply")
    else:
        print("\n✅ Changes applied successfully!")
        print("Review the changes and restart your Flask app to see updates.")
