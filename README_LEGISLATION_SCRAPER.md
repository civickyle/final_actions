# Legislation Details Scraper

Script to scrape detailed legislation information from the Atlanta City Council IQM2 system.

## What It Does

Fetches and parses the complete details for legislation items from:
```
https://atlantacityga.iqm2.com/Citizens/Detail_LegiFile.aspx?ID={ID}
```

Extracts all content from the `ContentPlaceholder1_pnlMain` element, including:
- Legislation title, number, and status
- Sponsor information (from structured data table)
- Department and category (from structured data table)
- Complete body text from `divBody` (WHEREAS clauses, BE IT RESOLVED sections, etc.)
- Meeting history with voting records
- Attachments and links
- All tables in the content

## Installation

```bash
pip install playwright beautifulsoup4
playwright install chromium
```

## Usage

### Scrape a Single ID

```bash
python scrape_legislation_details.py --id 37530
```

### Scrape Multiple IDs

```bash
python scrape_legislation_details.py --ids 37530 37531 37532
```

### Scrape IDs from a File

Create a text file with one ID per line:

```text
# ids.txt
37530
37531
37532
```

Then run:

```bash
python scrape_legislation_details.py --file ids.txt
```

### Options

- `--id <ID>` - Scrape a single legislation ID
- `--ids <ID1> <ID2> ...` - Scrape multiple IDs
- `--file <file>` - Read IDs from a file (one per line, # for comments)
- `--output <file>` - Output JSON file (default: legislation_details.json)
- `--delay <seconds>` - Delay between requests (default: 1.0 second)
- `--visible` - Show browser window during scraping

### Examples

```bash
# Single ID
python scrape_legislation_details.py --id 37530

# Multiple IDs with custom output
python scrape_legislation_details.py --ids 37530 37531 --output my_data.json

# From file with 2-second delay
python scrape_legislation_details.py --file ids.txt --delay 2

# Show browser window (for debugging)
python scrape_legislation_details.py --id 37530 --visible
```

## Output Format

The script generates a JSON file with this structure:

```json
{
  "scraped_at": "2026-02-16T...",
  "total_ids": 3,
  "successful": 3,
  "failed": 0,
  "results": [
    {
      "id": 37530,
      "url": "https://atlantacityga.iqm2.com/Citizens/Detail_LegiFile.aspx?ID=37530",
      "success": true,
      "scraped_at": "2026-02-16T...",
      "content": {
        "text": "Complete text content...",
        "html": "Full HTML of the content panel...",
        "links": [
          {
            "text": "Printout",
            "href": "/Citizens/FileOpen.aspx?Type=30&ID=427395"
          }
        ],
        "tables": [
          [
            ["Department:", "Office of Research...", "Sponsors:", "..."],
            ["Category:", "Personal Paper", "Functions:", "None Required"]
          ]
        ]
      }
    }
  ]
}
```

### Content Fields

- **`text`** - Plain text extracted from the entire content panel (readable format)
- **`full_text`** - Plain text extracted specifically from `divBody` (WHEREAS/BE IT RESOLVED sections)
- **`full_text_html`** - Cleaned HTML from `divBody` with formatting preserved:
  - Bold spans converted to `<strong>` tags
  - Underlined spans converted to `<u>` tags
  - Strikethrough spans converted to `<s>` tags
  - Font-family and font-size attributes removed
  - All other span tags unwrapped
  - Paragraph and table structure preserved
- **`html`** - Full HTML of the content panel (for detailed parsing)
- **`links`** - All hyperlinks found in the content
- **`tables`** - All tables parsed into arrays
- **`structured_data`** - Key-value pairs extracted from the info table (Department, Sponsors, Category, Functions, etc.)
- **`meeting_history`** - Array of meeting records with dates, groups, votes, comments, and video links to meeting recordings

## Rate Limiting

The script includes a 1-second delay between requests by default to be respectful to the server. You can adjust this with `--delay`.

```bash
# Slower scraping (2 second delay)
python scrape_legislation_details.py --file ids.txt --delay 2

# Faster scraping (0.5 second delay) - use cautiously
python scrape_legislation_details.py --file ids.txt --delay 0.5
```

## Getting Legislation IDs

Legislation IDs can be found in:
1. Your existing `meeting_dates/` JSON files (the `id` field)
2. URLs on the Atlanta City Council website
3. The IQM2 system itself

Example: Extract all IDs from your existing data:

```bash
find meeting_dates -name "*.json" -exec jq -r '.data[].id' {} \; | sort -u > all_ids.txt
```

## Use Cases

1. **Fetch Full Text**: Get the complete body text of resolutions/ordinances
2. **Track Voting History**: Extract detailed voting records for each piece of legislation
3. **Attachment Links**: Collect links to PDF documents and other attachments
4. **Meeting History**: See the complete timeline of how legislation moved through committees
5. **Sponsor Details**: Get detailed sponsor information

## Notes

- The script uses Playwright which launches a real Chrome browser
- It waits for the content to load properly before scraping
- Both successful and failed scrapes are recorded in the output
- The script is respectful to the server with default delays
- All data is saved in JSON format for easy processing

## Troubleshooting

### Playwright Not Installed

```bash
pip install playwright
playwright install chromium
```

### IDs Not Found

Make sure the ID actually exists in the IQM2 system. Try visiting the URL manually first:
```
https://atlantacityga.iqm2.com/Citizens/Detail_LegiFile.aspx?ID=YOUR_ID
```

### Slow Performance

- The script includes delays to be respectful to the server
- Each page load takes 2-3 seconds
- For large batches, consider running overnight

### Content Not Found

If the script reports "Content panel not found", the page structure may have changed or the ID may be invalid.
