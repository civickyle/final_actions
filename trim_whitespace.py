#!/usr/bin/env python3
"""
Trim whitespace from description and finalAction fields in meeting_dates data.
"""

import json
from pathlib import Path
import shutil

# Configuration
MEETING_DATES_DIR = Path('meeting_dates')

def trim_whitespace(dry_run=True):
    """
    Trim leading/trailing whitespace from description and finalAction fields.

    Args:
        dry_run: If True, only report what would be changed

    Returns:
        dict with statistics
    """
    stats = {
        'files_checked': 0,
        'files_modified': 0,
        'items_checked': 0,
        'items_updated': 0,
        'description_trimmed': 0,
        'finalaction_trimmed': 0,
        'sample_changes': []
    }

    print("\nTrimming whitespace from description and finalAction fields...")

    for json_file in sorted(MEETING_DATES_DIR.rglob('*.json')):
        if '.bak' in json_file.name:
            continue

        stats['files_checked'] += 1

        try:
            with open(json_file, 'r') as f:
                data = json.load(f)

            file_modified = False

            for item in data.get('data', []):
                stats['items_checked'] += 1

                item_modified = False

                # Trim description
                description = item.get('description', '')
                if description and description != description.strip():
                    # Store sample for reporting
                    if len(stats['sample_changes']) < 10:
                        stats['sample_changes'].append({
                            'file': str(json_file),
                            'number': item.get('number', 'N/A'),
                            'field': 'description',
                            'before': repr(description),
                            'after': repr(description.strip())
                        })

                    stats['description_trimmed'] += 1
                    item_modified = True

                    if not dry_run:
                        item['description'] = description.strip()

                # Trim finalAction
                final_action = item.get('finalAction', '')
                if final_action and final_action != final_action.strip():
                    # Store sample for reporting
                    if len(stats['sample_changes']) < 10:
                        stats['sample_changes'].append({
                            'file': str(json_file),
                            'number': item.get('number', 'N/A'),
                            'field': 'finalAction',
                            'before': repr(final_action),
                            'after': repr(final_action.strip())
                        })

                    stats['finalaction_trimmed'] += 1
                    item_modified = True

                    if not dry_run:
                        item['finalAction'] = final_action.strip()

                if item_modified:
                    stats['items_updated'] += 1
                    file_modified = True

            # Save file if modified
            if file_modified:
                stats['files_modified'] += 1

                if not dry_run:
                    # Create backup
                    backup_file = json_file.with_suffix('.json.bak')
                    shutil.copy2(json_file, backup_file)

                    # Save updated file
                    with open(json_file, 'w') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            continue

    return stats

def print_report(stats):
    """Print a summary report of the operation."""
    print("\n" + "="*80)
    print("WHITESPACE TRIMMING REPORT")
    print("="*80)

    print(f"\nFILES CHECKED: {stats['files_checked']:,}")
    print(f"ITEMS CHECKED: {stats['items_checked']:,}")
    print(f"\nDESCRIPTIONS TO TRIM: {stats['description_trimmed']:,}")
    print(f"FINAL ACTIONS TO TRIM: {stats['finalaction_trimmed']:,}")
    print(f"\nTOTAL ITEMS TO UPDATE: {stats['items_updated']:,}")
    print(f"FILES TO MODIFY: {stats['files_modified']:,}")

    # Show sample changes
    if stats['sample_changes']:
        print("\n" + "-"*80)
        print("SAMPLE CHANGES (first 10):")
        print("-"*80)
        for change in stats['sample_changes']:
            print(f"\nFile: {change['file']}")
            print(f"  Number: {change['number']}")
            print(f"  Field: {change['field']}")
            print(f"  Before: {change['before']}")
            print(f"  After: {change['after']}")

    print("\n" + "="*80)

if __name__ == '__main__':
    import sys

    dry_run = '--apply' not in sys.argv
    skip_confirm = '--yes' in sys.argv

    if dry_run:
        print("\n🔍 DRY RUN MODE - No files will be modified")
        print("Run with --apply to actually update the files\n")
    else:
        print("\n⚠️  APPLYING CHANGES - Files will be modified!")
        print("Make sure you have backups!\n")
        if not skip_confirm:
            response = input("Continue? (yes/no): ")
            if response.lower() != 'yes':
                print("Aborted.")
                sys.exit(0)

    stats = trim_whitespace(dry_run=dry_run)
    print_report(stats)

    if dry_run:
        print("\n💡 To apply these changes, run: python trim_whitespace.py --apply")
    else:
        print("\n✅ Changes applied successfully!")
        print("Whitespace has been trimmed from description and finalAction fields.")
