#!/usr/bin/env python3
"""Extract text from PDFs that were skipped by OCR (already had text layers).

Finds sidecar files containing '[OCR skipped on page(s) ...]' and uses
pdftotext to extract the native text layer into the sidecar .txt file.
Then rebuilds the FTS index.
"""

import subprocess
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


def extract_text(pdf_path: Path, txt_path: Path):
    """Run pdftotext on a PDF, write result to txt_path."""
    try:
        result = subprocess.run(
            ['pdftotext', str(pdf_path), str(txt_path)],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and txt_path.exists():
            chars = txt_path.stat().st_size
            return (pdf_path.stem, True, chars)
        return (pdf_path.stem, False, result.stderr[:100])
    except subprocess.TimeoutExpired:
        return (pdf_path.stem, False, 'timeout')
    except Exception as e:
        return (pdf_path.stem, False, str(e)[:100])


def main():
    pdf_dir = Path('/Volumes/Sandisk/Final Action Legislation – processed')
    sidecar_dir = pdf_dir / 'ocr_text'

    # Find all sidecar files with the skip marker
    print("Scanning for OCR-skipped files...")
    skipped = []
    for txt_path in sorted(sidecar_dir.glob('*.txt')):
        try:
            text = txt_path.read_text(encoding='utf-8').strip()
            if text.startswith('[OCR skipped on page'):
                pdf_path = pdf_dir / f'{txt_path.stem}.pdf'
                if pdf_path.exists():
                    skipped.append((pdf_path, txt_path))
        except (IOError, UnicodeDecodeError):
            continue

    total = len(skipped)
    print(f"Found {total:,} OCR-skipped files to extract\n")

    if total == 0:
        print("Nothing to do.")
        return

    success = 0
    failed = 0
    total_chars = 0
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(extract_text, pdf, txt): pdf.stem
            for pdf, txt in skipped
        }

        completed = 0
        for future in as_completed(futures):
            stem, ok, detail = future.result()
            completed += 1

            if ok:
                success += 1
                total_chars += detail
            else:
                failed += 1

            if completed % 500 == 0 or completed == total:
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                print(f"  {completed:,}/{total:,} ({completed/total*100:.1f}%) - "
                      f"OK: {success:,} - Failed: {failed:,} - "
                      f"Rate: {rate:.1f}/s")

    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print("Extraction Complete")
    print("=" * 60)
    print(f"Extracted: {success:,}")
    print(f"Failed:    {failed:,}")
    print(f"Chars:     {total_chars:,}")
    print(f"Time:      {elapsed:.1f}s")

    # Rebuild FTS index
    if success > 0:
        print("\nRebuilding FTS index...")
        rebuild_fts_index(sidecar_dir)


def rebuild_fts_index(sidecar_dir: Path):
    """Rebuild the FTS database with updated sidecar text."""
    import subprocess as sp
    result = sp.run(
        ['.venv/bin/python3', 'build_fts_index.py'],
        capture_output=False, text=True
    )


if __name__ == '__main__':
    main()
