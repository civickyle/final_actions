# Atlanta City Council News Releases Scraper

Scrapes news releases from the Atlanta City Council website using Playwright.

**⚠️ IMPORTANT**: Due to bot detection, this scraper **requires visible browser mode** (`--visible` flag). Headless mode will be blocked by the site.

## Features

- **ID-Based Scraping**: Scrapes news articles by sequential ID numbers
- **Incremental Updates**: Automatically stops after consecutive failures (finds the end)
- **Full Content Extraction**: Complete article text, HTML, and embedded links
- **Deduplication**: Tracks scraped items to avoid re-scraping
- **Smart Failure Handling**: Configurable consecutive failure threshold

## Installation

```bash
pip install playwright beautifulsoup4
python -m playwright install chromium
```

## Important Notes

- ⚠️ **You MUST use `--visible` flag** - the site blocks headless browsers
- Browser window will open and you'll see it navigating - this is normal
- Do not close the browser window while scraping is in progress
- News IDs are sequential integers starting from 1
- Some IDs may be gaps/deleted items (the scraper handles this)

## Usage

### Initial Scrape

```bash
# Scrape news IDs 1-100 (requires visible browser)
python scrape_news_releases.py --ids 1 100 --visible

# Scrape specific IDs
python scrape_news_releases.py --ids 1 5 10 15 --visible
```

### Update Mode (Recommended for Routine Updates)

```bash
# Scrape from ID 1 until 10 consecutive failures
# This automatically finds where the news articles end
python scrape_news_releases.py --update --start 1 --limit 500 --max-failures 10 --visible

# If you know the last scraped ID, start from there
python scrape_news_releases.py --update --start 450 --limit 100 --visible
```

### Custom Delay Between Requests

```bash
# Use 2-second delay (default is 1 second)
python scrape_news_releases.py --ids 1 50 --visible --delay 2.0
```

## Output Format

News items are saved to `news_releases.json`:

```json
{
  "last_updated": "2026-02-16T15:30:00",
  "total_count": 150,
  "news": [
    {
      "id": 1,
      "title": "Event at Levi's® Stadium August 14 and 15",
      "url": "https://citycouncil.atlantaga.gov/Home/Components/News/News/1",
      "date": "08/10/2015 9:03 AM",
      "content_text": "Taylor Swift will be performing...",
      "content_html": "<div class=\"detail-content\">...</div>",
      "links": [
        {
          "text": "www.levisstadium.com",
          "href": "http://www.levisstadium.com"
        }
      ],
      "scraped_at": "2026-02-16T15:30:15"
    }
  ]
}
```

### Fields

- **`id`** - News article ID number
- **`title`** - News release headline
- **`url`** - URL to the article
- **`date`** - Publication date (as shown on site)
- **`content_text`** - Complete article text (plain text)
- **`content_html`** - Complete article HTML
- **`links`** - All links within the article content
- **`scraped_at`** - When this item was scraped

## Routine Update Schedule

For routine monitoring, set up a scheduled task to run updates:

### macOS/Linux (cron)

```bash
# Daily at 6 PM - update from last known position
0 18 * * * cd /path/to/final_actions && python scrape_news_releases.py --update --start 1 --limit 1000 --visible > /dev/null 2>&1
```

Note: Running in visible mode via cron requires X server access. For automated headless operation, you may need to use a virtual display (Xvfb) or accept that some runs may fail due to bot detection.

### Alternative: Manual Weekly Updates

```bash
# Run this weekly to catch up on new releases
python scrape_news_releases.py --update --start 1 --limit 1000 --max-failures 10 --visible
```

## How It Works

1. **ID-Based Access**: News articles are accessed via `/Home/Components/News/News/{ID}`
2. **Sequential Scraping**: Tries IDs in order (1, 2, 3, ...)
3. **HTML Parsing**: Extracts title, date, content, and links using BeautifulSoup
4. **Failure Tracking**: Counts consecutive 404s/errors to detect the end
5. **Deduplication**: Compares IDs against existing data
6. **Storage**: Saves all items sorted by ID to `news_releases.json`

## Troubleshooting

### "Access Denied" or All IDs Failing

**Solution**: Make sure you're using the `--visible` flag. The site blocks headless browsers.

```bash
# ❌ Wrong (will be blocked)
python scrape_news_releases.py --ids 1 100

# ✅ Correct (will work)
python scrape_news_releases.py --ids 1 100 --visible
```

### Browser Opens But Nothing Happens

- Check your internet connection
- Increase the delay: `--delay 2.0`
- The site may be temporarily down

### Too Many Failures

If you're getting many consecutive failures:
- Some ID ranges may have gaps (deleted news)
- Increase `--max-failures` to 15-20 for initial scrapes
- Check a few IDs manually in your web browser to verify they exist

## Finding the Latest News ID

To find where the latest news is:

```bash
# Try recent high IDs to find active range
python scrape_news_releases.py --ids 1000 1050 --visible

# Or use update mode with a high start
python scrape_news_releases.py --update --start 500 --limit 500 --visible
```

## Integration with Web App

To display news releases in the Flask app, add a route in `app.py`:

```python
@app.route('/news')
def news_releases():
    """Display news releases."""
    news_file = Path('news_releases.json')
    if news_file.exists():
        with open(news_file, 'r') as f:
            data = json.load(f)
        # Reverse to show newest first
        news_items = sorted(data['news'], key=lambda x: x['id'], reverse=True)
        return render_template('news.html', news=news_items, total=data['total_count'])
    return render_template('error.html', message='No news releases found')
```

## Performance Notes

- Visible browser mode is slower than headless (unavoidable due to bot detection)
- Default 1-second delay keeps scraping respectful
- Expect ~3600 items/hour with default settings
- For large scrapes (1000+ items), run overnight or in batches

## Limitations

- ❌ Cannot run in fully automated headless mode (bot detection)
- ❌ Requires graphical environment (can't run on headless server without X)
- ❌ Slower than headless scraping
- ✅ Reliable and respectful to the server
- ✅ Gets complete article content
- ✅ Handles gaps in ID sequences gracefully
