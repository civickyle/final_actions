#!/usr/bin/env python3
"""
Extract final actions from legislation descriptions.
Creates a 'finalAction' field and removes the action from the description.
"""

import json
import re
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('extract_final_actions.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def extract_final_action(description):
    """
    Extract final action from description.

    Returns:
        tuple: (cleaned_description, final_action, needs_review)
    """
    if not description:
        return description, None, True

    # Action keywords in order of specificity
    action_keywords = [
        'ADOPTED', 'FILED', 'REFERRED', 'HELD', 'FAILED', 'APPROVED',
        'TABLED', 'CARRIED', 'PASSED', 'WITHDRAWN', 'VETOED', 'REJECTED',
        'DEFERRED', 'DEFEATED', 'ADVERSED', 'CONFIRMED', 'ACCEPTED'
    ]

    # Try to find action at the end of description
    # Pattern: Look for action keyword followed by optional details, typically at the end

    # First, try to find patterns with voting information (most specific)
    vote_pattern = r'\s+([A-Z][A-Z\s,;():/\-]*?(?:ROLL CALL VOTE|VOTE)[^.]*?(?:\d+\s*YEAS?;?\s*\d+\s*NAYS?|Y\/\d+N|\(\d+Y\/\d+N\))[^.]*?)$'
    match = re.search(vote_pattern, description)

    if match:
        final_action = match.group(1).strip()
        cleaned_desc = description[:match.start()].strip()
        return cleaned_desc, final_action, False

    # Try to find action with "ON CONSENT" or "WITHOUT OBJECTION"
    consent_pattern = r'\s+([A-Z][A-Z\s,;():/\-]*?(?:ON CONSENT|WITHOUT OBJECTION)[^.]*?)$'
    match = re.search(consent_pattern, description)

    if match:
        final_action = match.group(1).strip()
        cleaned_desc = description[:match.start()].strip()
        return cleaned_desc, final_action, False

    # Try to find simple action at the end
    for keyword in action_keywords:
        # Pattern: keyword followed by optional context, at the end
        simple_pattern = rf'\s+({keyword}(?:\s+[A-Z][A-Z\s,;():/\-]*?)?)$'
        match = re.search(simple_pattern, description)

        if match:
            final_action = match.group(1).strip()

            # Make sure we captured something meaningful
            if len(final_action) > len(keyword) + 50:  # Likely captured too much
                continue

            cleaned_desc = description[:match.start()].strip()

            # Medium confidence - has action but no vote details
            needs_review = len(final_action) <= len(keyword) + 5

            return cleaned_desc, final_action, needs_review

    # No clear action found
    return description, None, True

def process_all_files(dry_run=False):
    """
    Process all JSON files to extract final actions.

    Args:
        dry_run: If True, don't modify files, just report statistics
    """
    meeting_dates_dir = Path("meeting_dates")

    if not meeting_dates_dir.exists():
        logger.error("meeting_dates directory not found")
        return

    stats = {
        'total_items': 0,
        'extracted_high_conf': 0,
        'extracted_medium_conf': 0,
        'needs_review': 0,
        'no_action': 0
    }

    total_files = 0

    json_files = list(meeting_dates_dir.rglob("*.json"))
    logger.info(f"Processing {len(json_files)} files...")

    for json_file in json_files:
        total_files += 1

        try:
            # Read file
            with open(json_file, 'r') as f:
                content = json.load(f)

            data = content.get('data', [])
            modified = False

            for item in data:
                stats['total_items'] += 1
                description = item.get('description', '')

                # Extract final action
                cleaned_desc, final_action, needs_review = extract_final_action(description)

                # Update item
                if final_action:
                    item['finalAction'] = final_action
                    item['description'] = cleaned_desc

                    if needs_review:
                        item['needsReview'] = True
                        stats['extracted_medium_conf'] += 1
                    else:
                        stats['extracted_high_conf'] += 1

                    modified = True
                else:
                    # No action found - mark for review
                    item['needsReview'] = True
                    stats['needs_review'] += 1
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
        if total_files % 100 == 0:
            logger.info(f"Progress: {total_files}/{len(json_files)} files processed")

    # Final report
    logger.info("\n" + "="*80)
    logger.info("EXTRACTION COMPLETE")
    logger.info("="*80)
    logger.info(f"Total items processed: {stats['total_items']:,}")
    logger.info(f"Extracted (high confidence): {stats['extracted_high_conf']:,} ({stats['extracted_high_conf']/stats['total_items']*100:.1f}%)")
    logger.info(f"Extracted (medium confidence): {stats['extracted_medium_conf']:,} ({stats['extracted_medium_conf']/stats['total_items']*100:.1f}%)")
    logger.info(f"Marked for review (no action): {stats['needs_review']:,} ({stats['needs_review']/stats['total_items']*100:.1f}%)")

    if dry_run:
        logger.info("\nDRY RUN - No files were modified")
    else:
        logger.info("\nFiles have been updated with extracted final actions")

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Extract final actions from legislation descriptions'
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
        logger.info("Starting final action extraction...")
        logger.warning("This will modify your JSON files. Press Ctrl+C within 3 seconds to cancel.")
        import time
        time.sleep(3)

    process_all_files(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
