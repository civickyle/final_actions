#!/usr/bin/env python3
"""
Merge meeting_doc IDs into meeting_dates JSON files.
Matches FormalNumber from meeting_doc files to number in meeting_dates files.
Adds meetingDocId field to enable detail page links.
"""

import json
from pathlib import Path
from collections import defaultdict

# Configuration
MEETING_DOCS_DIR = Path('api_downloads/meeting_docs')
MEETING_DATES_DIR = Path('meeting_dates')

def build_meeting_doc_lookup():
    """
    Build a lookup dictionary from FormalNumber to meeting_doc ID.

    Returns:
        dict: {FormalNumber: meeting_doc_id}
    """
    lookup = {}
    stats = {
        'files_scanned': 0,
        'valid_entries': 0,
        'missing_formal_number': 0,
        'duplicate_formal_numbers': defaultdict(list)
    }

    print("Building meeting_doc lookup from API downloads...")

    for json_file in sorted(MEETING_DOCS_DIR.glob('meeting_doc_*.json')):
        stats['files_scanned'] += 1

        # Extract ID from filename (e.g., meeting_doc_00123.json -> 123)
        filename = json_file.stem
        doc_id_str = filename.replace('meeting_doc_', '')
        doc_id = int(doc_id_str)  # Convert to int to strip leading zeros

        try:
            with open(json_file, 'r') as f:
                data = json.load(f)

            # Only use FormalNumber field (e.g., "14-R-4044")
            formal_number = data.get('FormalNumber')

            if formal_number:
                # Check for duplicates
                if formal_number in lookup:
                    stats['duplicate_formal_numbers'][formal_number].append(doc_id)
                else:
                    lookup[formal_number] = doc_id
                    stats['valid_entries'] += 1
            else:
                stats['missing_formal_number'] += 1

        except Exception as e:
            print(f"Error reading {json_file}: {e}")
            continue

    print(f"  Files scanned: {stats['files_scanned']:,}")
    print(f"  Valid entries: {stats['valid_entries']:,}")
    print(f"  Missing FormalNumber: {stats['missing_formal_number']:,}")

    if stats['duplicate_formal_numbers']:
        print(f"  Duplicate FormalNumbers found: {len(stats['duplicate_formal_numbers'])}")
        print("  (Using first occurrence for each duplicate)")

    return lookup, stats

def merge_meeting_doc_ids(lookup, dry_run=True):
    """
    Merge meeting_doc IDs into meeting_dates JSON files.

    Args:
        lookup: Dictionary mapping FormalNumber to meeting_doc ID
        dry_run: If True, only report what would be changed

    Returns:
        dict with merge statistics
    """
    stats = {
        'files_checked': 0,
        'files_modified': 0,
        'items_checked': 0,
        'items_matched': 0,
        'items_updated': 0,
        'items_already_had_id': 0,
        'sample_matches': []
    }

    print("\nMerging meeting_doc IDs into meeting_dates files...")

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

                number = item.get('number', '')

                if number and number in lookup:
                    stats['items_matched'] += 1

                    meeting_doc_id = lookup[number]
                    current_id = item.get('meetingDocId')

                    if current_id == meeting_doc_id:
                        stats['items_already_had_id'] += 1
                    else:
                        # Store sample matches for reporting
                        if len(stats['sample_matches']) < 10:
                            stats['sample_matches'].append({
                                'file': str(json_file),
                                'number': number,
                                'meeting_doc_id': meeting_doc_id,
                                'description': item.get('description', '')[:80]
                            })

                        stats['items_updated'] += 1

                        # Apply change if not dry run
                        if not dry_run:
                            item['meetingDocId'] = meeting_doc_id
                            file_modified = True

            # Save file if modified
            if file_modified:
                stats['files_modified'] += 1
                with open(json_file, 'w') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            continue

    return stats

def print_merge_report(lookup_stats, merge_stats):
    """Print a summary report of the merge operation."""
    print("\n" + "="*80)
    print("MEETING DOC MERGE REPORT")
    print("="*80)

    print("\nLOOKUP BUILD:")
    print(f"  Meeting doc files scanned: {lookup_stats['files_scanned']:,}")
    print(f"  Valid FormalNumber entries: {lookup_stats['valid_entries']:,}")
    print(f"  Missing FormalNumber: {lookup_stats['missing_formal_number']:,}")

    print("\nMERGE RESULTS:")
    print(f"  Meeting date files checked: {merge_stats['files_checked']:,}")
    print(f"  Items checked: {merge_stats['items_checked']:,}")
    print(f"  Items matched to meeting_docs: {merge_stats['items_matched']:,}")
    print(f"  Items to be updated: {merge_stats['items_updated']:,}")
    print(f"  Items already had correct ID: {merge_stats['items_already_had_id']:,}")
    print(f"  Files to be modified: {merge_stats['files_modified']:,}")

    # Calculate match rate
    if merge_stats['items_checked'] > 0:
        match_rate = (merge_stats['items_matched'] / merge_stats['items_checked']) * 100
        print(f"\n  Match rate: {match_rate:.1f}%")

    # Show sample matches
    if merge_stats['sample_matches']:
        print("\n" + "-"*80)
        print("SAMPLE MATCHES (first 10):")
        print("-"*80)
        for match in merge_stats['sample_matches']:
            print(f"\nFile: {match['file']}")
            print(f"  Number: {match['number']}")
            print(f"  Meeting Doc ID: {match['meeting_doc_id']}")
            print(f"  Description: {match['description']}...")

    print("\n" + "="*80)

if __name__ == '__main__':
    import sys

    dry_run = '--apply' not in sys.argv
    skip_confirm = '--yes' in sys.argv

    # Check if meeting_docs directory exists
    if not MEETING_DOCS_DIR.exists():
        print(f"\n❌ Error: {MEETING_DOCS_DIR} directory not found!")
        print("Make sure the download_meeting_docs.py script has completed.")
        sys.exit(1)

    # Check if there are any meeting_doc files
    doc_files = list(MEETING_DOCS_DIR.glob('meeting_doc_*.json'))
    if not doc_files:
        print(f"\n❌ Error: No meeting_doc_*.json files found in {MEETING_DOCS_DIR}")
        print("Make sure the download_meeting_docs.py script has completed.")
        sys.exit(1)

    print(f"\nFound {len(doc_files):,} meeting_doc files")

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

    # Build lookup
    lookup, lookup_stats = build_meeting_doc_lookup()

    if not lookup:
        print("\n❌ Error: No valid FormalNumber entries found!")
        sys.exit(1)

    # Merge into meeting_dates
    merge_stats = merge_meeting_doc_ids(lookup, dry_run=dry_run)

    # Print report
    print_merge_report(lookup_stats, merge_stats)

    if dry_run:
        print("\n💡 To apply these changes, run: python merge_meeting_docs.py --apply")
    else:
        print("\n✅ Changes applied successfully!")
        print("Meeting doc IDs have been added to meeting_dates files.")
        print("You can now update the web templates to show detail links.")
