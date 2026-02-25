#!/usr/bin/env python3
"""
Move charter termination text from description to finalAction.

For items where description ends with charter termination text variants,
move that text to the finalAction field.
"""

import json
from pathlib import Path
import shutil

# Configuration
MEETING_DATES_DIR = Path('meeting_dates')
TERMINATION_TEXTS = [
    "AUTOMATICALLY TERMINATED AND FILED BY CLERK PER CHARTER SECTION 2-407 WITHOUT OBJECTION",
    "AUTOMATICALLY TERMINATED AND FILED BY CLERK PER CHARTER SECTION 2-407",
    "AUTOMATICALLY TERMINATED AND FILED PER CHARTER SECTION 2-407 WITHOUT OBJECTION"
]

def move_charter_termination(dry_run=True):
    """
    Move charter termination text from description to finalAction.

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
        'sample_changes': []
    }

    print("\nScanning for charter termination text in descriptions...")

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

                description = item.get('description', '')

                # Check if description ends with any termination text variant
                matched_text = None
                for termination_text in TERMINATION_TEXTS:
                    if description.endswith(termination_text):
                        matched_text = termination_text
                        break

                if matched_text:
                    # Store sample for reporting
                    if len(stats['sample_changes']) < 10:
                        stats['sample_changes'].append({
                            'file': str(json_file),
                            'number': item.get('number', 'N/A'),
                            'old_description': description[:100] + '...' if len(description) > 100 else description,
                            'old_final_action': item.get('finalAction', '(empty)'),
                            'termination_text': matched_text
                        })

                    stats['items_updated'] += 1

                    if not dry_run:
                        # Remove termination text from description
                        new_description = description[:-len(matched_text)].strip()
                        item['description'] = new_description

                        # Set finalAction to termination text
                        item['finalAction'] = matched_text

                        file_modified = True

            # Save file if modified
            if file_modified:
                stats['files_modified'] += 1

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
    print("CHARTER TERMINATION MOVE REPORT")
    print("="*80)

    print(f"\nFILES CHECKED: {stats['files_checked']:,}")
    print(f"ITEMS CHECKED: {stats['items_checked']:,}")
    print(f"ITEMS TO UPDATE: {stats['items_updated']:,}")
    print(f"FILES TO MODIFY: {stats['files_modified']:,}")

    # Show sample changes
    if stats['sample_changes']:
        print("\n" + "-"*80)
        print("SAMPLE CHANGES (first 10):")
        print("-"*80)
        for change in stats['sample_changes']:
            print(f"\nFile: {change['file']}")
            print(f"  Number: {change['number']}")
            print(f"  Old Description: {change['old_description']}")
            print(f"  Old Final Action: {change['old_final_action']}")
            print(f"  New Final Action: {change['termination_text']}")

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

    stats = move_charter_termination(dry_run=dry_run)
    print_report(stats)

    if dry_run:
        print("\n💡 To apply these changes, run: python move_charter_termination.py --apply")
    else:
        print("\n✅ Changes applied successfully!")
        print("Charter termination text has been moved from descriptions to finalAction fields.")
