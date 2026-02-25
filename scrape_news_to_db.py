#!/usr/bin/env python3
"""
Scrape Atlanta City Council news releases directly to database.

This version saves each item to the database immediately, so progress
is preserved even if the scraper is interrupted.
"""

import argparse
import time
import re
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from news_db import NewsDatabase


def detect_news_type(content_html):
    """Detect if item is News Release or Media Advisory from HTML."""
    if not content_html:
        return "Unknown"

    # News Release image signature (first 100 chars of base64 data)
    NEWS_RELEASE_IMG_SIG = "iVBORw0KGgoAAAANSUhEUgAAA88AAAD0CAYAAACl3hQwAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAAFxEAABcR"

    # Media Advisory image signature (first 100 chars of base64 data)
    MEDIA_ADVISORY_IMG_SIG = "iVBORw0KGgoAAAANSUhEUgAAA88AAAD1CAYAAABugseVAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAAFxEAABcR"

    # Check for specific News Release image by base64 signature
    if NEWS_RELEASE_IMG_SIG in content_html:
        return "News Release"

    # Check for specific Media Advisory image by base64 signature
    if MEDIA_ADVISORY_IMG_SIG in content_html:
        return "Media Advisory"

    # Check for image alt text
    img_match = re.search(r'<img[^>]*alt="([^"]+)"[^>]*>', content_html, re.IGNORECASE)
    if img_match:
        alt_text = img_match.group(1).lower()
        if 'media advisory' in alt_text:
            return "Media Advisory"
        elif 'news release' in alt_text:
            return "News Release"

    # Fallback: check content text
    content_lower = content_html.lower()
    if 'media advisory' in content_lower:
        return "Media Advisory"
    elif 'news release' in content_lower:
        return "News Release"

    return "Unknown"


