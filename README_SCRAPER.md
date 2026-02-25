# Presentations Scraper

Script to scrape presentation file links from the Atlanta City Council Finance Executive Committee presentations page.

## Installation

```bash
pip install beautifulsoup4 selenium undetected-chromedriver setuptools
```

## Usage

### Option 1: Automated Scraping (May be blocked)

```bash
python scrape_presentations.py
```

The script will attempt to bypass bot protection using undetected-chromedriver. However, the site uses Akamai protection which may still block automated access.

### Option 2: Manual HTML Input (Recommended)

Since the site has strong bot protection, the recommended approach is:

1. **Visit the page in your browser:**
   ```
   https://citycouncil.atlantaga.gov/standing-committees/finance-executive-committee/presentations
   ```

2. **Save the page:**
   - Right-click on the page
   - Select "Save Page As" or "Save As"
   - Choose "Webpage, Complete" or "HTML Only"
   - Save as `presentations.html`

3. **Run the scraper with the saved HTML:**
   ```bash
   python scrape_presentations.py --html presentations.html
   ```

### Options

- `--html <file>` - Use manually saved HTML file instead of automated scraping
- `--output <file>` - Specify output JSON file (default: finance_presentations.json)
- `--url <url>` - Specify URL to scrape (default: Finance Committee presentations page)

### Examples

```bash
# Try automated scraping
python scrape_presentations.py

# Use saved HTML file
python scrape_presentations.py --html presentations.html

# Specify custom output file
python scrape_presentations.py --html presentations.html --output results.json
```

## Output

The script generates a JSON file with:

```json
{
  "scraped_at": "2026-02-16T...",
  "source_url": "https://...",
  "presentation_count": 42,
  "presentations": [
    {
      "title": "2024 Budget Presentation",
      "url": "https://citycouncil.atlantaga.gov/files/budget.pdf",
      "file_type": "PDF",
      "date_context": "...",
      "href": "/files/budget.pdf"
    },
    ...
  ]
}
```

## Supported File Types

The script looks for links to:
- PDF files (.pdf)
- PowerPoint files (.pptx, .ppt)
- Word documents (.doc, .docx)
- Excel files (.xlsx, .xls)

## Troubleshooting

### "Access Denied" error
The site's bot protection is blocking automated access. Use the manual HTML input method instead.

### ChromeDriver version mismatch
The script tries to auto-detect your Chrome version. If you see version errors, make sure Chrome browser is up to date.

### No presentations found
- The page structure may have changed
- Make sure you saved the complete HTML (not just the page source)
- Check that the page actually contains presentation file links

## Notes

- The site uses Akamai bot protection which makes automated scraping difficult
- Manual HTML input is the most reliable method
- The script looks for direct file links in the HTML
- If presentations are loaded dynamically via JavaScript, they may not be captured in saved HTML
