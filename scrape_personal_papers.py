#!/usr/bin/env python3
"""
Download, split, and store Atlanta City Council Personal Papers PDFs.

The combined PDF is posted at:
  https://citycouncil.atlantaga.gov/legislation/personal-papers

Each package contains a TOC on page 1 and PDF bookmarks that map each
piece of legislation to its page range. We use those bookmarks to split
the combined PDF into individual items — no OCR required for splitting.

Usage:
    # Process a locally downloaded PDF
    python scrape_personal_papers.py --pdf "Personal Paper Summary 3226.pdf"

    # Scrape the page for new PDFs and process them (requires playwright)
    python scrape_personal_papers.py --auto [--visible]

    # Re-process a package already in the DB (re-split, re-OCR)
    python scrape_personal_papers.py --reprocess <package_id>
"""

import argparse
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pypdf
import pypdf.annotations

import personal_papers_db as db

# ── Directories ──────────────────────────────────────────────────────────────

BASE_DIR      = Path(__file__).parent
PP_DIR        = BASE_DIR / "personal_papers"
COMBINED_DIR  = PP_DIR / "combined"
ITEMS_DIR     = PP_DIR / "items"
OCR_DIR       = PP_DIR / "ocr"

for d in (COMBINED_DIR, ITEMS_DIR, OCR_DIR):
    d.mkdir(parents=True, exist_ok=True)

SOURCE_URL = "https://citycouncil.atlantaga.gov/legislation/personal-papers"


# ── TOC parsing ──────────────────────────────────────────────────────────────

def parse_toc(text):
    """Parse the summary table from page 1 text.

    Returns a list of dicts: row, elms_id, leg_id, sponsor, description,
    leg_type, committee.
    """
    lines = [l.strip() for l in text.splitlines()]

    # Group lines into items. Each item starts with: <number> <5-digit ELMS>
    item_start = re.compile(r'^(\d+)\s+(\d{5})\s+')
    groups = []
    current = []
    for line in lines:
        if item_start.match(line):
            if current:
                groups.append(" ".join(current))
            current = [line]
        elif current and line:
            current.append(line)
    if current:
        groups.append(" ".join(current))

    items = []
    for group in groups:
        group = " ".join(group.split())  # normalize whitespace

        # Pattern: row  elms  leg_id  sponsor  description  type  committee
        # leg_id may have OCR-introduced spaces (e.g. "26-R-330 0")
        m = re.match(
            r'^(\d+)\s+(\d{5})\s+'          # row, elms
            r'(\d{2}-[OR]-[\d ]{3,7})\s+'   # leg_id (with possible spaces)
            r'(\S+)\s+'                       # sponsor
            r'(.+?)\s+'                       # description
            r'(Resolution|Ordinance)\s*'      # type
            r'(.*)',                           # committee (optional)
            group,
            re.IGNORECASE,
        )
        if not m:
            continue

        leg_id = re.sub(r'\s+', '', m.group(3))  # strip OCR spaces from ID
        items.append({
            "row":         int(m.group(1)),
            "elms_id":     m.group(2),
            "leg_id":      leg_id,
            "sponsor":     m.group(4),
            "description": m.group(5).strip(),
            "leg_type":    m.group(6),
            "committee":   m.group(7).strip(),
        })

    return items


