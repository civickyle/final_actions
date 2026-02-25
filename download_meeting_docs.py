#!/usr/bin/env python3
"""
Download JSON data from Atlanta City Council MeetingDoc API.
Downloads documents with IDs from 1 to 40,000.
"""

import json
import time
import requests
from pathlib import Path
from datetime import datetime

# Configuration
API_URL = "https://atlantacityga.iqm2.com/api/MeetingDoc/{id}"
OUTPUT_DIR = Path('api_downloads/meeting_docs')
START_ID = 1
END_ID = 40000
DELAY_SECONDS = 0.1  # Delay between requests (be polite to the server)
PROGRESS_INTERVAL = 100  # Report progress every N downloads
ERROR_LOG_FILE = OUTPUT_DIR / 'download_errors.log'
SUCCESS_LOG_FILE = OUTPUT_DIR / 'download_success.log'

def setup_output_dir():
    """Create output directory if it doesn't exist."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR.absolute()}")

def get_filename(doc_id):
    """Generate filename for a document ID."""
    return OUTPUT_DIR / f"meeting_doc_{doc_id:05d}.json"

def download_document(doc_id, session, dry_run=False):
    """
    Download a single document from the API.

    Args:
        doc_id: The document ID to download
        session: requests.Session object for connection pooling
        dry_run: If True, only simulate the download

    Returns:
        tuple: (success, status_code, message)
    """
    url = API_URL.format(id=doc_id)
    filename = get_filename(doc_id)

    # Skip if file already exists (resume capability)
    if filename.exists():
        return (True, 'exists', 'File already exists')

    if dry_run:
        return (True, 'dry_run', f'Would download: {url}')

    try:
        response = session.get(url, timeout=30)

        if response.status_code == 200:
            # Validate JSON
            try:
                data = response.json()
                # Save to file
                with open(filename, 'w') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                return (True, 200, 'Success')
            except json.JSONDecodeError as e:
                return (False, 200, f'Invalid JSON: {e}')
        elif response.status_code == 404:
            return (False, 404, 'Not found')
        else:
            return (False, response.status_code, f'HTTP {response.status_code}')

    except requests.exceptions.Timeout:
        return (False, 'timeout', 'Request timeout')
    except requests.exceptions.RequestException as e:
        return (False, 'error', f'Request error: {e}')

def log_result(log_file, doc_id, status, message):
    """Append result to log file."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_file, 'a') as f:
        f.write(f"{timestamp} | ID {doc_id:05d} | {status} | {message}\n")

