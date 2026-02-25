#!/usr/bin/env python3
"""
Deduplicate legislation data - Phase 2: Substring handling.
For items with the same number where one description is a substring of another,
keep the longer version.
"""

import json
from pathlib import Path
from collections import defaultdict
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('deduplication_substrings.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def is_substring_match(item1, item2):
    """
    Check if two items are substring matches.
    Returns: (is_match, longer_item, shorter_item) or (False, None, None)
    """
    # Must have same number
    if item1.get('number') != item2.get('number'):
        return False, None, None

    # Check if all fields except ID and description are identical
    keys_to_check = set(item1.keys()) | set(item2.keys())
    keys_to_check.discard('id')
    keys_to_check.discard('description')

    for key in keys_to_check:
        if item1.get(key) != item2.get(key):
            return False, None, None

    # Now check if descriptions are substring matches
    desc1 = item1.get('description', '')
    desc2 = item2.get('description', '')

    if not desc1 or not desc2:
        return False, None, None

    # Check if one is substring of the other
    if desc1 in desc2:
        # desc1 is substring of desc2
        return True, item2, item1
    elif desc2 in desc1:
        # desc2 is substring of desc1
        return True, item1, item2

    return False, None, None

def deduplicate_by_substring(items):
    """
    Deduplicate items where one description is a substring of another.
    Keep the longer version.

    Args:
        items: List of legislation items

    Returns:
        tuple: (deduplicated_list, number_of_duplicates_removed, details)
    """
    # Group by legislation number
    by_number = defaultdict(list)
    for item in items:
        number = item.get('number')
        if number:
            by_number[number].append(item)

    # Track which items to keep
    items_to_keep = []
    items_to_remove = set()  # Track by ID
    substring_removals = []

    for number, number_items in by_number.items():
        if len(number_items) == 1:
            # No duplicates for this number
            items_to_keep.extend(number_items)
            continue

        # Check all pairs for substring matches
        kept_items = list(number_items)
        removed_in_group = []

        i = 0
        while i < len(kept_items):
            j = i + 1
            while j < len(kept_items):
                item1 = kept_items[i]
                item2 = kept_items[j]

                is_match, longer, shorter = is_substring_match(item1, item2)

                if is_match:
                    # Remove the shorter one
                    shorter_id = shorter.get('id')
                    longer_id = longer.get('id')

                    if shorter_id not in items_to_remove:
                        items_to_remove.add(shorter_id)
                        removed_in_group.append({
                            'number': number,
                            'kept_id': longer_id,
                            'removed_id': shorter_id,
                            'kept_desc_len': len(longer.get('description', '')),
                            'removed_desc_len': len(shorter.get('description', ''))
                        })

                        # Remove shorter from kept_items
                        if item1.get('id') == shorter_id:
                            kept_items.pop(i)
                            j = i + 1  # Reset j since we removed item at i
                        else:
                            kept_items.pop(j)
                            # Don't increment j, check same position again
                        continue

                j += 1
            i += 1

        items_to_keep.extend(kept_items)
        substring_removals.extend(removed_in_group)

    # Log details
    for removal in substring_removals:
        logger.debug(
            f"Legislation {removal['number']}: "
            f"Kept ID {removal['kept_id']} ({removal['kept_desc_len']} chars), "
            f"Removed ID {removal['removed_id']} ({removal['removed_desc_len']} chars)"
        )

    return items_to_keep, len(items_to_remove), substring_removals

def deduplicate_all_files(dry_run=False):
    """
    Deduplicate all JSON files by removing substring duplicates.

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
    all_removals = []

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

            # Deduplicate by substring
            deduplicated_data, duplicates_removed, removals = deduplicate_by_substring(original_data)
            items_after = len(deduplicated_data)
            total_items_after += items_after

            if duplicates_removed > 0:
                files_with_duplicates += 1
                total_duplicates_removed += duplicates_removed
                all_removals.extend(removals)

                logger.info(f"{json_file}: {items_before} -> {items_after} items ({duplicates_removed} substring duplicates removed)")

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
    logger.info("Phase 2 Deduplication Complete (substring handling)")
    logger.info("="*60)
    logger.info(f"Files processed: {total_files}")
    logger.info(f"Files with substring duplicates: {files_with_duplicates}")
    logger.info(f"Total items before: {total_items_before}")
    logger.info(f"Total items after: {total_items_after}")
    logger.info(f"Total substring duplicates removed: {total_duplicates_removed}")
    logger.info(f"Reduction: {(total_duplicates_removed/total_items_before*100):.1f}%")

    # Show some examples
    if all_removals and len(all_removals) > 0:
        logger.info("\nSample removals (first 5):")
        for i, removal in enumerate(all_removals[:5], 1):
            logger.info(f"  {i}. Legislation {removal['number']}")
            logger.info(f"     Kept ID {removal['kept_id']} ({removal['kept_desc_len']} chars)")
            logger.info(f"     Removed ID {removal['removed_id']} ({removal['removed_desc_len']} chars)")
            logger.info(f"     Saved: {removal['kept_desc_len'] - removal['removed_desc_len']} extra characters")

    if dry_run:
        logger.info("\nDRY RUN - No files were modified")
    else:
        logger.info("\nFiles have been updated with substring duplicates removed")

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Deduplicate legislation data - Phase 2: Keep longer versions'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without modifying files'
    )

    args = parser.parse_args()

    if args.dry_run:
        logger.info("Starting Phase 2 deduplication in DRY RUN mode...")
        logger.info("This will identify substring duplicates and keep the longer version")
    else:
        logger.info("Starting Phase 2 deduplication (substring handling)...")
        logger.info("This will:")
        logger.info("  1. Find items with same number where one description is substring of another")
        logger.info("  2. Keep the longer version (more complete information)")
        logger.info("  3. Remove the shorter version")
        logger.warning("\nThis will modify your JSON files. Press Ctrl+C within 3 seconds to cancel.")
        import time
        time.sleep(3)

    deduplicate_all_files(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
