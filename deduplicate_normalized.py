#!/usr/bin/env python3
"""
Deduplicate legislation data with normalization.
Phase 1: Normalize quotes and whitespace before deduplication.
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
        logging.FileHandler('deduplication_normalized.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def normalize_text(text):
    """
    Normalize text by:
    1. Converting Unicode quotes to ASCII
    2. Normalizing whitespace
    """
    if not isinstance(text, str):
        return text

    # Replace Unicode quote characters with ASCII equivalents
    quote_replacements = {
        '\u2018': "'",  # Left single quotation mark
        '\u2019': "'",  # Right single quotation mark
        '\u201a': "'",  # Single low-9 quotation mark
        '\u201b': "'",  # Single high-reversed-9 quotation mark
        '\u201c': '"',  # Left double quotation mark
        '\u201d': '"',  # Right double quotation mark
        '\u201e': '"',  # Double low-9 quotation mark
        '\u201f': '"',  # Double high-reversed-9 quotation mark
        '\u2013': '-',  # En dash
        '\u2014': '-',  # Em dash
        '\u2010': '-',  # Hyphen
        '\u2011': '-',  # Non-breaking hyphen
        '\u2012': '-',  # Figure dash
        '\u2015': '-',  # Horizontal bar
    }

    for old, new in quote_replacements.items():
        text = text.replace(old, new)

    # Normalize whitespace (collapse multiple spaces to single space)
    text = ' '.join(text.split())

    return text

def normalize_item(item):
    """
    Normalize all string fields in an item.
    Returns a new normalized item.
    """
    normalized = {}
    for key, value in item.items():
        if isinstance(value, str):
            normalized[key] = normalize_text(value)
        else:
            normalized[key] = value
    return normalized

def create_fingerprint(item):
    """
    Create a fingerprint of a normalized item excluding the 'id' field.
    """
    # Normalize the item first
    normalized = normalize_item(item)

    # Create fingerprint without ID
    item_without_id = {k: v for k, v in normalized.items() if k != 'id'}
    fingerprint_str = json.dumps(item_without_id, sort_keys=True)
    return hashlib.md5(fingerprint_str.encode()).hexdigest()

def deduplicate_items(items):
    """
    Deduplicate a list of items after normalization, keeping the one with the lowest ID.

    Args:
        items: List of legislation items

    Returns:
        tuple: (deduplicated_list, number_of_duplicates_removed, normalization_stats)
    """
    # Group by fingerprint
    fingerprint_groups = defaultdict(list)

    for item in items:
        fp = create_fingerprint(item)
        fingerprint_groups[fp].append(item)

    # For each group, keep only the one with the lowest ID
    deduplicated = []
    duplicates_removed = 0
    quote_normalized = 0
    whitespace_normalized = 0

    for fp, group in fingerprint_groups.items():
        if len(group) > 1:
            # Sort by ID and keep the first (lowest)
            group_sorted = sorted(group, key=lambda x: x.get('id', float('inf')))
            kept_item = group_sorted[0]

            # Check what kind of normalization made these match
            for removed_item in group_sorted[1:]:
                # Check if they differ in quotes
                has_quote_diff = False
                has_ws_diff = False

                for key in kept_item.keys():
                    if key == 'id':
                        continue
                    val1 = kept_item.get(key)
                    val2 = removed_item.get(key)

                    if isinstance(val1, str) and isinstance(val2, str) and val1 != val2:
                        # Check if normalization made them equal
                        if normalize_text(val1) == normalize_text(val2):
                            # They're equal after normalization
                            # Check what changed
                            if normalize_text(val1) != val1 or normalize_text(val2) != val2:
                                # Check if it's quotes
                                quote_chars = {'\u2018', '\u2019', '\u201c', '\u201d', '\u2013', '\u2014'}
                                if any(c in val1 or c in val2 for c in quote_chars):
                                    has_quote_diff = True
                                # Check if it's whitespace
                                if ' '.join(val1.split()) != val1 or ' '.join(val2.split()) != val2:
                                    has_ws_diff = True

                if has_quote_diff:
                    quote_normalized += 1
                if has_ws_diff:
                    whitespace_normalized += 1

            # Normalize the kept item's text fields
            normalized_item = normalize_item(kept_item)
            deduplicated.append(normalized_item)
            duplicates_removed += len(group) - 1

            # Log the duplicate IDs that were removed
            removed_ids = [item['id'] for item in group_sorted[1:]]
            logger.debug(f"Kept ID {kept_item['id']}, removed IDs: {removed_ids} for {kept_item.get('number', 'unknown')}")
        else:
            # No duplicates, but still normalize
            normalized_item = normalize_item(group[0])
            deduplicated.append(normalized_item)

    return deduplicated, duplicates_removed, {
        'quote_normalized': quote_normalized,
        'whitespace_normalized': whitespace_normalized
    }

def deduplicate_all_files(dry_run=False):
    """
    Deduplicate all JSON files with normalization.

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
    total_quote_normalized = 0
    total_ws_normalized = 0

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

            # Deduplicate with normalization
            deduplicated_data, duplicates_removed, norm_stats = deduplicate_items(original_data)
            items_after = len(deduplicated_data)
            total_items_after += items_after

            if duplicates_removed > 0:
                files_with_duplicates += 1
                total_duplicates_removed += duplicates_removed
                total_quote_normalized += norm_stats['quote_normalized']
                total_ws_normalized += norm_stats['whitespace_normalized']

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
    logger.info("Phase 1 Deduplication Complete (with normalization)")
    logger.info("="*60)
    logger.info(f"Files processed: {total_files}")
    logger.info(f"Files with duplicates: {files_with_duplicates}")
    logger.info(f"Total items before: {total_items_before}")
    logger.info(f"Total items after: {total_items_after}")
    logger.info(f"Total duplicates removed: {total_duplicates_removed}")
    logger.info(f"Reduction: {(total_duplicates_removed/total_items_before*100):.1f}%")
    logger.info("")
    logger.info("Normalization breakdown:")
    logger.info(f"  Quote normalization contributed to: {total_quote_normalized} removals")
    logger.info(f"  Whitespace normalization contributed to: {total_ws_normalized} removals")

    if dry_run:
        logger.info("\nDRY RUN - No files were modified")
    else:
        logger.info("\nFiles have been updated with normalized, deduplicated data")

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Deduplicate legislation data with normalization (Phase 1)')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without modifying files'
    )

    args = parser.parse_args()

    if args.dry_run:
        logger.info("Starting Phase 1 deduplication in DRY RUN mode...")
        logger.info("This will normalize quotes and whitespace before deduplication")
    else:
        logger.info("Starting Phase 1 deduplication with normalization...")
        logger.info("This will:")
        logger.info("  1. Normalize Unicode quotes to ASCII")
        logger.info("  2. Normalize whitespace")
        logger.info("  3. Deduplicate based on normalized values")
        logger.info("  4. Save normalized data back to files")
        logger.warning("\nThis will modify your JSON files. Press Ctrl+C within 3 seconds to cancel.")
        import time
        time.sleep(3)

    deduplicate_all_files(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
