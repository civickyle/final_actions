#!/usr/bin/env python3
"""
Remove invalid sponsor patterns from legislation data.
Removes sponsors containing "AS AMENDED" or "AS SUBSTITUTED" which are description text, not actual sponsors.
"""

import json
from pathlib import Path
from collections import defaultdict

# Configuration
MEETING_DATES_DIR = Path('meeting_dates')

def is_invalid_sponsor(sponsor_name):
    """Check if a sponsor name contains invalid patterns."""
    if not sponsor_name:
        return False

    lower_name = sponsor_name.lower()
    # Check for "as substituted" or "as amended" patterns (case insensitive)
    # These are description patterns, not actual sponsor names
    # Also check for variations like "(as substituted", "#2 by", etc.
    invalid_patterns = [
        ' as substitut',  # Catches "as Substituted", "as Substituted and Amended", etc.
        ' as amend',      # Catches "as Amended", "as Amended by", etc.
        '(as substitut',  # Catches "(as substituted by"
        '(as amend',      # Catches "(as amended by"
    ]
    return any(pattern in lower_name for pattern in invalid_patterns)

def clean_files(dry_run=True):
    """
    Clean all JSON files by removing invalid sponsors.

    Args:
        dry_run: If True, only report what would be changed without modifying files

    Returns:
        dict with statistics and changes
    """
    stats = {
        'files_checked': 0,
        'items_checked': 0,
        'sponsors_removed': 0,
        'files_modified': 0,
        'items_modified': 0,
        'removed_sponsors': defaultdict(int),
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

            current_sponsors = item.get('sponsors', [])
            if not current_sponsors:
                continue

            # Filter out invalid sponsors
            valid_sponsors = [s for s in current_sponsors if not is_invalid_sponsor(s)]
            invalid_sponsors = [s for s in current_sponsors if is_invalid_sponsor(s)]

            if invalid_sponsors:
                stats['items_modified'] += 1
                stats['sponsors_removed'] += len(invalid_sponsors)

                for invalid in invalid_sponsors:
                    stats['removed_sponsors'][invalid] += 1

                change = {
                    'file': str(json_file),
                    'item_id': item.get('id'),
                    'number': item.get('number'),
                    'removed': invalid_sponsors,
                    'before': current_sponsors.copy(),
                    'after': valid_sponsors,
                    'description_preview': item.get('description', '')[:100]
                }
                stats['changes'].append(change)

                # Apply change if not dry run
                if not dry_run:
                    item['sponsors'] = valid_sponsors
                    file_modified = True

        # Save file if modified
        if file_modified:
            stats['files_modified'] += 1
            with open(json_file, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    return stats

def print_report(stats):
    """Print a human-readable report of the analysis."""
    print("\n" + "="*80)
    print("INVALID SPONSOR REMOVAL REPORT")
    print("="*80)

    print(f"\nFiles checked: {stats['files_checked']:,}")
    print(f"Items checked: {stats['items_checked']:,}")
    print(f"Items modified: {stats['items_modified']:,}")
    print(f"Sponsors removed: {stats['sponsors_removed']:,}")
    print(f"Files to be modified: {stats['files_modified']:,}")

    if stats['removed_sponsors']:
        print("\n" + "-"*80)
        print("INVALID SPONSORS TO BE REMOVED:")
        print("-"*80)
        for sponsor, count in sorted(stats['removed_sponsors'].items(),
                                     key=lambda x: x[1], reverse=True):
            print(f"  [{count:,}x] {sponsor}")

    # Show sample changes
    if stats['changes']:
        print("\n" + "-"*80)
        print("SAMPLE CHANGES (first 10):")
        print("-"*80)
        for change in stats['changes'][:10]:
            print(f"\nFile: {change['file']}")
            print(f"  Number: {change['number']}")
            print(f"  Removed sponsors: {change['removed']}")
            print(f"  Before: {change['before']}")
            print(f"  After: {change['after']}")
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

    stats = clean_files(dry_run=dry_run)
    print_report(stats)

    if dry_run:
        print("\n💡 To apply these changes, run: python clean_invalid_sponsors.py --apply")
    else:
        print("\n✅ Changes applied successfully!")
        print("Invalid sponsors have been removed from the data files.")