def download_all(dry_run=False):
    """
    Download all documents in the ID range.

    Args:
        dry_run: If True, only simulate downloads without making actual requests

    Returns:
        dict with download statistics
    """
    stats = {
        'total': END_ID - START_ID + 1,
        'downloaded': 0,
        'already_existed': 0,
        'not_found': 0,
        'errors': 0,
        'start_time': datetime.now()
    }

    print(f"\n{'='*80}")
    print(f"MEETING DOC DOWNLOAD {'(DRY RUN)' if dry_run else ''}")
    print(f"{'='*80}")
    print(f"API URL: {API_URL}")
    print(f"ID Range: {START_ID} to {END_ID}")
    print(f"Total documents: {stats['total']:,}")
    print(f"Delay between requests: {DELAY_SECONDS} seconds")
    print(f"Progress interval: every {PROGRESS_INTERVAL} documents")
    print(f"{'='*80}\n")

    # Use session for connection pooling
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    })

    try:
        for doc_id in range(START_ID, END_ID + 1):
            success, status, message = download_document(doc_id, session, dry_run)

            # Update statistics
            if status == 'exists':
                stats['already_existed'] += 1
            elif success and status == 200:
                stats['downloaded'] += 1
                if not dry_run:
                    log_result(SUCCESS_LOG_FILE, doc_id, status, message)
            elif status == 404:
                stats['not_found'] += 1
                if not dry_run:
                    log_result(ERROR_LOG_FILE, doc_id, status, message)
            else:
                stats['errors'] += 1
                if not dry_run:
                    log_result(ERROR_LOG_FILE, doc_id, status, message)

            # Progress reporting
            if doc_id % PROGRESS_INTERVAL == 0:
                elapsed = (datetime.now() - stats['start_time']).total_seconds()
                rate = doc_id / elapsed if elapsed > 0 else 0
                remaining = (END_ID - doc_id) / rate if rate > 0 else 0

                print(f"Progress: {doc_id:,}/{END_ID:,} "
                      f"| Downloaded: {stats['downloaded']:,} "
                      f"| Existed: {stats['already_existed']:,} "
                      f"| 404s: {stats['not_found']:,} "
                      f"| Errors: {stats['errors']:,} "
                      f"| Rate: {rate:.1f}/sec "
                      f"| ETA: {remaining/60:.1f} min")

            # Delay between requests (except on last iteration)
            if doc_id < END_ID and not dry_run:
                time.sleep(DELAY_SECONDS)

    except KeyboardInterrupt:
        print("\n\n⚠️  Download interrupted by user")
        print("You can resume by running the script again - it will skip existing files.\n")

    finally:
        session.close()

    stats['end_time'] = datetime.now()
    stats['duration'] = (stats['end_time'] - stats['start_time']).total_seconds()

    return stats

def print_report(stats):
    """Print final download report."""
    print(f"\n{'='*80}")
    print("DOWNLOAD COMPLETE")
    print(f"{'='*80}")
    print(f"Duration: {stats['duration']/60:.2f} minutes")
    print(f"Average rate: {(stats['downloaded'] + stats['already_existed']) / stats['duration']:.1f} docs/sec")
    print(f"\n{'─'*80}")
    print("RESULTS:")
    print(f"{'─'*80}")
    print(f"  Total processed: {stats['total']:,}")
    print(f"  Successfully downloaded: {stats['downloaded']:,}")
    print(f"  Already existed: {stats['already_existed']:,}")
    print(f"  Not found (404): {stats['not_found']:,}")
    print(f"  Errors: {stats['errors']:,}")

    total_files = stats['downloaded'] + stats['already_existed']
    print(f"\n  Total files saved: {total_files:,}")

    if stats['errors'] > 0 or stats['not_found'] > 0:
        print(f"\n📋 Check log files for details:")
        if stats['errors'] > 0:
            print(f"   Errors: {ERROR_LOG_FILE}")
        if stats['not_found'] > 0:
            print(f"   404s logged in: {ERROR_LOG_FILE}")
        if stats['downloaded'] > 0:
            print(f"   Successes: {SUCCESS_LOG_FILE}")

    print(f"\n{'='*80}\n")

if __name__ == '__main__':
    import sys

    dry_run = '--dry-run' in sys.argv
    skip_confirm = '--skip-confirm' in sys.argv

    if dry_run:
        print("\n🔍 DRY RUN MODE - No files will be downloaded")
        print("Run without --dry-run to actually download files\n")

    # Setup
    setup_output_dir()

    # Check if resuming
    existing_files = list(OUTPUT_DIR.glob('meeting_doc_*.json'))
    if existing_files and not dry_run:
        print(f"\n📁 Found {len(existing_files)} existing files - will skip these and resume")

    # Confirm if not dry run
    if not dry_run and not skip_confirm:
        print("\n⚠️  This will download up to 40,000 files!")
        print(f"   They will be saved to: {OUTPUT_DIR.absolute()}")
        print(f"   Estimated duration: ~2-3 hours (with 0.1s delay)")
        response = input("\nContinue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            sys.exit(0)

    # Download
    stats = download_all(dry_run=dry_run)

    # Report
    if not dry_run:
        print_report(stats)
    else:
        print("\n💡 To start downloading, run: python download_meeting_docs.py")
