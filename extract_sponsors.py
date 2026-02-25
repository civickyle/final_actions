#!/usr/bin/env python3
"""
Extract sponsor (councilmember) names from legislation descriptions.
The sponsor information remains in the description after extraction.
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
        logging.FileHandler('extract_sponsors.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def extract_sponsors(description):
    """
    Extract sponsor names from description.

    Handles patterns like:
    - BY COUNCILMEMBER NAME
    - BY COUNCILMEMBERS NAME1 AND NAME2
    - BY COUNCILMEMBERS NAME1, NAME2 AND NAME3
    - BY COUNCIL MEMBER NAME
    - AS INTRODUCED BY COUNCILMEMBER NAME

    Returns:
        tuple: (list of sponsor names, confidence level)
        confidence: 'high', 'medium', 'low', or None
    """
    if not description:
        return None, None

    sponsors = []
    confidence = None

    # Pattern 1: BY COUNCILMEMBER(S) [NAMES]
    # Match "BY COUNCILMEMBER(S)" followed by names until we hit a verb or "AS AMENDED" or other keywords
    pattern1 = r'BY\s+COUNCIL\s*MEMBERS?\s+([A-Z][A-Z\s.,\-\'&]+?)(?:\s+AS\s+(?:AMENDED|SUBSTITUTED|INTRODUCED)|DIRECTING|AUTHORIZING|TO\s+(?:AMEND|AUTHORIZE|ZONE|PROHIBIT|CONVERT)|REQUESTING|EXPRESSING|RECOGNIZING)'

    match = re.search(pattern1, description, re.IGNORECASE)
    if match:
        names_text = match.group(1).strip()
        sponsors = parse_names(names_text)
        confidence = 'high' if sponsors else 'medium'
        return sponsors, confidence

    # Pattern 2: AS INTRODUCED BY COUNCILMEMBER [NAME]
    pattern2 = r'AS\s+INTRODUCED\s+BY\s+COUNCIL\s*MEMBERS?\s+([A-Z][A-Z\s.,\-\'&]+?)(?:\s+(?:AUTHORIZING|TO\s+|DIRECTING|REQUESTING|AS\s+))'

    match = re.search(pattern2, description, re.IGNORECASE)
    if match:
        names_text = match.group(1).strip()
        sponsors = parse_names(names_text)
        confidence = 'high' if sponsors else 'medium'
        return sponsors, confidence

    # Pattern 3: Look for COUNCILMEMBER at the start (more lenient)
    if description.strip().upper().startswith(('A RESOLUTION BY COUNCILMEMBER', 'AN ORDINANCE BY COUNCILMEMBER',
                                                'A RESOLUTION BY COUNCIL MEMBER', 'AN ORDINANCE BY COUNCIL MEMBER')):
        # Try to extract just the names part
        pattern3 = r'^(?:A\s+(?:RESOLUTION|ORDINANCE)\s+)?BY\s+COUNCIL\s*MEMBERS?\s+([A-Z][A-Z\s.,\-\'&]{5,100}?)\s+(?:DIRECTING|AUTHORIZING|TO\s|REQUESTING|EXPRESSING|RECOGNIZING|AS\s+)'

        match = re.search(pattern3, description, re.IGNORECASE)
        if match:
            names_text = match.group(1).strip()
            sponsors = parse_names(names_text)
            confidence = 'medium' if sponsors else 'low'
            return sponsors, confidence

    return None, None

def normalize_name(name):
    """
    Normalize a name to title case with special handling for prefixes and suffixes.
    """
    # Handle special cases that should remain uppercase
    uppercase_parts = ['II', 'III', 'IV', 'JR', 'SR']

    # Split into parts
    parts = name.split()
    normalized_parts = []

    for part in parts:
        # Remove punctuation for comparison
        part_clean = part.rstrip('.,')

        # Keep uppercase suffixes
        if part_clean.upper() in uppercase_parts:
            normalized_parts.append(part_clean.upper() + (part[len(part_clean):] if len(part) > len(part_clean) else ''))
        # Handle initials (single letter or letter with period)
        elif len(part_clean) <= 2 and part_clean[0].isupper():
            normalized_parts.append(part)
        # Title case for regular name parts
        else:
            # Special handling for hyphenated names
            if '-' in part:
                hyphen_parts = [p.capitalize() for p in part.split('-')]
                normalized_parts.append('-'.join(hyphen_parts))
            else:
                normalized_parts.append(part.capitalize())

    return ' '.join(normalized_parts)

def parse_names(names_text):
    """
    Parse individual names from a text string containing multiple names.

    Handles formats like:
    - "JOHN DOE"
    - "JOHN DOE AND JANE SMITH"
    - "JOHN DOE, JANE SMITH AND BOB JONES"
    - "JOHN DOE, JR. AND JANE SMITH"
    """
    if not names_text:
        return []

    # Clean up the text
    names_text = names_text.strip()

    # Remove trailing punctuation and clean spaces
    names_text = re.sub(r'\s+', ' ', names_text)
    names_text = re.sub(r'[,;]+$', '', names_text)

    # Split by AND (case insensitive)
    parts = re.split(r'\s+AND\s+', names_text, flags=re.IGNORECASE)

    sponsors = []
    for part in parts:
        # Further split by commas
        subparts = [p.strip() for p in part.split(',') if p.strip()]

        for name in subparts:
            # Clean the name
            name = name.strip()

            # Skip if too short or looks invalid
            if len(name) < 3:
                continue

            # Skip common non-name words that might leak in
            skip_words = ['AS AMENDED', 'AS SUBSTITUTED', 'COMMITTEE', 'DIRECTING',
                         'AUTHORIZING', 'REQUESTING', 'THE', 'TO']
            if any(skip in name.upper() for skip in skip_words):
                continue

            # Add to sponsors if it looks like a name (has at least one space or initials)
            if ' ' in name or re.search(r'[A-Z]\.\s*[A-Z]\.', name):
                # Normalize to title case
                normalized_name = normalize_name(name)
                sponsors.append(normalized_name)

    return sponsors

def process_all_files(dry_run=False):
    """
    Extract sponsor information from all items.

    Args:
        dry_run: If True, don't modify files, just report statistics
    """
    meeting_dates_dir = Path("meeting_dates")

    if not meeting_dates_dir.exists():
        logger.error("meeting_dates directory not found")
        return

    stats = {
        'total_items': 0,
        'sponsors_extracted': 0,
        'high_confidence': 0,
        'medium_confidence': 0,
        'low_confidence': 0,
        'no_sponsors': 0,
        'sponsor_counts': {}
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
                description = item.get('description', '')

                # Extract sponsors
                sponsors, confidence = extract_sponsors(description)

                if sponsors and confidence:
                    item['sponsors'] = sponsors
                    item['sponsorConfidence'] = confidence
                    stats['sponsors_extracted'] += 1

                    if confidence == 'high':
                        stats['high_confidence'] += 1
                    elif confidence == 'medium':
                        stats['medium_confidence'] += 1
                    else:
                        stats['low_confidence'] += 1

                    # Track individual sponsors
                    for sponsor in sponsors:
                        stats['sponsor_counts'][sponsor] = stats['sponsor_counts'].get(sponsor, 0) + 1

                    modified = True
                else:
                    stats['no_sponsors'] += 1

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
    logger.info("SPONSOR EXTRACTION COMPLETE")
    logger.info("="*80)
    logger.info(f"Total items processed: {stats['total_items']:,}")
    logger.info(f"Sponsors extracted: {stats['sponsors_extracted']:,} ({stats['sponsors_extracted']/stats['total_items']*100:.1f}%)")
    logger.info(f"  High confidence: {stats['high_confidence']:,} ({stats['high_confidence']/stats['total_items']*100:.1f}%)")
    logger.info(f"  Medium confidence: {stats['medium_confidence']:,} ({stats['medium_confidence']/stats['total_items']*100:.1f}%)")
    logger.info(f"  Low confidence: {stats['low_confidence']:,} ({stats['low_confidence']/stats['total_items']*100:.1f}%)")
    logger.info(f"No sponsors found: {stats['no_sponsors']:,} ({stats['no_sponsors']/stats['total_items']*100:.1f}%)")

    # Show top sponsors
    logger.info(f"\nTop 20 sponsors (by frequency):")
    for sponsor, count in sorted(stats['sponsor_counts'].items(), key=lambda x: x[1], reverse=True)[:20]:
        logger.info(f"  {sponsor:40s} {count:6,} items")

    if dry_run:
        logger.info("\nDRY RUN - No files were modified")
    else:
        logger.info("\nFiles have been updated with sponsor information")

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Extract sponsor information from legislation descriptions'
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
        logger.info("Starting sponsor extraction...")
        logger.warning("This will modify your JSON files. Press Ctrl+C within 3 seconds to cancel.")
        import time
        time.sleep(3)

    process_all_files(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
