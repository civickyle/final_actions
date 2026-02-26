#!/usr/bin/env python3
"""OCR all PDFs with rotation detection/correction using OCRmyPDF."""

import json
import os
import re
import subprocess
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


def ocr_pdf(pdf_path: Path, output_dir: Path, sidecar_dir: Path) -> Tuple[str, bool, str, Optional[dict]]:
    """Process a single PDF with rotation detection and OCR."""
    filename = pdf_path.name
    output_pdf = output_dir / filename
    sidecar_txt = sidecar_dir / f"{pdf_path.stem}.txt"
    sidecar_json = sidecar_dir / f"{pdf_path.stem}.json"

    # Skip if already processed
    if output_pdf.exists() and sidecar_txt.exists():
        return (filename, True, "Already processed", None)

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
                # All pages already have text — copy the (possibly rotated) PDF
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
    # Configuration
    input_dir = Path('/Volumes/Sandisk/Final Action Legislation')
    output_dir = Path('/Volumes/Sandisk/Final Action Legislation \u2013 processed')
    sidecar_dir = output_dir / 'ocr_text'
    log_dir = Path(__file__).parent / 'ocr_logs'

    # Create directories
    output_dir.mkdir(exist_ok=True)
    sidecar_dir.mkdir(exist_ok=True)
    log_dir.mkdir(exist_ok=True)

    print("=" * 80)
    print("OCR Processing with Rotation Detection")
    print("=" * 80)
    print(f"Input directory:   {input_dir}")
    print(f"Output directory:  {output_dir}")
    print(f"Sidecar directory: {sidecar_dir}")
    print(f"Log directory:     {log_dir}")
    print()

    # Find all PDFs
    print("Finding PDF files...")
    all_pdf_files = sorted(input_dir.glob('*.pdf'))
    total_all = len(all_pdf_files)

    # Pre-filter: skip files already processed
    pdf_files = []
    skipped = 0
    for pdf_path in all_pdf_files:
        out_pdf = output_dir / pdf_path.name
        out_txt = sidecar_dir / f"{pdf_path.stem}.txt"
        if out_pdf.exists() and out_txt.exists():
            skipped += 1
        else:
            pdf_files.append(pdf_path)

    total_pdfs = len(pdf_files)

    print(f"Found {total_all:,} total PDF files")
    print(f"Skipping {skipped:,} already processed")
    print(f"Remaining to process: {total_pdfs:,}")
    print()

    if total_pdfs == 0:
        print("Nothing to process.")
        return

    # Track results
    successful = []
    failed = []
    metadata_list = []
    start_time = time.time()

    max_workers = 8

    print(f"Starting OCR processing with {max_workers} workers...")
    print()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_pdf = {
            executor.submit(ocr_pdf, pdf_file, output_dir, sidecar_dir): pdf_file
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
    if elapsed_time > 0:
        print(f"Average rate: {total_pdfs/elapsed_time:.2f} files/second")

    total_chars = sum(m.get('text_characters', 0) for m in metadata_list)
    rotated_count = sum(1 for m in metadata_list if m.get('rotation_corrected'))
    print(f"Total text extracted: {total_chars:,} characters")
    print(f"Files with rotation correction: {rotated_count:,}")
    print()

    # Save detailed logs
    with open(log_dir / 'ocr_success.json', 'w') as f:
        json.dump(successful, f, indent=2)

    with open(log_dir / 'ocr_errors.json', 'w') as f:
        json.dump(failed, f, indent=2)

    with open(log_dir / 'ocr_metadata.json', 'w') as f:
        json.dump(metadata_list, f, indent=2)

    with open(log_dir / 'ocr_summary.txt', 'w') as f:
        f.write("OCR Processing Summary\n")
        f.write("=" * 80 + "\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total PDFs: {total_pdfs:,}\n")
        f.write(f"Successful: {len(successful):,}\n")
        f.write(f"Failed: {len(failed):,}\n")
        f.write(f"Time elapsed: {elapsed_time/3600:.2f} hours\n")
        f.write(f"Files with rotation correction: {rotated_count:,}\n")
        f.write(f"Total text extracted: {total_chars:,} characters\n")
        f.write(f"\nDirectories:\n")
        f.write(f"  Input: {input_dir}\n")
        f.write(f"  OCR PDFs: {output_dir}\n")
        f.write(f"  Text files: {sidecar_dir}\n")
        f.write(f"  Logs: {log_dir}\n")

    print(f"Logs saved to: {log_dir}")


if __name__ == '__main__':
    main()