def scrape_news_by_id(page, news_id):
    """
    Scrape a single news article by ID.

    Returns:
        Dict with news content or None if not found
    """
    url = f"https://citycouncil.atlantaga.gov/Home/Components/News/News/{news_id}"

    try:
        # Navigate to the page
        response = page.goto(url, wait_until='domcontentloaded', timeout=15000)

        if response.status != 200:
            return None

        # Brief wait for dynamic content
        time.sleep(0.2)

        # Get the page content
        content = page.content()
        soup = BeautifulSoup(content, 'html.parser')

        # Check for access denied
        if 'Access Denied' in content:
            return None

        # Find the news widget
        news_widget = soup.find('div', class_='news_widget')
        if not news_widget:
            return None

        # Extract title
        title_elem = news_widget.find('h2', class_='detail-title')
        title = title_elem.get_text(strip=True) if title_elem else 'No title'

        # Extract date
        date_elem = news_widget.find('span', class_='detail-list-value')
        date_text = date_elem.get_text(strip=True) if date_elem else None

        # Extract content
        content_elem = news_widget.find('div', class_='detail-content')
        if content_elem:
            content_html = str(content_elem)
            content_text = content_elem.get_text(separator='\n', strip=True)

            # Extract links
            links = []
            for link in content_elem.find_all('a', href=True):
                href = link['href']
                if not href.startswith('http'):
                    href = f"https://citycouncil.atlantaga.gov{href}"
                links.append({
                    'text': link.get_text(strip=True),
                    'href': href
                })
        else:
            content_html = ''
            content_text = ''
            links = []

        # Detect type (News Release or Media Advisory)
        news_type = detect_news_type(content_html)

        return {
            'id': news_id,
            'title': title,
            'url': url,
            'date': date_text,
            'content_text': content_text,
            'content_html': content_html,
            'links': links,
            'type': news_type,
            'scraped_at': datetime.now().isoformat()
        }

    except Exception as e:
        print(f"  ❌ Error scraping ID {news_id}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Scrape Atlanta City Council news directly to database'
    )

    parser.add_argument('--start', type=int, required=True,
                       help='Starting ID')
    parser.add_argument('--end', type=int, required=True,
                       help='Ending ID (inclusive)')
    parser.add_argument('--max-failures', type=int, default=10,
                       help='Stop after N consecutive failures (default: 10)')
    parser.add_argument('--visible', action='store_true',
                       help='Show browser window')
    parser.add_argument('--delay', type=float, default=0.2,
                       help='Delay between requests (default: 0.2s)')
    parser.add_argument('--db', default='news_releases.db',
                       help='Database file (default: news_releases.db)')
    parser.add_argument('--batch-commit', type=int, default=10,
                       help='Commit to DB every N items (default: 10)')

    args = parser.parse_args()

    print("="*80)
    print("ATLANTA CITY COUNCIL NEWS SCRAPER (Direct to DB)")
    print("="*80)
    print(f"Range: {args.start} to {args.end}")
    print(f"Database: {args.db}")
    print(f"Visible: {args.visible}")
    print(f"Delay: {args.delay}s")
    print(f"Batch commit: every {args.batch_commit} items")
    print()

    # Connect to database
    db = NewsDatabase(args.db)

    # Get existing IDs to avoid re-scraping
    existing = db.get_all_news(include_hidden=True)
    existing_ids = {item['id'] for item in existing}
    print(f"Found {len(existing_ids)} existing items in database")
    print()

    new_count = 0
    updated_count = 0
    skipped_count = 0
    consecutive_failures = 0
    batch_count = 0

    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(
            headless=not args.visible,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        context.set_extra_http_headers({
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        })

        page = context.new_page()

        try:
            for news_id in range(args.start, args.end + 1):
                # Scrape the item
                news_item = scrape_news_by_id(page, news_id)

                if news_item:
                    # Save directly to database
                    try:
                        cursor = db.conn.cursor()

                        # Check if exists
                        cursor.execute('SELECT id FROM news WHERE id = ?', (news_id,))
                        exists = cursor.fetchone()

                        if exists:
                            # Update existing
                            cursor.execute('''
                                UPDATE news SET
                                    title = ?, url = ?, date = ?,
                                    content_text = ?, content_html = ?,
                                    type = ?, scraped_at = ?, updated_at = CURRENT_TIMESTAMP
                                WHERE id = ?
                            ''', (
                                news_item['title'], news_item['url'], news_item['date'],
                                news_item['content_text'], news_item['content_html'],
                                news_item['type'], news_item['scraped_at'], news_id
                            ))
                            updated_count += 1
                            print(f"  ↻ ID {news_id}: {news_item['title'][:60]}... (updated)")
                        else:
                            # Insert new
                            cursor.execute('''
                                INSERT INTO news (id, title, url, date, content_text, content_html, type, scraped_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                news_id, news_item['title'], news_item['url'],
                                news_item['date'], news_item['content_text'],
                                news_item['content_html'], news_item['type'], news_item['scraped_at']
                            ))
                            new_count += 1
                            print(f"  ✓ ID {news_id}: {news_item['title'][:60]}... [{news_item['type']}]")

                        # Save links
                        cursor.execute('DELETE FROM news_links WHERE news_id = ?', (news_id,))
                        for link in news_item['links']:
                            cursor.execute('''
                                INSERT INTO news_links (news_id, link_text, link_href)
                                VALUES (?, ?, ?)
                            ''', (news_id, link['text'], link['href']))

                        batch_count += 1

                        # Commit every N items
                        if batch_count >= args.batch_commit:
                            db.conn.commit()
                            batch_count = 0
                            print(f"    💾 Committed to database (total: {new_count} new, {updated_count} updated)")

                        consecutive_failures = 0

                    except Exception as e:
                        print(f"  ❌ Database error for ID {news_id}: {e}")
                        consecutive_failures += 1

                else:
                    consecutive_failures += 1
                    print(f"  ⚠️  ID {news_id}: Not found")

                    # Stop if too many failures
                    if consecutive_failures >= args.max_failures:
                        print(f"\n  Stopped after {args.max_failures} consecutive failures")
                        break

                # Delay between requests
                time.sleep(args.delay)

        finally:
            # Final commit
            db.conn.commit()
            browser.close()

    print("\n" + "="*80)
    print("SCRAPING COMPLETE")
    print("="*80)
    print(f"New items: {new_count}")
    print(f"Updated items: {updated_count}")
    print(f"Total in database: {len(db.get_all_news(include_hidden=True))}")
    print()

    db.close()
    print("✅ Done!")


if __name__ == '__main__':
    main()
