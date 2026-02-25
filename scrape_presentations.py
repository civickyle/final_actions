#!/usr/bin/env python3
"""
Scrape presentation file links from Atlanta City Council Finance Executive Committee page.

Usage:
    # Try automated scraping with Playwright:
    python scrape_presentations.py

    # Use manually saved HTML file:
    python scrape_presentations.py --html page.html

    # Specify output file:
    python scrape_presentations.py --output output.json

To manually save the page:
    1. Visit https://citycouncil.atlantaga.gov/standing-committees/finance-executive-committee/presentations
    2. Right-click > Save Page As > "Complete" or "HTML Only"
    3. Run: python scrape_presentations.py --html presentations.html

Requirements:
    pip install playwright beautifulsoup4
    playwright install chromium
"""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import sys
from datetime import datetime
from pathlib import Path
import argparse
import time

# Target URL
FINANCE_PRESENTATIONS_URL = "https://citycouncil.atlantaga.gov/standing-committees/finance-executive-committee/presentations"

def scrape_presentations_from_html(html_content, source_url):
    """
    Parse presentations from HTML content.

    Args:
        html_content: HTML string to parse
        source_url: Original URL (for metadata)

    Returns:
        dict with metadata and list of presentations
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    presentations = []

    # Find all links that point to PDF, PPTX, or other presentation files
    file_extensions = ['.pdf', '.pptx', '.ppt', '.doc', '.docx', '.xlsx', '.xls']

    # Find all links on the page
    links = soup.find_all('a', href=True)

    print(f"Found {len(links)} total links on the page")

    for link in links:
        href = link['href']

        # Check if link is a presentation file
        if any(href.lower().endswith(ext) for ext in file_extensions):
            # Get link text (title/description)
            title = link.get_text(strip=True)

            # Make URL absolute if it's relative
            if href.startswith('/'):
                full_url = f"https://citycouncil.atlantaga.gov{href}"
            elif href.startswith('http'):
                full_url = href
            else:
                full_url = f"https://citycouncil.atlantaga.gov/{href}"

            # Try to extract date from context (parent elements, nearby text, etc.)
            date_context = ""
            parent = link.parent
            if parent:
                date_context = parent.get_text(strip=True)

            # Determine file type
            file_type = None
            for ext in file_extensions:
                if href.lower().endswith(ext):
                    file_type = ext.upper().replace('.', '')
                    break

            presentation = {
                'title': title or '(no title)',
                'url': full_url,
                'file_type': file_type,
                'date_context': date_context[:200] if date_context else '',
                'href': href
            }

            presentations.append(presentation)
            print(f"  Found: {presentation['title'][:60]}... ({file_type})")

    # Also look for any structured content (tables, lists, divs with specific classes)
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            for cell in cells:
                cell_links = cell.find_all('a', href=True)
                for link in cell_links:
                    href = link['href']
                    if any(href.lower().endswith(ext) for ext in file_extensions):
                        # Check if already added
                        if not any(p['href'] == href for p in presentations):
                            title = link.get_text(strip=True)

                            if href.startswith('/'):
                                full_url = f"https://citycouncil.atlantaga.gov{href}"
                            elif href.startswith('http'):
                                full_url = href
                            else:
                                full_url = f"https://citycouncil.atlantaga.gov/{href}"

                            file_type = None
                            for ext in file_extensions:
                                if href.lower().endswith(ext):
                                    file_type = ext.upper().replace('.', '')
                                    break

                            # Get row context for date information
                            row_text = row.get_text(' | ', strip=True)

                            presentation = {
                                'title': title or '(no title)',
                                'url': full_url,
                                'file_type': file_type,
                                'date_context': row_text[:200] if row_text else '',
                                'href': href
                            }

                            presentations.append(presentation)
                            print(f"  Found (table): {presentation['title'][:60]}... ({file_type})")

    result = {
        'scraped_at': datetime.now().isoformat(),
        'source_url': source_url,
        'presentation_count': len(presentations),
        'presentations': presentations
    }

    return result

def scrape_presentations_automated(url, headless=True):
    """
    Try to scrape presentations using Playwright.

    Args:
        url: URL to scrape
        headless: If True, run in headless mode. If False, show browser window.

    Returns:
        HTML content as string, or None if failed
    """
    print(f"Fetching: {url}")
    mode = "headless" if headless else "visible browser"
    print(f"Using Playwright with Chromium ({mode}) to fetch page...")

    try:
        with sync_playwright() as p:
            # Launch browser with options to avoid detection
            browser = p.chromium.launch(
                headless=headless,
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled'
                ]
            )

            # Create context with realistic settings
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York',
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                }
            )

            page = context.new_page()

            # Add additional stealth measures
            page.add_init_script("""
                // Override the navigator.webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });

                // Override plugins to look more realistic
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });

                // Override languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
            """)

            # Navigate to page
            print("Loading page...")
            page.goto(url, wait_until='domcontentloaded', timeout=30000)

            # Wait a bit for any dynamic content
            print("Waiting for dynamic content...")
            time.sleep(2)

            # Get page content
            page_source = page.content()

            # Close browser
            browser.close()

            # Check if we got blocked
            if 'Access Denied' in page_source or len(page_source) < 1000:
                print(f"\n⚠️  Warning: Page appears to be blocked or very small ({len(page_source)} bytes)")
                print("The site's bot protection may be blocking access.")
                return None

            print(f"✓ Successfully fetched page ({len(page_source)} bytes)")
            return page_source

    except Exception as e:
        print(f"Error using Playwright: {e}")
        print("\nMake sure Playwright is installed:")
        print("  pip install playwright")
        print("  playwright install chromium")
        return None

def main():
    parser = argparse.ArgumentParser(
        description='Scrape presentation file links from Atlanta City Council Finance Committee page',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scrape_presentations.py                    # Try automated scraping
  python scrape_presentations.py --html page.html   # Use saved HTML file

To manually save the page:
  1. Visit the URL in your browser
  2. Right-click > Save Page As > "Complete" or "HTML Only"
  3. Run: python scrape_presentations.py --html presentations.html
        """
    )
    parser.add_argument(
        '--output', '-o',
        default='finance_presentations.json',
        help='Output JSON file (default: finance_presentations.json)'
    )
    parser.add_argument(
        '--html',
        help='Path to manually saved HTML file (bypasses automated scraping)'
    )
    parser.add_argument(
        '--url',
        default=FINANCE_PRESENTATIONS_URL,
        help='URL to scrape (default: Finance Committee presentations page)'
    )
    parser.add_argument(
        '--visible',
        action='store_true',
        help='Show browser window during scraping (may help bypass bot detection)'
    )

    args = parser.parse_args()

    print("="*80)
    print("ATLANTA CITY COUNCIL FINANCE COMMITTEE PRESENTATIONS SCRAPER")
    print("="*80)
    print()

    if args.html:
        # Use manually saved HTML file
        html_file = Path(args.html)
        if not html_file.exists():
            print(f"❌ Error: HTML file not found: {html_file}")
            sys.exit(1)

        print(f"Reading HTML from: {html_file}")
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        result = scrape_presentations_from_html(html_content, args.url)
    else:
        # Try automated scraping
        html_content = scrape_presentations_automated(args.url, headless=not args.visible)

        if html_content is None:
            print("\n" + "="*80)
            print("❌ Automated scraping failed due to bot protection.")
            print("="*80)
            print("\nTo scrape manually:")
            print("  1. Visit:", args.url)
            print("  2. Right-click > Save Page As > 'Complete' or 'HTML Only'")
            print("  3. Run: python scrape_presentations.py --html <saved-file>.html")
            print()
            sys.exit(1)

        result = scrape_presentations_from_html(html_content, args.url)

    if result is None:
        print("\n❌ Failed to parse presentations")
        sys.exit(1)

    # Save to JSON file
    output_path = Path(args.output)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print()
    print("="*80)
    print("SCRAPING COMPLETE")
    print("="*80)
    print(f"Scraped at: {result['scraped_at']}")
    print(f"Source URL: {result['source_url']}")
    print(f"Total presentations found: {result['presentation_count']}")
    print(f"Output saved to: {output_path.absolute()}")
    print()

    # Show breakdown by file type
    if result['presentations']:
        print("Breakdown by file type:")
        file_types = {}
        for p in result['presentations']:
            ft = p['file_type'] or 'UNKNOWN'
            file_types[ft] = file_types.get(ft, 0) + 1

        for ft, count in sorted(file_types.items()):
            print(f"  {ft}: {count}")
        print()

        # Show first 5 presentations
        print("First 5 presentations:")
        for i, p in enumerate(result['presentations'][:5], 1):
            print(f"  {i}. {p['title'][:60]}{'...' if len(p['title']) > 60 else ''}")
            print(f"     Type: {p['file_type']}, URL: {p['url']}")

        if len(result['presentations']) > 5:
            print(f"  ... and {len(result['presentations']) - 5} more")
    else:
        print("⚠️  No presentations found. The page structure may have changed,")
        print("    or the HTML doesn't contain direct links to presentation files.")

    print()
    print("✅ Scraping complete!")

if __name__ == '__main__':
    main()
