#!/usr/bin/env python3
"""Build SQLite FTS5 index from OCR sidecar text files.

Reads ~71K .txt files from the OCR output directory, cross-references with
legislation metadata from meeting_dates/ JSON files, and creates a searchable
FTS5 database.
"""

import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from legislation_search_db import LegislationSearchDB


def build_metadata_lookup(meeting_dates_dir: Path) -> dict:
    """Build lookup from PDF filename stem to legislation metadata.

    Scans all meeting_dates/**/*.json files and extracts the stem from each
    item's pdfUrl (e.g. "20r3001" from ".../20r3001.pdf").

    Returns dict mapping stem -> metadata dict.
    """
    lookup = {}
    json_files = sorted(meeting_dates_dir.rglob('*.json'))
    # Skip .bak files
    json_files = [f for f in json_files if not f.name.endswith('.bak')]

    print(f"Scanning {len(json_files):,} meeting date files for metadata...")

    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        items = data.get('data', [])
        date_str = data.get('date', '')

        for item in items:
            pdf_url = item.get('pdfUrl', '')
            if not pdf_url:
                continue

            # Extract stem: "https://.../20r3001.pdf" -> "20r3001"
            filename = urlparse(pdf_url).path.rsplit('/', 1)[-1]
            stem = filename.replace('.pdf', '').lower()

            if stem and stem not in lookup:
                lookup[stem] = {
                    'legislation_number': item.get('number'),
                    'description': item.get('description'),
                    'legislation_date': date_str or (item.get('legislationDate', '')[:10] if item.get('legislationDate') else None),
                    'legislation_type': item.get('legislationTypeName'),
                    'sponsors': item.get('sponsors'),
                    'pdf_url': pdf_url,
                    'final_action': item.get('finalAction'),
                }

    print(f"Built metadata lookup: {len(lookup):,} entries")
    return lookup


def main():
    sidecar_dir = Path('/Volumes/Sandisk/Final Action Legislation – processed/ocr_text')
    meeting_dates_dir = Path('meeting_dates')
    db_path = Path('legislation_fts.db')

    if not sidecar_dir.exists():
        print(f"Error: Sidecar directory not found: {sidecar_dir}")
        return

    # Remove existing database to rebuild from scratch
    if db_path.exists():
        os.remove(db_path)
        print(f"Removed existing database: {db_path}")

    # Build metadata lookup
    metadata = build_metadata_lookup(meeting_dates_dir)

    # Initialize database
    db = LegislationSearchDB(str(db_path))
    db.init_database()

    # Find all .txt sidecar files
    txt_files = sorted(sidecar_dir.glob('*.txt'))
    total = len(txt_files)
    print(f"\nFound {total:,} text files to index")
    print()

    inserted = 0
    skipped = 0
    errors = 0
    start_time = time.time()

    # Use a transaction for bulk inserts
    db.conn.execute('BEGIN')

    for i, txt_path in enumerate(txt_files):
        paper_number = txt_path.stem

        try:
            text = txt_path.read_text(encoding='utf-8')
        except (IOError, UnicodeDecodeError):
            errors += 1
            continue

        # Skip placeholder files (PDFs that already had text)
        if text.strip() == '# PDF already contains searchable text':
            text = ''  # Store empty — they'll match on metadata only

        meta = metadata.get(paper_number, {})

        success = db.insert_document(
            paper_number=paper_number,
            text_content=text,
            legislation_number=meta.get('legislation_number'),
            description=meta.get('description'),
            legislation_date=meta.get('legislation_date'),
            legislation_type=meta.get('legislation_type'),
            sponsors=meta.get('sponsors'),
            pdf_url=meta.get('pdf_url'),
            char_count=len(text),
            final_action=meta.get('final_action'),
        )

        if success:
            inserted += 1
        else:
            skipped += 1

        # Progress every 1000 files
        if (i + 1) % 1000 == 0 or (i + 1) == total:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"  {i+1:,}/{total:,} ({(i+1)/total*100:.1f}%) - "
                  f"Inserted: {inserted:,} - Rate: {rate:.0f}/s")

    # Commit all inserts
    db.conn.commit()

    # Build FTS index
    print("\nBuilding FTS5 index...")
    fts_start = time.time()
    db.rebuild_fts()
    fts_elapsed = time.time() - fts_start
    print(f"FTS5 index built in {fts_elapsed:.1f}s")

    # Summary
    elapsed = time.time() - start_time
    stats = db.get_stats()
    db_size = db_path.stat().st_size / (1024 * 1024)

    print()
    print("=" * 60)
    print("Index Build Complete")
    print("=" * 60)
    print(f"Documents indexed:  {inserted:,}")
    print(f"Skipped (dupes):    {skipped:,}")
    print(f"Errors:             {errors:,}")
    print(f"Total characters:   {stats['total_characters']:,}")
    print(f"Date range:         {stats['earliest_date']} to {stats['latest_date']}")
    print(f"Database size:      {db_size:.1f} MB")
    print(f"Time elapsed:       {elapsed:.1f}s")

    db.close()


if __name__ == '__main__':
    main()
