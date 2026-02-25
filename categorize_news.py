#!/usr/bin/env python3
"""
Categorize news items as News Release or Media Advisory based on content.
"""

import re
from news_db import NewsDatabase


def detect_news_type(content_html):
    """
    Detect if a news item is a News Release or Media Advisory.

    Args:
        content_html: HTML content of the news item

    Returns:
        str: "News Release", "Media Advisory", or "Unknown"
    """
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

    # Check for image alt text indicators
    img_match = re.search(r'<img[^>]*alt="([^"]+)"[^>]*>', content_html, re.IGNORECASE)

    if img_match:
        alt_text = img_match.group(1).lower()

        if 'media advisory' in alt_text:
            return "Media Advisory"
        elif 'news release' in alt_text:
            return "News Release"

    # Fallback: check content text
    if 'media advisory' in content_html.lower():
        return "Media Advisory"
    elif 'news release' in content_html.lower():
        return "News Release"

    return "Unknown"


def main():
    """Categorize all news items in the database."""
    db = NewsDatabase('news_releases.db')

    # Get all news items
    print("Loading all news items...")
    all_news = db.get_all_news(limit=None, include_hidden=True, order_by='id ASC')
    total = len(all_news)

    print(f"Found {total} news items to categorize")
    print()

    # Track statistics
    stats = {
        "News Release": 0,
        "Media Advisory": 0,
        "Unknown": 0
    }

    cursor = db.conn.cursor()

    # Process each item
    for i, item in enumerate(all_news, 1):
        news_id = item['id']
        content_html = item.get('content_html', '')

        # Detect type
        news_type = detect_news_type(content_html)
        stats[news_type] += 1

        # Update database
        cursor.execute('UPDATE news SET type = ? WHERE id = ?', (news_type, news_id))

        # Progress indicator
        if i % 100 == 0:
            print(f"Processed {i}/{total} ({i*100//total}%)")
            db.conn.commit()  # Commit every 100 items

    # Final commit
    db.conn.commit()

    print()
    print("="*60)
    print("CATEGORIZATION COMPLETE")
    print("="*60)
    print(f"News Releases: {stats['News Release']}")
    print(f"Media Advisories: {stats['Media Advisory']}")
    print(f"Unknown: {stats['Unknown']}")
    print()
    print(f"Total: {total}")

    db.close()
    print("✅ Done!")


if __name__ == '__main__':
    main()
