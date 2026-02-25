#!/usr/bin/env python3
"""
Process scraped legislation details into individual files.

Takes the output from scrape_legislation_details.py and splits it into
individual JSON files in the legislation_details/ directory, one per ID.

Usage:
    python process_scraped_details.py legislation_details_2026.json
    python process_scraped_details.py --input my_scrape.json --output-dir custom_dir
"""

import json
import sys
from pathlib import Path
import argparse


def process_scraped_file(input_file, output_dir):
    """
    Process a scraped legislation details file.

    Args:
        input_file: Path to the scraped JSON file
        output_dir: Directory to write individual files to
    """
    input_path = Path(input_file)
    output_path = Path(output_dir)

    if not input_path.exists():
        print(f"❌ Error: Input file not found: {input_path}")
        sys.exit(1)

    # Create output directory if it doesn't exist
    output_path.mkdir(exist_ok=True)

    # Load the scraped data
    print(f"Loading scraped data from: {input_path}")
    with open(input_path, 'r') as f:
        data = json.load(f)

    results = data.get('results', [])
    total_results = len(results)

    if total_results == 0:
        print("⚠️  Warning: No results found in input file")
        return

    print(f"Processing {total_results} legislation items...")

    successful = 0
    failed = 0
    skipped = 0

    for result in results:
        legislation_id = result.get('id')
        success = result.get('success', False)

        if not legislation_id:
            print(f"  ⚠️  Skipping result with no ID")
            skipped += 1
            continue

        if not success:
            print(f"  ⚠️  Skipping failed scrape for ID {legislation_id}")
            failed += 1
            continue

        # Write individual file
        output_file = output_path / f"{legislation_id}.json"

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            successful += 1
            if successful % 10 == 0:
                print(f"  Processed {successful}/{total_results}...")

        except Exception as e:
            print(f"  ❌ Error writing file for ID {legislation_id}: {e}")
            failed += 1

    print()
    print("="*80)
    print("PROCESSING COMPLETE")
    print("="*80)
    print(f"Total results: {total_results}")
    print(f"✓ Successfully processed: {successful}")
    print(f"✗ Failed: {failed}")
    print(f"⊘ Skipped: {skipped}")
    print(f"Output directory: {output_path.absolute()}")
    print()

    # Show some examples
    if successful > 0:
        files = sorted(output_path.glob('*.json'))[:5]
        print("Example files created:")
        for f in files:
            file_size = f.stat().st_size
            print(f"  {f.name} ({file_size:,} bytes)")

        if successful > 5:
            print(f"  ... and {successful - 5} more")

    print()
    print("✅ Processing complete!")


def main():
    parser = argparse.ArgumentParser(
        description='Process scraped legislation details into individual files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python process_scraped_details.py legislation_details_2026.json
  python process_scraped_details.py --input my_scrape.json --output-dir custom_dir
        """
    )

    parser.add_argument(
        'input',
        nargs='?',
        help='Input JSON file from scraper (optional if using --input)'
    )
    parser.add_argument(
        '--input', '-i',
        dest='input_file',
        help='Input JSON file from scraper'
    )
    parser.add_argument(
        '--output-dir', '-o',
        default='legislation_details',
        help='Output directory for individual files (default: legislation_details)'
    )

    args = parser.parse_args()

    # Determine input file
    input_file = args.input or args.input_file

    if not input_file:
        print("❌ Error: No input file specified")
        parser.print_help()
        sys.exit(1)

    process_scraped_file(input_file, args.output_dir)


if __name__ == '__main__':
    main()
