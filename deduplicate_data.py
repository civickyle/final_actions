#!/usr/bin/env python3
"""
Deduplicate legislation data.
For exact duplicates (same in all fields except 'id'), keep only the one with the lowest ID.
"""

import json
from pathlib import Path
from collections import defaultdict
import hashlib
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('deduplication.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def create_fingerprint(item):
    """
    Create a fingerprint of an item excluding the 'id' field.
    Returns a hash of all other fields.
    """
    item_without_id = {k: v for k, v in item.items() if k != 'id'}
    fingerprint_str = json.dumps(item_without_id, sort_keys=True)
    return hashlib.md5(fingerprint_str.encode()).hexdigest()

def deduplicate_items(items):
    """
    Deduplicate a list of items, keeping the one with the lowest ID.

    Args:
        items: List of legislation items

    Returns:
        tuple: (deduplicated_list, number_of_duplicates_removed)
    """
    # Group by fingerprint
    fingerprint_groups = defaultdict(list)

    for item in items:
        fp = create_fingerprint(item)
        fingerprint_groups[fp].append(item)

    # For each group, keep only the one with the lowest ID
    deduplicated = []
    duplicates_removed = 0

    for fp, group in fingerprint_groups.items():
        if len(group) > 1:
            # Sort by ID and keep the first (lowest)
            group_sorted = sorted(group, key=lambda x: x.get('id', float('inf')))
            kept_item = group_sorted[0]
            deduplicated.append(kept_item)
            duplicates_removed += len(group) - 1

            # Log the duplicate IDs that were removed
            removed_ids = [item['id'] for item in group_sorted[1:]]
            logger.debug(f"Kept ID {kept_item['id']}, removed IDs: {removed_ids} for {kept_item.get('number', 'unknown')}")
        else:
            # No duplicates, keep the single item
            deduplicated.append(group[0])

    return deduplicated, duplicates_removed

def deduplicate_all_files(dry_run=False):
    """
    Deduplicate all JSON files in the meeting_dates directory.

    Args:
        dry_run: If True, don't actually modify files, just report what would be done
    """
    meeting_dates_dir = Path("meeting_dates")

    if not meeting_dates_dir.exists():
        logger.error("meeting_dates directory not found")
        return

    total_files = 0
    total_items_before = 0
    total_items_after = 0
    total_duplicates_removed = 0
    files_with_duplicates = 0

    # Process all JSON files
    json_files = list(meeting_dates_dir.rglob("*.json"))
    logger.info(f"Found {len(json_files)} JSON files to process")

    for json_file in json_files:
        total_files += 1

        try:
            # Read the file
            with open(json_file, 'r') as f:
                content = json.load(f)

            original_data = content.get('data', [])
            items_before = len(original_data)
            total_items_before += items_before

            # Deduplicate
            deduplicated_data, duplicates_removed = deduplicate_items(original_data)
            items_after = len(deduplicated_data)
            total_items_after += items_after

            if duplicates_removed > 0:
                files_with_duplicates += 1
                total_duplicates_removed += duplicates_removed
                logger.info(f"{json_file}: {items_before} -> {items_after} items ({duplicates_removed} duplicates removed)")

                if not dry_run:
                    # Update the data
                    content['data'] = deduplicated_data

                    # Write back to file
                    with open(json_file, 'w') as f:
                        json.dump(content, f, indent=2)

        except Exception as e:
            logger.error(f"Error processing {json_file}: {e}")
            continue

        # Progress update
        if total_files % 100 == 0:
            logger.info(f"Progress: {total_files}/{len(json_files)} files processed")

    # Final summary
    logger.info("\n" + "="*60)
    logger.info("Deduplication Complete")
    logger.info("="*60)
    logger.info(f"Files processed: {total_files}")
    logger.info(f"Files with duplicates: {files_with_duplicates}")
    logger.info(f"Total items before: {total_items_before}")
    logger.info(f"Total items after: {total_items_after}")
    logger.info(f"Total duplicates removed: {total_duplicates_removed}")
    logger.info(f"Reduction: {(total_duplicates_removed/total_items_before*100):.1f}%")

    if dry_run:
        logger.info("\nDRY RUN - No files were modified")
    else:
        logger.info("\nFiles have been updated with deduplicated data")

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Deduplicate legislation data')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without modifying files'
    )

    args = parser.parse_args()

    if args.dry_run:
        logger.info("Starting deduplication in DRY RUN mode...")
    else:
        logger.info("Starting deduplication...")
        logger.warning("This will modify your JSON files. Press Ctrl+C within 3 seconds to cancel.")
        import time
        time.sleep(3)

    deduplicate_all_files(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
