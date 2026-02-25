#!/usr/bin/env python3
"""
Identify and tag claim-related legislation in the data.
Claims typically have descriptions starting with "For" and contain the word "claim".
Tags them with claimType: "adversed" or "settlement" based on final action.
"""

import json
from pathlib import Path
from collections import defaultdict

# Configuration
MEETING_DATES_DIR = Path('meeting_dates')

def is_claim(description):
    """Check if a description appears to be a claim."""
    if not description:
        return False

    desc_lower = description.lower().strip()
    # Check if starts with "for" and contains "claim"
    return desc_lower.startswith('for') and 'claim' in desc_lower

def determine_claim_type(final_action):
    """Determine the claim type based on final action."""
    if not final_action or final_action == "MISSING":
        return None

    action_upper = final_action.upper()

    # Check for adversed
    if 'ADVERS' in action_upper:
        return 'adversed'

    # Check for settlement indicators
    if any(word in action_upper for word in ['SETTLEMENT', 'SETTLED', 'ADOPT', 'ACCEPT', 'CONFIRM']):
        return 'settlement'

    # Default to None if unclear
    return None

def tag_claims(dry_run=True):
    """
    Tag claim items across all JSON files.

    Args:
        dry_run: If True, only report what would be changed without modifying files

    Returns:
        dict with statistics and changes
    """
    stats = {
        'files_checked': 0,
        'items_checked': 0,
        'claims_found': 0,
        'files_modified': 0,
        'items_modified': 0,
        'claim_types': defaultdict(int),
        'claim_types_none': 0,
        'changes': []
    }

    # Iterate through all JSON files
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

                # Check if this is a claim
                if is_claim(description):
                    stats['claims_found'] += 1

                    # Determine claim type
                    final_action = item.get('finalAction', '')
                    claim_type = determine_claim_type(final_action)

                    # Track statistics
                    if claim_type:
                        stats['claim_types'][claim_type] += 1
                    else:
                        stats['claim_types_none'] += 1

                    # Check if we need to add or update the claimType
                    current_claim_type = item.get('claimType')
                    if current_claim_type != claim_type:
                        stats['items_modified'] += 1

                        change = {
                            'file': str(json_file),
                            'item_id': item.get('id'),
                            'number': item.get('number'),
                            'description_preview': description[:100],
                            'final_action': final_action,
                            'old_claim_type': current_claim_type,
                            'new_claim_type': claim_type
                        }
                        stats['changes'].append(change)

                        # Apply change if not dry run
                        if not dry_run:
                            if claim_type:
                                item['claimType'] = claim_type
                            elif 'claimType' in item:
                                # Remove claimType if it's now None
                                del item['claimType']
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

def print_report(stats):
    """Print a human-readable report of the analysis."""
    print("\n" + "="*80)
    print("CLAIMS TAGGING REPORT")
    print("="*80)

    print(f"\nFiles checked: {stats['files_checked']:,}")
    print(f"Items checked: {stats['items_checked']:,}")
    print(f"Claims found: {stats['claims_found']:,}")
    print(f"Items to be modified: {stats['items_modified']:,}")
    print(f"Files to be modified: {stats['files_modified']:,}")

    print("\n" + "-"*80)
    print("CLAIM TYPE DISTRIBUTION:")
    print("-"*80)
    for claim_type, count in sorted(stats['claim_types'].items()):
        print(f"  {claim_type}: {count:,}")
    if stats['claim_types_none'] > 0:
        print(f"  (no type - unclear from final action): {stats['claim_types_none']:,}")

    # Show sample changes
    if stats['changes']:
        print("\n" + "-"*80)
        print("SAMPLE CHANGES (first 20):")
        print("-"*80)
        for change in stats['changes'][:20]:
            print(f"\nFile: {change['file']}")
            print(f"  Number: {change['number']}")
            print(f"  Description: {change['description_preview']}...")
            print(f"  Final Action: {change['final_action']}")
            print(f"  Claim Type: {change['old_claim_type']} → {change['new_claim_type']}")

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

    stats = tag_claims(dry_run=dry_run)
    print_report(stats)

    if dry_run:
        print("\n💡 To apply these changes, run: python tag_claims.py --apply")
    else:
        print("\n✅ Changes applied successfully!")
        print("Claims have been tagged with claimType property.")