def parse_meeting_date(text):
    """Extract meeting date from TOC header text (e.g. 'MARCH 2, 2026')."""
    m = re.search(
        r'(january|february|march|april|may|june|july|august|september|'
        r'october|november|december)\s+\d{1,2},?\s+\d{4}',
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    try:
        for fmt in ("%B %d, %Y", "%B %d %Y"):
            try:
                dt = datetime.strptime(m.group(0).replace(",", ", ").strip(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
    except Exception:
        pass
    return None


# ── Bookmark / page-range parsing ─────────────────────────────────────────────

def parse_bookmarks(reader):
    """Read PDF bookmarks to get the page range for each item.

    Returns list of dicts: row, elms_id, page_start (0-indexed), page_end.
    """
    # Map indirect-object id → 0-based page index
    page_map = {
        page.indirect_reference.idnum: i
        for i, page in enumerate(reader.pages)
    }
    total = len(reader.pages)
    outline = reader.outline

    entries = []
    for entry in outline:
        if not isinstance(entry, dict):
            continue
        title = entry.get("/Title", "")
        m = re.match(r"#(\d+)_(\d+)", title)
        if not m:
            continue
        page_ref = entry.get("/Page")
        if not page_ref:
            continue
        entries.append({
            "row":        int(m.group(1)),
            "elms_id":    m.group(2),
            "page_start": page_map.get(page_ref.idnum, 0),
        })

    # Compute page_end = next item's start - 1
    for i, e in enumerate(entries):
        if i + 1 < len(entries):
            e["page_end"] = entries[i + 1]["page_start"] - 1
        else:
            e["page_end"] = total - 1

    return entries


# ── Enriched combined PDF (internal TOC hyperlinks) ──────────────────────────

def create_linked_combined_pdf(source_path, items, output_path):
    """Create a copy of the combined PDF where each TOC row on page 1
    is a clickable internal link jumping to that item's first page.

    Returns True on success, False if text positions could not be found.
    """
    reader = pypdf.PdfReader(str(source_path))
    toc_page = reader.pages[0]
    page_width  = float(toc_page.mediabox.width)   # typically 612 pt
    page_height = float(toc_page.mediabox.height)  # typically 792 pt

    # Extract (text, y) pairs from the TOC page.
    # Most rows arrive as a single chunk containing the ELMS number.
    text_chunks = []

    def _capture(text, cm, tm, fontDict, fontSize):
        t = text.strip()
        y = float(tm[5])
        if t and y > 0:
            text_chunks.append((t, y))

    toc_page.extract_text(visitor_text=_capture)

    # Map elms_id → y-coordinate of its TOC row
    elms_y = {}
    for t, y in text_chunks:
        for item in items:
            if item["elms_id"] in t and item["elms_id"] not in elms_y:
                elms_y[item["elms_id"]] = y

    if not elms_y:
        print("  ⚠  Could not extract text positions from TOC — skipping link enrichment")
        return False

    # Clone all pages into a writer
    writer = pypdf.PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    # Overlay a link annotation for each matched row.
    # Rect spans full page width; height is ~15 pt to cover one text line.
    linked = 0
    for item in items:
        y = elms_y.get(item["elms_id"])
        if y is None:
            continue
        annotation = pypdf.annotations.Link(
            rect=(0, y - 3, page_width, y + 14),
            target_page_index=item["page_start"],
        )
        writer.add_annotation(page_number=0, annotation=annotation)
        linked += 1

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        writer.write(f)

    print(f"   Linked PDF   : {linked}/{len(items)} TOC rows linked → {output_path.name}")
    return True


# ── PDF splitting ─────────────────────────────────────────────────────────────

def split_pdf(source_path, items, package_id):
    """Write one PDF per item into ITEMS_DIR/<package_id>/.

    Merges bookmark data and TOC data (keyed by elms_id).
    Returns updated items list with pdf_path set.
    """
    out_dir = ITEMS_DIR / str(package_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    reader = pypdf.PdfReader(str(source_path))

    for item in items:
        writer = pypdf.PdfWriter()
        for page_idx in range(item["page_start"], item["page_end"] + 1):
            if page_idx < len(reader.pages):
                writer.add_page(reader.pages[page_idx])

        leg_id_safe = re.sub(r"[^A-Za-z0-9_-]", "_", item.get("leg_id", item["elms_id"]))
        filename = f"{item['elms_id']}_{leg_id_safe}.pdf"
        out_path = out_dir / filename
        with open(out_path, "wb") as f:
            writer.write(f)
        item["pdf_path"] = str(out_path)
        print(f"  [{item['row']:>3}] {item.get('leg_id','?'):12}  pages {item['page_start']+1}–{item['page_end']+1}  → {filename}")

    return items


# ── Core processor ────────────────────────────────────────────────────────────

def process_pdf(pdf_path, source_url=None, package_id=None):
    """Process a personal papers PDF: parse → OCR → split → link → store in DB.

    Pipeline:
      1. Parse TOC + bookmarks from original PDF
      2. OCR the combined PDF (adds text layer to scanned pages)
      3. Split the OCR'd PDF into per-item PDFs
      4. Add internal TOC hyperlinks to the OCR'd combined PDF → enriched PDF
      5. Store everything in DB

    If package_id is provided the package record already exists (reprocess).
    Returns the package_id.
    """
    import shutil, tempfile
    pdf_path = Path(pdf_path)
    print(f"\n📄 Processing: {pdf_path.name}")

    reader = pypdf.PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    print(f"   {total_pages} pages")

    # ── 1. Parse TOC (page 1) ─────────────────────────────────────────────
    page1_text = reader.pages[0].extract_text() or ""
    toc_items  = parse_toc(page1_text)
    meeting_date = parse_meeting_date(page1_text)

    print(f"   Meeting date : {meeting_date or '(not found)'}")
    print(f"   TOC items    : {len(toc_items)}")

    # ── 2. Parse bookmarks ────────────────────────────────────────────────
    bm_items = parse_bookmarks(reader)
    print(f"   Bookmarks    : {len(bm_items)}")

    # ── 3. Merge by elms_id ───────────────────────────────────────────────
    toc_by_elms = {t["elms_id"]: t for t in toc_items}
    merged = []
    for bm in bm_items:
        toc = toc_by_elms.get(bm["elms_id"], {})
        merged.append({
            "row":         bm["row"],
            "elms_id":     bm["elms_id"],
            "leg_id":      toc.get("leg_id", ""),
            "sponsor":     toc.get("sponsor", ""),
            "description": toc.get("description", ""),
            "leg_type":    toc.get("leg_type", ""),
            "committee":   toc.get("committee", ""),
            "page_start":  bm["page_start"],
            "page_end":    bm["page_end"],
        })

    if not merged:
        print("  ⚠  No items found — check bookmarks and TOC")
        return None

    # ── 4. Create / update DB package record ──────────────────────────────
    db.init_db()

    dest = COMBINED_DIR / pdf_path.name
    if pdf_path.resolve() != dest.resolve():
        shutil.copy2(pdf_path, dest)
        print(f"   Copied to    : {dest}")

    if package_id is None:
        package_id = db.insert_package(
            source_url   = source_url or "",
            meeting_date = meeting_date or "",
            filename     = pdf_path.name,
            pdf_path     = str(dest),
        )
        print(f"   Package ID   : {package_id}")
    else:
        print(f"   Reprocessing package {package_id}")

    # ── 5. OCR the combined PDF ───────────────────────────────────────────
    # Run OCR once on the combined PDF so that all downstream PDFs
    # (split items + enriched combined) inherit a searchable text layer.
    ocr_available = _check_ocrmypdf()
    source = dest  # fallback: use original if OCR unavailable/fails

    if ocr_available:
        ocr_dir = COMBINED_DIR / "ocr"
        ocr_dir.mkdir(parents=True, exist_ok=True)
        ocr_combined = ocr_dir / dest.name
        tmp = Path(tempfile.mktemp(suffix=".pdf"))
        print(f"\n🔍 Running OCR on combined PDF ({total_pages} pages) ...")
        try:
            result = subprocess.run(
                [
                    "ocrmypdf",
                    "--deskew",
                    "--skip-text",
                    "--output-type", "pdf",
                    "--jobs", "4",
                    str(dest),
                    str(tmp),
                ],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode in (0, 6) and tmp.exists():
                shutil.move(str(tmp), str(ocr_combined))
                source = ocr_combined
                print(f"   ✅ OCR complete → {ocr_combined.name}")
            else:
                print(f"   ⚠  OCR returned code {result.returncode}: {result.stderr[:200]}")
                tmp.unlink(missing_ok=True)
        except subprocess.TimeoutExpired:
            print("   ⚠  OCR timed out — continuing without OCR")
            tmp.unlink(missing_ok=True)
    else:
        print("\n⚠  ocrmypdf not found — skipping OCR (install with: brew install ocrmypdf)")

    # ── 6. Save TOC pages as a standalone PDF ─────────────────────────────
    first_item_page = merged[0]["page_start"] if merged else 1
    if first_item_page > 0:
        toc_dir = ITEMS_DIR / str(package_id)
        toc_dir.mkdir(parents=True, exist_ok=True)
        toc_path = toc_dir / "00_TOC.pdf"
        toc_reader = pypdf.PdfReader(str(source))
        toc_writer = pypdf.PdfWriter()
        for i in range(first_item_page):
            toc_writer.add_page(toc_reader.pages[i])
        with open(toc_path, "wb") as f:
            toc_writer.write(f)
        db.set_toc_pdf_path(package_id, str(toc_path))
        print(f"   TOC PDF      : {toc_path.name} ({first_item_page} page(s))")

    # ── 7. Split from OCR'd source ────────────────────────────────────────
    print(f"\n✂  Splitting into {len(merged)} items:")
    merged = split_pdf(source, merged, package_id)

    # ── 8. Enriched combined PDF: OCR'd + internal TOC links ──────────────
    enriched_path = COMBINED_DIR / "enriched" / dest.name
    ok = create_linked_combined_pdf(source, merged, enriched_path)
    if ok:
        db.set_enriched_pdf_path(package_id, str(enriched_path))

    # ── 9. Store items in DB ──────────────────────────────────────────────
    # Split items come from the OCR'd source, so they already have a text
    # layer. Extract that text with pypdf for the ocr_text DB column.
    for item in merged:
        ocr_text = None
        if item.get("pdf_path"):
            try:
                r = pypdf.PdfReader(item["pdf_path"])
                ocr_text = "\n".join(
                    p.extract_text() or "" for p in r.pages
                ).strip() or None
            except Exception:
                pass

        db.insert_item(
            package_id  = package_id,
            row_num     = item["row"],
            elms_id     = item["elms_id"],
            leg_id      = item["leg_id"],
            sponsor     = item["sponsor"],
            description = item["description"],
            leg_type    = item["leg_type"],
            committee   = item["committee"],
            page_start  = item["page_start"],
            page_end    = item["page_end"],
            pdf_path    = item.get("pdf_path"),
            ocr_text    = ocr_text,
        )

    db.mark_package_processed(package_id, len(merged))
    print(f"\n✅ Done — package {package_id}, {len(merged)} items stored")
    return package_id


def _check_ocrmypdf():
    try:
        subprocess.run(["ocrmypdf", "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ── Auto-scrape with Playwright ───────────────────────────────────────────────

def scrape_and_download(visible=False):
    """Use Playwright to find new PDFs on the personal papers page.

    Returns list of (local_path, source_url) tuples for newly downloaded files.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    db.init_db()
    downloaded = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not visible)
        page = browser.new_page()
        print(f"🌐 Loading {SOURCE_URL} ...")
        page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page.content(), "html.parser")
        browser.close()

    # Collect PDF links
    pdf_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href:
            continue
        # Normalise relative URLs
        if href.startswith("/"):
            href = "https://citycouncil.atlantaga.gov" + href
        # Accept document viewer links or direct .pdf links
        if "showpublisheddocument" in href.lower() or href.lower().endswith(".pdf"):
            text = a.get_text(strip=True)
            if text:
                pdf_links.append((href, text))

    print(f"   Found {len(pdf_links)} PDF link(s)")

    import requests
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    for url, link_text in pdf_links:
        if db.url_already_downloaded(url):
            print(f"   ↩  Already downloaded: {link_text[:60]}")
            continue

        # Derive a filename from the link text or URL
        slug = re.sub(r"[^\w\s-]", "", link_text)[:60].strip()
        slug = re.sub(r"\s+", "_", slug)
        filename = f"{slug}.pdf" if slug else "personal_papers.pdf"
        dest = COMBINED_DIR / filename

        print(f"   ⬇  Downloading: {link_text[:60]}")
        try:
            r = requests.get(url, headers=headers, timeout=60, stream=True)
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            downloaded.append((dest, url))
        except Exception as e:
            print(f"   ❌ Download failed: {e}")

    return downloaded


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Process Atlanta City Council Personal Papers PDFs")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pdf",        metavar="PATH", help="Process a local PDF file")
    group.add_argument("--auto",       action="store_true", help="Scrape page and process new PDFs")
    group.add_argument("--reprocess",  metavar="ID", type=int, help="Re-split/re-OCR a package by DB id")
    parser.add_argument("--visible",   action="store_true", help="Show browser window (--auto only)")
    args = parser.parse_args()

    if args.pdf:
        process_pdf(args.pdf)

    elif args.auto:
        new_files = scrape_and_download(visible=args.visible)
        if not new_files:
            print("No new PDFs to process.")
            return
        for local_path, source_url in new_files:
            process_pdf(local_path, source_url=source_url)

    elif args.reprocess:
        pkg = db.get_package(args.reprocess)
        if not pkg:
            print(f"Package {args.reprocess} not found in DB")
            sys.exit(1)
        process_pdf(pkg["pdf_path"], source_url=pkg["source_url"], package_id=args.reprocess)


if __name__ == "__main__":
    main()
