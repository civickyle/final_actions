#!/usr/bin/env python3
"""
Scrape Atlanta City Council news releases.

The site uses bot detection, so we use Playwright with a real browser.
News items are accessed by sequential IDs rather than list pages.

Usage:
    # Scrape news IDs 1-100
    python scrape_news_releases.py --ids 1 100

    # Scrape specific IDs
    python scrape_news_releases.py --ids 50 51 52

    # Update mode (try recent IDs, stop after N consecutive failures)
    python scrape_news_releases.py --update --start 1 --limit 500

    # Show headless browser
    python scrape_news_releases.py --ids 1 10 --visible
"""

import json
import argparse
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup


def scrape_news_by_id(page, news_id):
    """
    Scrape a single news article by ID.

    Args:
        page: Playwright page object
        news_id: News article ID number

    Returns:
        Dict with news content or None if not found
    """
    url = f"https://citycouncil.atlantaga.gov/Home/Components/News/News/{news_id}"

    try:
        # Navigate to the page
        response = page.goto(url, wait_until='domcontentloaded', timeout=15000)

        # Check if page loaded successfully
        if response.status != 200:
            return None

        # Brief wait for dynamic content
        time.sleep(0.2)

        # Get the page content
        content = page.content()
        soup = BeautifulSoup(content, 'html.parser')

        # Check for access denied
        if 'Access Denied' in content:
            print(f"    ⚠️  Access denied for ID {news_id}")
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
            # Get HTML content
            content_html = str(content_elem)
            # Get text content
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

        news_item = {
            'id': news_id,
            'title': title,
            'url': url,
            'date': date_text,
            'content_text': content_text,
            'content_html': content_html,
            'links': links,
            'scraped_at': datetime.now().isoformat()
        }

        print(f"  ✓ ID {news_id}: {title[:60]}... ({date_text})")
        return news_item

    except Exception as e:
        print(f"  ❌ Error scraping ID {news_id}: {e}")
        return None


def load_existing_news():
    """Load existing scraped news from file."""
    news_file = Path('news_releases.json')
    if news_file.exists():
        with open(news_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('news', [])
    return []


def save_news(news_items):
    """Save news items to file."""
    news_file = Path('news_releases.json')

    # Sort by ID
    news_items_sorted = sorted(news_items, key=lambda x: x.get('id', 0))

    data = {
        'last_updated': datetime.now().isoformat(),
        'total_count': len(news_items_sorted),
        'news': news_items_sorted
    }

    with open(news_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved {len(news_items_sorted)} news items to {news_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Scrape Atlanta City Council news releases by ID',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape IDs 1-100
  python scrape_news_releases.py --ids 1 100

  # Scrape specific IDs
  python scrape_news_releases.py --ids 50 51 52

  # Update mode - scrape from start ID until consecutive failures
  python scrape_news_releases.py --update --start 1 --limit 500

  # Show browser window
  python scrape_news_releases.py --ids 1 10 --visible
        """
    )

    parser.add_argument('--ids', type=int, nargs='+',
                       help='Specific news IDs to scrape (single ID, or start end for range)')
    parser.add_argument('--update', action='store_true',
                       help='Update mode: scrape sequentially, stop after failures')
    parser.add_argument('--start', type=int, default=1,
                       help='Starting ID for update mode (default: 1)')
    parser.add_argument('--limit', type=int, default=1000,
                       help='Maximum IDs to try in update mode (default: 1000)')
    parser.add_argument('--max-failures', type=int, default=10,
                       help='Stop after N consecutive failures in update mode (default: 10)')
    parser.add_argument('--visible', action='store_true',
                       help='Show browser window (for debugging)')
    parser.add_argument('--delay', type=float, default=0.2,
                       help='Delay between requests in seconds (default: 0.2)')

    args = parser.parse_args()

    # Determine which IDs to scrape
    if args.ids:
        if len(args.ids) == 2:
            # Range: start and end
            ids_to_scrape = range(args.ids[0], args.ids[1] + 1)
        else:
            # Specific IDs
            ids_to_scrape = args.ids
    elif args.update:
        ids_to_scrape = range(args.start, args.start + args.limit)
    else:
        # Default: scrape first 10
        ids_to_scrape = range(1, 11)

    # Load existing news
    existing_news = load_existing_news()
    existing_ids = {item['id'] for item in existing_news}
    print(f"Loaded {len(existing_news)} existing news items")

    print("="*80)
    print("ATLANTA CITY COUNCIL NEWS SCRAPER")
    print("="*80)
    print(f"Mode: {'UPDATE' if args.update else 'ID RANGE' if len(ids_to_scrape) > 5 else 'SPECIFIC IDS'}")
    print(f"IDs to scrape: {list(ids_to_scrape)[:10]}{'...' if len(list(ids_to_scrape)) > 10 else ''}")
    print(f"Headless: {'No' if args.visible else 'Yes'}")
    print(f"Delay: {args.delay}s")
    print()

    all_news = {item['id']: item for item in existing_news}  # Use dict for faster lookups
    new_count = 0
    updated_count = 0
    consecutive_failures = 0

    with sync_playwright() as p:
        # Launch browser with stealth settings
        browser = p.chromium.launch(
            headless=not args.visible,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080}
        )

        # Add extra headers to look more like a real browser
        context.set_extra_http_headers({
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        })

        page = context.new_page()

        try:
            for news_id in ids_to_scrape:
                # Check if we already have this
                if news_id in existing_ids and not args.update:
                    print(f"  ⏭️  ID {news_id}: Already exists, skipping")
                    continue

                # Scrape the news item
                news_item = scrape_news_by_id(page, news_id)

                if news_item:
                    if news_id in existing_ids:
                        updated_count += 1
                    else:
                        new_count += 1

                    all_news[news_id] = news_item
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    print(f"    ⚠️  ID {news_id}: Not found or error")

                # In update mode, stop after too many consecutive failures
                if args.update and consecutive_failures >= args.max_failures:
                    print(f"\n  Stopped after {args.max_failures} consecutive failures")
                    break

                # Delay between requests
                time.sleep(args.delay)

        finally:
            browser.close()

    print("\n" + "="*80)
    print("SCRAPING COMPLETE")
    print("="*80)
    print(f"Total news items: {len(all_news)}")
    print(f"New items: {new_count}")
    print(f"Updated items: {updated_count}")
    print()

    # Save results
    save_news(list(all_news.values()))

    # Show some examples
    if new_count > 0:
        print("\nRecent new items:")
        sorted_items = sorted(all_news.values(), key=lambda x: x.get('id', 0))
        recent_new = [item for item in sorted_items if item['id'] not in existing_ids][-5:]
        for item in recent_new:
            print(f"  • ID {item['id']}: {item['title'][:70]} ({item['date']})")

    print("\n✅ Done!")


if __name__ == '__main__':
    main()
