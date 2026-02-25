#!/usr/bin/env python3
"""Download all PDF files from the generated URLs."""

import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple
import urllib.request
import urllib.error

def download_pdf(url: str, output_dir: Path) -> Tuple[str, bool, str]:
    """Download a single PDF file.

    Returns:
        Tuple of (url, success, message)
    """
    # Extract filename from URL
    filename = url.split('/')[-1]
    output_path = output_dir / filename

    # Skip if already exists
    if output_path.exists():
        return (url, True, f"Already exists: {filename}")

    try:
        # Download the file
        urllib.request.urlretrieve(url, output_path)
        return (url, True, f"Downloaded: {filename}")
    except urllib.error.HTTPError as e:
        return (url, False, f"HTTP Error {e.code}: {filename}")
    except urllib.error.URLError as e:
        return (url, False, f"URL Error: {filename} - {e.reason}")
    except Exception as e:
        return (url, False, f"Error: {filename} - {str(e)}")

def main():
    # Configuration
    input_file = Path(__file__).parent / 'pdf_urls.json'
    output_dir = Path('/Users/kyle/Library/CloudStorage/GoogleDrive-kyle@civicatlanta.org/Shared drives/CCI External/Public/City Legislation')
    log_dir = Path(__file__).parent

    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Read URLs
    print("Loading URLs...")
    with open(input_file, 'r', encoding='utf-8') as f:
        urls = json.load(f)

    total_urls = len(urls)
    print(f"Total URLs to process: {total_urls}")
    print(f"Output directory: {output_dir}")
    print(f"\nStarting downloads...\n")

    # Track results
    successful = []
    failed = []
    start_time = time.time()

    # Use ThreadPoolExecutor for concurrent downloads
    max_workers = 10  # Adjust based on your network and server capacity

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all download tasks
        future_to_url = {executor.submit(download_pdf, url, output_dir): url for url in urls}

        # Process completed downloads
        completed = 0
        for future in as_completed(future_to_url):
            url, success, message = future.result()
            completed += 1

            if success:
                successful.append({'url': url, 'message': message})
            else:
                failed.append({'url': url, 'message': message})

            # Print progress every 100 files
            if completed % 100 == 0:
                elapsed = time.time() - start_time
                rate = completed / elapsed
                remaining = total_urls - completed
                eta = remaining / rate if rate > 0 else 0
                print(f"Progress: {completed}/{total_urls} ({completed/total_urls*100:.1f}%) - "
                      f"Success: {len(successful)} - Failed: {len(failed)} - "
                      f"Rate: {rate:.1f}/s - ETA: {eta/60:.1f}m")

    # Final summary
    elapsed_time = time.time() - start_time
    print(f"\n{'='*80}")
    print(f"Download Complete!")
    print(f"{'='*80}")
    print(f"Total processed: {total_urls}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    print(f"Time elapsed: {elapsed_time/60:.1f} minutes")
    print(f"Average rate: {total_urls/elapsed_time:.1f} files/second")

    # Save success log
    success_log = log_dir / 'download_success.json'
    with open(success_log, 'w', encoding='utf-8') as f:
        json.dump(successful, f, indent=2)
    print(f"\nSuccess log saved to: {success_log}")

    # Save error log
    error_log = log_dir / 'download_errors.json'
    with open(error_log, 'w', encoding='utf-8') as f:
        json.dump(failed, f, indent=2)
    print(f"Error log saved to: {error_log}")

    # Save summary
    summary_log = log_dir / 'download_summary.txt'
    with open(summary_log, 'w', encoding='utf-8') as f:
        f.write(f"Download Summary\n")
        f.write(f"{'='*80}\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total URLs: {total_urls}\n")
        f.write(f"Successful: {len(successful)}\n")
        f.write(f"Failed: {len(failed)}\n")
        f.write(f"Time elapsed: {elapsed_time/60:.1f} minutes\n")
        f.write(f"Average rate: {total_urls/elapsed_time:.1f} files/second\n")
        f.write(f"\nOutput directory: {output_dir}\n")
        f.write(f"Success log: {success_log}\n")
        f.write(f"Error log: {error_log}\n")
    print(f"Summary saved to: {summary_log}")

if __name__ == '__main__':
    main()
