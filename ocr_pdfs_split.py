#!/usr/bin/env python3
"""OCR PDFs with file range support for parallel processing across machines."""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple, Optional
import shutil

import pikepdf

def detect_page_rotation(image_path: str) -> Optional[int]:
    """Run Tesseract OSD on a single page image to detect rotation.

    Returns the rotation angle (0, 90, 180, 270) needed to correct
    the page, or None if detection fails.
    """
    try:
        result = subprocess.run(
            ['tesseract', image_path, '-', '--psm', '0'],
            capture_output=True,
            text=True,
            timeout=30
        )
        for line in result.stdout.splitlines() + result.stderr.splitlines():
            match = re.match(r'Rotate:\s+(\d+)', line)
            if match:
                angle = int(match.group(1))
                if angle in (90, 180, 270):
                    return angle
                return 0
        return None
    except (subprocess.TimeoutExpired, Exception):
        return None


def pre_rotate_pdf(pdf_path: Path, temp_dir: str) -> Path:
    """Detect and fix page rotation for all pages in a PDF.

    Renders each page to a grayscale image, runs Tesseract OSD to detect
    orientation, and applies rotation corrections using pikepdf.

    Returns path to the rotation-corrected PDF, or the original
    pdf_path if no rotation was needed.
    """
    image_prefix = os.path.join(temp_dir, 'page')

    try:
        render_result = subprocess.run(
            [
                'pdftoppm',
                '-gray',
                '-r', '150',
                str(pdf_path),
                image_prefix
            ],
            capture_output=True,
            text=True,
            timeout=120
        )
        if render_result.returncode != 0:
            return pdf_path
    except (subprocess.TimeoutExpired, Exception):
        return pdf_path

    page_images = sorted(
        [f for f in os.listdir(temp_dir) if f.startswith('page-') and f.endswith('.pgm')]
    )

    if not page_images:
        return pdf_path

    # Detect rotation for each page
    rotations = {}
    for i, img_name in enumerate(page_images):
        img_path = os.path.join(temp_dir, img_name)
        angle = detect_page_rotation(img_path)
        if angle is not None and angle != 0:
            rotations[i] = angle
        try:
            os.unlink(img_path)
        except OSError:
            pass

    if not rotations:
        return pdf_path

    # Apply rotations using pikepdf
    try:
        rotated_pdf_path = os.path.join(temp_dir, 'rotated.pdf')

        with pikepdf.Pdf.open(pdf_path) as pdf:
            for page_idx, angle in rotations.items():
                if page_idx < len(pdf.pages):
                    page = pdf.pages[page_idx]
                    existing_rotation = int(page.get('/Rotate', 0))
                    new_rotation = (existing_rotation + angle) % 360
                    page['/Rotate'] = new_rotation

            pdf.save(rotated_pdf_path)

        return Path(rotated_pdf_path)

    except Exception:
        return pdf_path


def ocr_pdf(pdf_path: Path, output_dir: Path, sidecar_dir: Path, gdrive_check_dirs: tuple = None) -> Tuple[str, bool, str, Optional[dict]]:
    """Process a single PDF with OCR."""
    filename = pdf_path.name
    output_pdf = output_dir / filename
    sidecar_txt = sidecar_dir / f"{pdf_path.stem}.txt"
    sidecar_json = sidecar_dir / f"{pdf_path.stem}.json"

    # Skip if already processed locally
    if output_pdf.exists() and sidecar_txt.exists():
        return (filename, True, "Already processed (local)", None)

    # Skip if already processed in Google Drive
    if gdrive_check_dirs:
        gdrive_output, gdrive_sidecar = gdrive_check_dirs
        gdrive_pdf = gdrive_output / filename
        gdrive_txt = gdrive_sidecar / f"{pdf_path.stem}.txt"
        if gdrive_pdf.exists() and gdrive_txt.exists():
            return (filename, True, "Already processed (Google Drive)", None)

    try:
        start_time = time.time()

        with tempfile.TemporaryDirectory(prefix='ocr_rotate_') as temp_dir:
            # Pre-rotate pages to fix orientation before OCR
            effective_pdf = pre_rotate_pdf(pdf_path, temp_dir)
            was_rotated = (effective_pdf != pdf_path)

            cmd = [
                'ocrmypdf',
                '--deskew',
                '--skip-text',
                '--sidecar', str(sidecar_txt),
                '--output-type', 'pdf',
                '--jobs', '1',
                str(effective_pdf),
                str(output_pdf)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            elapsed = time.time() - start_time

            if result.returncode == 0:
                original_size = pdf_path.stat().st_size
                output_size = output_pdf.stat().st_size
                text_size = sidecar_txt.stat().st_size if sidecar_txt.exists() else 0

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
                    'rotation_corrected': was_rotated,
                    'status': 'success'
                }

                with open(sidecar_json, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2)

                return (filename, True, f"Processed in {elapsed:.1f}s, {char_count} chars{' [rotated]' if was_rotated else ''}", metadata)

            elif result.returncode == 6:
                shutil.copy2(effective_pdf, output_pdf)
                sidecar_txt.write_text("# PDF already contains searchable text\n")

                metadata = {
                    'filename': filename,
                    'original_size_bytes': pdf_path.stat().st_size,
                    'status': 'already_has_text',
                    'rotation_corrected': was_rotated,
                    'processing_time_seconds': round(elapsed, 2)
                }

                with open(sidecar_json, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2)

                return (filename, True, f"Already has text{' [rotated]' if was_rotated else ''}", metadata)

            else:
                error_msg = result.stderr[:200] if result.stderr else "Unknown error"
                return (filename, False, f"OCR failed (code {result.returncode}): {error_msg}", None)

    except subprocess.TimeoutExpired:
        return (filename, False, "Timeout (>5 minutes)", None)
    except Exception as e:
        return (filename, False, f"Error: {str(e)[:200]}", None)

