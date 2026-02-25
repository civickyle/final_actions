#!/usr/bin/env python3
"""OCR all PDFs using OCRmyPDF with sidecar text files."""

import json
import subprocess
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple, Optional
import shutil

def ocr_pdf(pdf_path: Path, output_dir: Path, sidecar_dir: Path, gdrive_check_dirs: tuple = None) -> Tuple[str, bool, str, Optional[dict]]:
    """Process a single PDF with OCR.

    Returns:
        Tuple of (filename, success, message, metadata)
    """
    filename = pdf_path.name
    output_pdf = output_dir / filename
    sidecar_txt = sidecar_dir / f"{pdf_path.stem}.txt"
    sidecar_json = sidecar_dir / f"{pdf_path.stem}.json"

    # Skip if already processed locally
    if output_pdf.exists() and sidecar_txt.exists():
        return (filename, True, "Already processed (local)", None)

    # Skip if already processed in Google Drive (from previous run)
    if gdrive_check_dirs:
        gdrive_output, gdrive_sidecar = gdrive_check_dirs
        gdrive_pdf = gdrive_output / filename
        gdrive_txt = gdrive_sidecar / f"{pdf_path.stem}.txt"
        if gdrive_pdf.exists() and gdrive_txt.exists():
            return (filename, True, "Already processed (Google Drive)", None)

    try:
        start_time = time.time()

        # Run OCRmyPDF with sidecar text output
        # --rotate-pages: Automatically rotate pages to correct orientation
        # --deskew: Straighten pages that are slightly skewed
        # --clean: Clean artifacts from scans
        # --skip-text: Skip pages that already have text
        # --sidecar: Create text file with extracted text
        cmd = [
            'ocrmypdf',
            '--rotate-pages',
            '--rotate-pages-threshold', '0',  # Force rotation even with low confidence
            '--deskew',
            '--skip-text',
            '--sidecar', str(sidecar_txt),
            '--output-type', 'pdf',
            '--jobs', '1',  # Single job per process (we handle parallelism)
            str(pdf_path),
            str(output_pdf)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout per PDF
        )

        elapsed = time.time() - start_time

        if result.returncode == 0:
            # Get file sizes for metadata
            original_size = pdf_path.stat().st_size
            output_size = output_pdf.stat().st_size
            text_size = sidecar_txt.stat().st_size if sidecar_txt.exists() else 0

            # Read sidecar text to get character count
            char_count = 0
            if sidecar_txt.exists():
                with open(sidecar_txt, 'r', encoding='utf-8') as f:
                    char_count = len(f.read())

            metadata = {
                'filename': filename,
                'original_size_bytes': original_size,
                'output_size_bytes': output_size,
                'sidecar_size_bytes': text_size,
                'text_characters': char_count,
                'processing_time_seconds': round(elapsed, 2),
                'status': 'success'
            }

            # Save metadata as JSON sidecar
            with open(sidecar_json, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)

            return (filename, True, f"Processed in {elapsed:.1f}s, {char_count} chars", metadata)

        elif result.returncode == 6:
            # Exit code 6 means PDF already has text - copy it and note it
            shutil.copy2(pdf_path, output_pdf)

            # Create empty sidecar to mark as processed
            sidecar_txt.write_text("# PDF already contains searchable text\n")

            metadata = {
                'filename': filename,
                'original_size_bytes': pdf_path.stat().st_size,
                'status': 'already_has_text',
                'processing_time_seconds': round(elapsed, 2)
            }

            with open(sidecar_json, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)

            return (filename, True, "Already has text", metadata)

        else:
            error_msg = result.stderr[:200] if result.stderr else "Unknown error"
            return (filename, False, f"OCR failed (code {result.returncode}): {error_msg}", None)

    except subprocess.TimeoutExpired:
        return (filename, False, "Timeout (>5 minutes)", None)
    except Exception as e:
        return (filename, False, f"Error: {str(e)[:200]}", None)

