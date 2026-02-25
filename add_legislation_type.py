#!/usr/bin/env python3
"""
Add legislation type field to all items.
Extracts type from the number field (pattern: YY-[TYPE]-####).
"""

import json
from pathlib import Path
import re
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('add_legislation_type.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Type mappings
TYPE_NAMES = {
    'R': 'Resolution',
    'O': 'Ordinance',
    'C': 'Communication',
    'RT': 'Report',
    'TR': 'Transfer'
}

def extract_type(number):
    """
    Extract type from legislation number.

    Handles multiple patterns:
    - Standard: YY-TYPE-####
    - Without middle dash: YY-TYPE####
    - With suffix: YY-TYPE-####A
    - Other variations

    Returns:
        tuple: (type_code, type_name) or (None, None)
    """
    if not number:
        return None, None

    number = number.strip()

    # Pattern 1: Standard format YY-TYPE-#### (with optional suffix)
    match = re.match(r'^\d{2}-([A-Z]+)-\d+[A-Z]?', number)
    if match:
        type_code = match.group(1)
        type_name = TYPE_NAMES.get(type_code, type_code)
        return type_code, type_name

    # Pattern 2: Missing middle dash YY-TYPE#### (like 13-C0626)
    match = re.match(r'^\d{2}-([A-Z]+)\d+', number)
    if match:
        type_code = match.group(1)
        type_name = TYPE_NAMES.get(type_code, type_code)
        return type_code, type_name

    # Pattern 3: Try to find any letters between dashes or digits
    match = re.search(r'-([A-Z]+)-', number)
    if match:
        type_code = match.group(1)
        type_name = TYPE_NAMES.get(type_code, type_code)
        return type_code, type_name

    return None, None

def process_all_files(dry_run=False):
    """
    Add legislation type field to all items.

    Args:
        dry_run: If True, don't modify files, just report statistics
    """
    meeting_dates_dir = Path("meeting_dates")

    if not meeting_dates_dir.exists():
        logger.error("meeting_dates directory not found")
        return

    stats = {
        'total_items': 0,
        'type_added': 0,
        'no_type': 0,
        'type_counts': {}
    }

    json_files = list(meeting_dates_dir.rglob("*.json"))
    logger.info(f"Processing {len(json_files)} files...")

    for idx, json_file in enumerate(json_files, 1):
        try:
            # Read file
            with open(json_file, 'r') as f:
                content = json.load(f)

            data = content.get('data', [])
            modified = False

            for item in data:
                stats['total_items'] += 1
                number = item.get('number', '')

                # Extract type
                type_code, type_name = extract_type(number)

                if type_code:
                    item['legislationType'] = type_code
                    item['legislationTypeName'] = type_name
                    stats['type_added'] += 1
                    stats['type_counts'][type_code] = stats['type_counts'].get(type_code, 0) + 1
                    modified = True
                else:
                    # No type extractable
                    item['legislationType'] = None
                    item['legislationTypeName'] = None
                    stats['no_type'] += 1
                    modified = True

            # Write back to file if modified and not dry run
            if modified and not dry_run:
                content['data'] = data
                with open(json_file, 'w') as f:
                    json.dump(content, f, indent=2)

        except Exception as e:
            logger.error(f"Error processing {json_file}: {e}")
            continue

        # Progress update
        if idx % 100 == 0:
            logger.info(f"Progress: {idx}/{len(json_files)} files processed")

    # Final report
    logger.info("\n" + "="*80)
    logger.info("LEGISLATION TYPE EXTRACTION COMPLETE")
    logger.info("="*80)
    logger.info(f"Total items processed: {stats['total_items']:,}")
    logger.info(f"Type added: {stats['type_added']:,} ({stats['type_added']/stats['total_items']*100:.1f}%)")
    logger.info(f"No type found: {stats['no_type']:,} ({stats['no_type']/stats['total_items']*100:.1f}%)")

    logger.info("\nType breakdown:")
    for type_code, count in sorted(stats['type_counts'].items(), key=lambda x: x[1], reverse=True):
        type_name = TYPE_NAMES.get(type_code, type_code)
        percentage = (count / stats['total_items']) * 100
        logger.info(f"  {type_code:5s} ({type_name:25s}): {count:8,} ({percentage:5.2f}%)")

    if dry_run:
        logger.info("\nDRY RUN - No files were modified")
    else:
        logger.info("\nFiles have been updated with legislation type fields")

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Add legislation type field to all items'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without modifying files'
    )

    args = parser.parse_args()

    if args.dry_run:
        logger.info("Starting extraction in DRY RUN mode...")
    else:
        logger.info("Starting legislation type extraction...")
        logger.warning("This will modify your JSON files. Press Ctrl+C within 3 seconds to cancel.")
        import time
        time.sleep(3)

    process_all_files(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
