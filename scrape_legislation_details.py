#!/usr/bin/env python3
"""
Scrape legislation details from Atlanta City Council IQM2 system.

Fetches and parses content from:
https://atlantacityga.iqm2.com/Citizens/Detail_LegiFile.aspx?ID={ID}

Usage:
    # Scrape a single ID:
    python scrape_legislation_details.py --id 12345

    # Scrape multiple IDs:
    python scrape_legislation_details.py --ids 12345 12346 12347

    # Scrape IDs from a file (one ID per line):
    python scrape_legislation_details.py --file ids.txt

    # Scrape with delay between requests:
    python scrape_legislation_details.py --ids 12345 12346 --delay 2

    # Output to specific file:
    python scrape_legislation_details.py --id 12345 --output results.json

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

BASE_URL = "https://atlantacityga.iqm2.com/Citizens/Detail_LegiFile.aspx?ID="

def scrape_legislation_detail(legislation_id, headless=True, delay=1):
    """
    Scrape legislation details for a specific ID.

    Args:
        legislation_id: The legislation ID to scrape
        headless: If True, run browser in headless mode
        delay: Delay in seconds before scraping (to be respectful to server)

    Returns:
        dict with legislation details, or None if failed
    """
    url = f"{BASE_URL}{legislation_id}"
    print(f"Fetching ID {legislation_id}: {url}")

    # Respectful delay
    if delay > 0:
        time.sleep(delay)

    try:
        with sync_playwright() as p:
            # Launch browser
            browser = p.chromium.launch(
                headless=headless,
                args=['--no-sandbox']
            )

            # Create context with realistic settings
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )

            page = context.new_page()

            # Navigate to page
            page.goto(url, wait_until='domcontentloaded', timeout=30000)

            # Wait for the content panel to load
            try:
                page.wait_for_selector('#ContentPlaceholder1_pnlMain', timeout=10000)
            except:
                print(f"  Warning: Content panel not found for ID {legislation_id}")

            # Get page content
            page_source = page.content()

            # Close browser
            browser.close()

            # Parse with BeautifulSoup
            soup = BeautifulSoup(page_source, 'html.parser')

            # Find the main content panel
            content_panel = soup.find(id='ContentPlaceholder1_pnlMain')

            if not content_panel:
                print(f"  ❌ No content found for ID {legislation_id}")
                return {
                    'id': legislation_id,
                    'url': url,
                    'success': False,
                    'error': 'Content panel not found',
                    'scraped_at': datetime.now().isoformat()
                }

            # Extract all text from the content panel
            content_text = content_panel.get_text(separator='\n', strip=True)

            # Extract all links within the content panel
            links = []
            for link in content_panel.find_all('a', href=True):
                links.append({
                    'text': link.get_text(strip=True),
                    'href': link['href']
                })

            # Extract tables if any
            tables = []
            for table in content_panel.find_all('table'):
                rows = []
                for row in table.find_all('tr'):
                    cells = [cell.get_text(strip=True) for cell in row.find_all(['td', 'th'])]
                    if cells:
                        rows.append(cells)
                if rows:
                    tables.append(rows)

            # Parse structured data from tables
            structured_data = {}

            # Find the info table (LegiFileInfo)
            info_table = content_panel.find('table', id='tblLegiFileInfo')
            if info_table:
                for row in info_table.find_all('tr'):
                    cells = row.find_all(['td', 'th'])
                    # Tables usually have pairs of key:value cells
                    for i in range(0, len(cells), 2):
                        if i + 1 < len(cells):
                            key = cells[i].get_text(strip=True).rstrip(':')
                            value = cells[i + 1].get_text(strip=True)
                            if key and value:
                                structured_data[key] = value

            # Extract meeting history data
            meeting_history = []
            history_div = content_panel.find('div', class_='LegiFileSection MeetingHistory')
            if history_div:
                history_table = history_div.find('table', class_='MeetingHistory')
                if history_table:
                    current_meeting = None
                    for row in history_table.find_all('tr'):
                        if 'HeaderRow' in row.get('class', []):
                            # Start of a new meeting
                            if current_meeting:
                                meeting_history.append(current_meeting)

                            date_cell = row.find('td', class_='Date')
                            group_cell = row.find('td', class_='Group')
                            type_cell = row.find('td', class_='Type')

                            # Extract date text and video link if present
                            date_text = date_cell.get_text(strip=True) if date_cell else ''
                            video_link = None
                            if date_cell:
                                # Look for the video link (second anchor with onclick)
                                video_anchors = date_cell.find_all('a')
                                for anchor in video_anchors:
                                    onclick = anchor.get('onclick', '')
                                    if 'SplitView.aspx' in onclick and 'Video' in onclick:
                                        # Extract URL from onclick="OpenWindow('/Citizens/SplitView.aspx?...')"
                                        import re
                                        match = re.search(r'OpenWindow\("([^"]+)"\)', onclick)
                                        if match:
                                            href = match.group(1)
                                            # Make absolute URL if relative
                                            if href.startswith('/'):
                                                video_link = f'https://atlantacityga.iqm2.com{href}'
                                            else:
                                                video_link = href
                                            break
                                # Remove 'Video' text from date if it's there
                                date_text = date_text.replace('Video', '').strip()

                            current_meeting = {
                                'date': date_text,
                                'group': group_cell.get_text(strip=True) if group_cell else '',
                                'type': type_cell.get_text(strip=True) if type_cell else '',
                                'video_link': video_link,
                                'votes': {},
                                'comments': ''
                            }
                        elif 'VoteResultRow' in row.get('class', []) and current_meeting:
                            # Extract vote data
                            comments_div = row.find('div', class_='Comments')
                            if comments_div:
                                current_meeting['comments'] = comments_div.get_text('\n', strip=True)

                            vote_table = row.find('table', class_='VoteRecord')
                            if vote_table:
                                for vote_row in vote_table.find_all('tr'):
                                    cells = vote_row.find_all('td')
                                    if len(cells) >= 2:
                                        role = cells[0].get_text(strip=True).rstrip(':')
                                        value = cells[1].get_text(strip=True)
                                        if role and value:
                                            current_meeting['votes'][role] = value

                    # Add the last meeting
                    if current_meeting:
                        meeting_history.append(current_meeting)

            # Extract full text from divBody if available
            full_text = ''
            full_text_html = ''
            div_body = content_panel.find('div', id='divBody')
            if div_body:
                # Create a copy to process
                from copy import copy
                import re
                body_copy = BeautifulSoup(str(div_body), 'html.parser')

                # Process span tags: convert bold ones to <strong>, unwrap others
                for span in body_copy.find_all('span'):
                    style = span.get('style', '')

                    # Check if this span is bold
                    is_bold = 'font-weight:bold' in style or 'font-weight: bold' in style
                    is_underline = 'text-decoration:underline' in style or 'text-decoration: underline' in style
                    is_strikethrough = 'text-decoration:line-through' in style or 'text-decoration: line-through' in style

                    if is_bold:
                        # Replace span with strong tag
                        span.name = 'strong'
                        if span.has_attr('style'):
                            del span['style']
                        if span.has_attr('class'):
                            del span['class']
                    elif is_underline:
                        # Replace span with u tag
                        span.name = 'u'
                        if span.has_attr('style'):
                            del span['style']
                        if span.has_attr('class'):
                            del span['class']
                    elif is_strikethrough:
                        # Replace span with s tag
                        span.name = 's'
                        if span.has_attr('style'):
                            del span['style']
                        if span.has_attr('class'):
                            del span['class']
                    else:
                        # Remove span but keep content
                        span.unwrap()

                # Remove style and class attributes from remaining tags
                for tag in body_copy.find_all(True):
                    if tag.has_attr('style'):
                        del tag['style']
                    if tag.has_attr('class'):
                        del tag['class']

                # Get HTML with only allowed formatting tags
                full_text_html = str(body_copy.find('div', id='divBody'))
                if full_text_html:
                    # Remove the outer div wrapper
                    full_text_html = full_text_html.replace('<div id="divBody">', '').replace('</div>', '', 1).strip()

                # Also keep plain text version
                full_text = div_body.get_text(separator='\n', strip=True)

            # Get the HTML content as well for more detailed parsing later
            content_html = str(content_panel)

            result = {
                'id': legislation_id,
                'url': url,
                'success': True,
                'scraped_at': datetime.now().isoformat(),
                'content': {
                    'text': content_text,
                    'html': content_html,
                    'links': links,
                    'tables': tables,
                    'structured_data': structured_data,
                    'meeting_history': meeting_history,
                    'full_text': full_text,
                    'full_text_html': full_text_html
                }
            }

            print(f"  ✓ Successfully scraped ID {legislation_id} ({len(content_text)} chars)")
            return result

    except Exception as e:
        print(f"  ❌ Error scraping ID {legislation_id}: {e}")
        return {
            'id': legislation_id,
            'url': url,
            'success': False,
            'error': str(e),
            'scraped_at': datetime.now().isoformat()
        }

def main():
    parser = argparse.ArgumentParser(
        description='Scrape legislation details from Atlanta City Council IQM2 system',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scrape_legislation_details.py --id 12345
  python scrape_legislation_details.py --ids 12345 12346 12347
  python scrape_legislation_details.py --file ids.txt
  python scrape_legislation_details.py --ids 12345 12346 --delay 2
        """
    )
    parser.add_argument(
        '--id',
        type=int,
        help='Single legislation ID to scrape'
    )
    parser.add_argument(
        '--ids',
        type=int,
        nargs='+',
        help='Multiple legislation IDs to scrape'
    )
    parser.add_argument(
        '--file',
        help='File containing legislation IDs (one per line)'
    )
    parser.add_argument(
        '--output', '-o',
        default='legislation_details.json',
        help='Output JSON file (default: legislation_details.json)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=1.0,
        help='Delay between requests in seconds (default: 1.0)'
    )
    parser.add_argument(
        '--visible',
        action='store_true',
        help='Show browser window during scraping'
    )

    args = parser.parse_args()

    # Collect all IDs to scrape
    ids_to_scrape = []

    if args.id:
        ids_to_scrape.append(args.id)

    if args.ids:
        ids_to_scrape.extend(args.ids)

    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"❌ Error: File not found: {file_path}")
            sys.exit(1)

        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    try:
                        ids_to_scrape.append(int(line))
                    except ValueError:
                        print(f"⚠️  Warning: Skipping invalid ID: {line}")

    if not ids_to_scrape:
        print("❌ Error: No IDs specified. Use --id, --ids, or --file")
        parser.print_help()
        sys.exit(1)

    # Remove duplicates and sort
    ids_to_scrape = sorted(set(ids_to_scrape))

    print("="*80)
    print("ATLANTA CITY COUNCIL LEGISLATION DETAILS SCRAPER")
    print("="*80)
    print(f"IDs to scrape: {len(ids_to_scrape)}")
    print(f"Delay between requests: {args.delay}s")
    print(f"Output file: {args.output}")
    print()

    # Scrape all IDs
    results = []
    success_count = 0
    fail_count = 0

    for i, legislation_id in enumerate(ids_to_scrape, 1):
        print(f"[{i}/{len(ids_to_scrape)}] ", end='')
        result = scrape_legislation_detail(
            legislation_id,
            headless=not args.visible,
            delay=args.delay if i > 1 else 0  # No delay for first request
        )
        results.append(result)

        if result['success']:
            success_count += 1
        else:
            fail_count += 1

    # Save results
    output_path = Path(args.output)
    output_data = {
        'scraped_at': datetime.now().isoformat(),
        'total_ids': len(ids_to_scrape),
        'successful': success_count,
        'failed': fail_count,
        'results': results
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print()
    print("="*80)
    print("SCRAPING COMPLETE")
    print("="*80)
    print(f"Total IDs processed: {len(ids_to_scrape)}")
    print(f"✓ Successful: {success_count}")
    print(f"✗ Failed: {fail_count}")
    print(f"Output saved to: {output_path.absolute()}")
    print()

    # Show first successful result as example
    successful_results = [r for r in results if r['success']]
    if successful_results:
        first = successful_results[0]
        print("Example (first successful result):")
        print(f"  ID: {first['id']}")
        print(f"  URL: {first['url']}")
        print(f"  Content length: {len(first['content']['text'])} chars")
        print(f"  Links found: {len(first['content']['links'])}")
        print(f"  Tables found: {len(first['content']['tables'])}")
        print()
        print("  First 200 characters of text:")
        print(f"    {first['content']['text'][:200]}...")
        print()

    if fail_count > 0:
        print(f"⚠️  {fail_count} ID(s) failed. Check the output file for details.")

    print("✅ Scraping complete!")

if __name__ == '__main__':
    main()