def main():
    # Configuration
    input_dir = Path.home() / 'Library/CloudStorage/GoogleDrive-kyle@civicatlanta.org/Shared drives/CCI External/Public/City Legislation'

    # TEMPORARY: Use LOCAL directories for faster processing (no Google Drive sync overhead)
    # Will copy to Google Drive when complete
    local_base = Path(__file__).parent / 'ocr_output_local'
    output_dir = local_base / 'ocr_processed'
    sidecar_dir = local_base / 'ocr_text'
    log_dir = Path(__file__).parent / 'ocr_logs'

    # Create directories
    local_base.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    sidecar_dir.mkdir(exist_ok=True)
    log_dir.mkdir(exist_ok=True)

    print("=" * 80)
    print("OCR Processing with OCRmyPDF")
    print("=" * 80)
    print(f"Input directory:  {input_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Sidecar directory: {sidecar_dir}")
    print(f"Log directory:    {log_dir}")
    print()

    # Find all PDFs
    print("Finding PDF files...")
    all_pdf_files = sorted(input_dir.glob('*.pdf'))
    total_all = len(all_pdf_files)

    # Google Drive directories to check for already-processed files
    gdrive_output = input_dir / 'ocr_processed'
    gdrive_sidecar = input_dir / 'ocr_text'
    gdrive_check_dirs = (gdrive_output, gdrive_sidecar)

    # Pre-filter: skip files already processed locally or in Google Drive
    pdf_files = []
    skipped = 0
    for pdf_path in all_pdf_files:
        out_pdf = output_dir / pdf_path.name
        out_txt = sidecar_dir / f"{pdf_path.stem}.txt"
        gd_pdf = gdrive_output / pdf_path.name
        gd_txt = gdrive_sidecar / f"{pdf_path.stem}.txt"
        if (out_pdf.exists() and out_txt.exists()) or (gd_pdf.exists() and gd_txt.exists()):
            skipped += 1
        else:
            pdf_files.append(pdf_path)

    total_pdfs = len(pdf_files)

    print(f"Found {total_all:,} total PDF files")
    print(f"Skipping {skipped:,} already processed")
    print(f"Remaining to process: {total_pdfs:,}")
    print()

    # Track results
    successful = []
    failed = []
    metadata_list = []
    start_time = time.time()

    # Concurrent processing
    max_workers = 8  # OCR is CPU-intensive, adjust based on your machine

    print(f"Starting OCR processing with {max_workers} workers...")
    print()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_pdf = {
            executor.submit(ocr_pdf, pdf_file, output_dir, sidecar_dir, gdrive_check_dirs): pdf_file
            for pdf_file in pdf_files
        }

        # Process completed tasks
        completed = 0
        for future in as_completed(future_to_pdf):
            filename, success, message, metadata = future.result()
            completed += 1

            if success:
                successful.append({'filename': filename, 'message': message})
                if metadata:
                    metadata_list.append(metadata)
            else:
                failed.append({'filename': filename, 'error': message})

            # Progress update every 10 files
            if completed % 10 == 0 or completed == total_pdfs:
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = total_pdfs - completed
                eta = remaining / rate if rate > 0 else 0

                print(f"Progress: {completed:,}/{total_pdfs:,} ({completed/total_pdfs*100:.1f}%) - "
                      f"Success: {len(successful):,} - Failed: {len(failed):,} - "
                      f"Rate: {rate:.1f}/s - ETA: {eta/3600:.1f}h")

                # Save intermediate results every 100 files
                if completed % 100 == 0:
                    # Save progress
                    with open(log_dir / 'ocr_progress.json', 'w') as f:
                        json.dump({
                            'completed': completed,
                            'total': total_pdfs,
                            'successful': len(successful),
                            'failed': len(failed),
                            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                        }, f, indent=2)

    # Final summary
    elapsed_time = time.time() - start_time

    print()
    print("=" * 80)
    print("OCR Processing Complete!")
    print("=" * 80)
    print(f"Total PDFs: {total_pdfs:,}")
    print(f"Successful: {len(successful):,}")
    print(f"Failed: {len(failed):,}")
    print(f"Time elapsed: {elapsed_time/3600:.2f} hours")
    print(f"Average rate: {total_pdfs/elapsed_time:.2f} files/second")

    # Calculate total text extracted
    total_chars = sum(m.get('text_characters', 0) for m in metadata_list)
    print(f"Total text extracted: {total_chars:,} characters")
    print()

    # Save detailed logs
    success_log = log_dir / 'ocr_success.json'
    with open(success_log, 'w') as f:
        json.dump(successful, f, indent=2)
    print(f"Success log: {success_log}")

    error_log = log_dir / 'ocr_errors.json'
    with open(error_log, 'w') as f:
        json.dump(failed, f, indent=2)
    print(f"Error log: {error_log}")

    metadata_log = log_dir / 'ocr_metadata.json'
    with open(metadata_log, 'w') as f:
        json.dump(metadata_list, f, indent=2)
    print(f"Metadata log: {metadata_log}")

    # Summary report
    summary_file = log_dir / 'ocr_summary.txt'
    with open(summary_file, 'w') as f:
        f.write("OCR Processing Summary\n")
        f.write("=" * 80 + "\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total PDFs: {total_pdfs:,}\n")
        f.write(f"Successful: {len(successful):,}\n")
        f.write(f"Failed: {len(failed):,}\n")
        f.write(f"Time elapsed: {elapsed_time/3600:.2f} hours\n")
        f.write(f"Average rate: {total_pdfs/elapsed_time:.2f} files/second\n")
        f.write(f"Total text extracted: {total_chars:,} characters\n")
        f.write(f"\nDirectories:\n")
        f.write(f"  Input: {input_dir}\n")
        f.write(f"  OCR PDFs: {output_dir}\n")
        f.write(f"  Text files: {sidecar_dir}\n")
        f.write(f"  Logs: {log_dir}\n")

    print(f"Summary: {summary_file}")
    print()
    print("Original PDFs remain untouched in the input directory.")
    print("OCR-processed PDFs are in: ocr_processed/")
    print("Extracted text files are in: ocr_text/")

if __name__ == '__main__':
    main()