def main():
    # Parse command line arguments for file range
    start_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end_idx = int(sys.argv[2]) if len(sys.argv) > 2 else None

    # Configuration
    input_dir = Path('/Users/kylekessler/Library/CloudStorage/GoogleDrive-kyle@civicatlanta.org/Shared drives/CCI External/Public/City Legislation')

    # Use LOCAL directories for faster processing
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
    print("OCR Processing with OCRmyPDF (Split Mode)")
    print("=" * 80)
    print(f"Input directory:  {input_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Sidecar directory: {sidecar_dir}")
    print(f"Log directory:    {log_dir}")
    print()

    # Find all PDFs
    print("Finding PDF files...")
    pdf_files = sorted(input_dir.glob('*.pdf'))
    total_pdfs = len(pdf_files)

    # Apply range filter
    if end_idx:
        pdf_files = pdf_files[start_idx:end_idx]
    else:
        pdf_files = pdf_files[start_idx:]

    print(f"Total PDFs in directory: {total_pdfs:,}")
    print(f"Processing range: {start_idx:,} to {end_idx if end_idx else total_pdfs:,}")
    print(f"Files to process: {len(pdf_files):,}")
    print()

    # Track results
    successful = []
    failed = []
    metadata_list = []
    start_time = time.time()

    # Google Drive directories to check
    gdrive_output = input_dir / 'ocr_processed'
    gdrive_sidecar = input_dir / 'ocr_text'
    gdrive_check_dirs = (gdrive_output, gdrive_sidecar)

    # Concurrent processing
    max_workers = 8

    print(f"Starting OCR processing with {max_workers} workers...")
    print(f"Note: Skipping files already processed in Google Drive")
    print()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_pdf = {
            executor.submit(ocr_pdf, pdf_file, output_dir, sidecar_dir, gdrive_check_dirs): pdf_file
            for pdf_file in pdf_files
        }

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

            if completed % 10 == 0 or completed == len(pdf_files):
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = len(pdf_files) - completed
                eta = remaining / rate if rate > 0 else 0

                print(f"Progress: {completed:,}/{len(pdf_files):,} ({completed/len(pdf_files)*100:.1f}%) - "
                      f"Success: {len(successful):,} - Failed: {len(failed):,} - "
                      f"Rate: {rate:.1f}/s - ETA: {eta/3600:.1f}h")

                if completed % 100 == 0:
                    with open(log_dir / f'ocr_progress_{start_idx}_{end_idx}.json', 'w') as f:
                        json.dump({
                            'completed': completed,
                            'total': len(pdf_files),
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
    print(f"Total PDFs: {len(pdf_files):,}")
    print(f"Successful: {len(successful):,}")
    print(f"Failed: {len(failed):,}")
    print(f"Time elapsed: {elapsed_time/3600:.2f} hours")
    print(f"Average rate: {len(pdf_files)/elapsed_time:.2f} files/second")

    total_chars = sum(m.get('text_characters', 0) for m in metadata_list)
    print(f"Total text extracted: {total_chars:,} characters")

    # Save logs
    success_log = log_dir / f'ocr_success_{start_idx}_{end_idx}.json'
    with open(success_log, 'w') as f:
        json.dump(successful, f, indent=2)

    error_log = log_dir / f'ocr_errors_{start_idx}_{end_idx}.json'
    with open(error_log, 'w') as f:
        json.dump(failed, f, indent=2)

    metadata_log = log_dir / f'ocr_metadata_{start_idx}_{end_idx}.json'
    with open(metadata_log, 'w') as f:
        json.dump(metadata_list, f, indent=2)

    print(f"\nLogs saved to: {log_dir}")

if __name__ == '__main__':
    main()
