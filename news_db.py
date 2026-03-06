#!/usr/bin/env python3
"""
Database management for Atlanta City Council news releases.

Creates and manages a SQLite database for efficient news storage and querying.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

from search_utils import prepare_fts_query


class NewsDatabase:
    """Manage news releases in SQLite database."""

    def __init__(self, db_path='news_releases.db'):
        """Initialize database connection."""
        self.db_path = db_path
        self.conn = None
        self.init_database()

    def init_database(self):
        """Create database tables if they don't exist."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row  # Return dict-like rows

        cursor = self.conn.cursor()

        # Create news table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT,
                date TEXT,
                content_text TEXT,
                content_html TEXT,
                scraped_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create links table (one-to-many relationship)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS news_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id INTEGER NOT NULL,
                link_text TEXT,
                link_href TEXT,
                FOREIGN KEY (news_id) REFERENCES news (id) ON DELETE CASCADE
            )
        ''')

        # Add is_hidden and admin_notes columns if they don't exist
        try:
            cursor.execute('ALTER TABLE news ADD COLUMN is_hidden INTEGER DEFAULT 0')
        except:
            pass  # Column already exists

        try:
            cursor.execute('ALTER TABLE news ADD COLUMN admin_notes TEXT')
        except:
            pass  # Column already exists

        # Add type column for categorization (News Release, Media Advisory, etc.)
        try:
            cursor.execute('ALTER TABLE news ADD COLUMN type TEXT DEFAULT "Unknown"')
        except:
            pass  # Column already exists

        # Create indexes for common queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_news_date ON news(date)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_news_title ON news(title)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_news_hidden ON news(is_hidden)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_news_type ON news(type)
        ''')

        # Create full-text search virtual table
        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS news_fts USING fts5(
                title,
                content_text,
                content='news',
                content_rowid='id'
            )
        ''')

        # Create triggers to keep FTS index updated
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS news_fts_insert AFTER INSERT ON news BEGIN
                INSERT INTO news_fts(rowid, title, content_text)
                VALUES (new.id, new.title, new.content_text);
            END
        ''')

        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS news_fts_update AFTER UPDATE ON news BEGIN
                UPDATE news_fts SET title = new.title, content_text = new.content_text
                WHERE rowid = old.id;
            END
        ''')

        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS news_fts_delete AFTER DELETE ON news BEGIN
                DELETE FROM news_fts WHERE rowid = old.id;
            END
        ''')

        self.conn.commit()

    def import_from_json(self, json_file='news_releases.json'):
        """
        Import news from JSON file into database.

        Args:
            json_file: Path to JSON file

        Returns:
            Dict with import statistics
        """
        json_path = Path(json_file)
        if not json_path.exists():
            return {'error': 'JSON file not found'}

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        news_items = data.get('news', [])
        if not news_items:
            return {'error': 'No news items in JSON'}

        cursor = self.conn.cursor()
        imported = 0
        updated = 0
        skipped = 0

        for item in news_items:
            news_id = item.get('id')
            if not news_id:
                skipped += 1
                continue

            # Check if news already exists
            cursor.execute('SELECT id FROM news WHERE id = ?', (news_id,))
            exists = cursor.fetchone()

            if exists:
                # Update existing
                cursor.execute('''
                    UPDATE news SET
                        title = ?,
                        url = ?,
                        date = ?,
                        content_text = ?,
                        content_html = ?,
                        scraped_at = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (
                    item.get('title'),
                    item.get('url'),
                    item.get('date'),
                    item.get('content_text'),
                    item.get('content_html'),
                    item.get('scraped_at'),
                    news_id
                ))
                updated += 1
            else:
                # Insert new
                cursor.execute('''
                    INSERT INTO news (id, title, url, date, content_text, content_html, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    news_id,
                    item.get('title'),
                    item.get('url'),
                    item.get('date'),
                    item.get('content_text'),
                    item.get('content_html'),
                    item.get('scraped_at')
                ))
                imported += 1

            # Delete old links and insert new ones
            cursor.execute('DELETE FROM news_links WHERE news_id = ?', (news_id,))
            for link in item.get('links', []):
                cursor.execute('''
                    INSERT INTO news_links (news_id, link_text, link_href)
                    VALUES (?, ?, ?)
                ''', (news_id, link.get('text'), link.get('href')))

        self.conn.commit()

        return {
            'imported': imported,
            'updated': updated,
            'skipped': skipped,
            'total': len(news_items)
        }

    def get_all_news(self, limit=None, offset=0, order_by='id DESC', include_hidden=False, news_type=None):
        """
        Get all news items.

        Args:
            limit: Maximum number of items to return
            offset: Number of items to skip
            order_by: SQL ORDER BY clause
            include_hidden: If False, filter out hidden items (default: False)
            news_type: Filter by type ("News Release", "Media Advisory", or None for all)

        Returns:
            List of news items as dicts
        """
        cursor = self.conn.cursor()

        # Build WHERE clause
        conditions = []
        if not include_hidden:
            conditions.append('(is_hidden IS NULL OR is_hidden = 0)')
        if news_type:
            conditions.append(f'type = "{news_type}"')

        where_clause = 'WHERE ' + ' AND '.join(conditions) if conditions else ''
        query = f'SELECT * FROM news {where_clause} ORDER BY {order_by}'
        if limit:
            query += f' LIMIT {limit} OFFSET {offset}'

        cursor.execute(query)
        rows = cursor.fetchall()

        # Convert to list of dicts with links
        results = []
        for row in rows:
            item = dict(row)
            # Get links for this news item
            cursor.execute('SELECT link_text, link_href FROM news_links WHERE news_id = ?', (item['id'],))
            item['links'] = [{'text': r[0], 'href': r[1]} for r in cursor.fetchall()]
            results.append(item)

        return results

    def get_news_by_id(self, news_id):
        """Get a single news item by ID."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM news WHERE id = ?', (news_id,))
        row = cursor.fetchone()

        if not row:
            return None

        item = dict(row)
        # Get links
        cursor.execute('SELECT link_text, link_href FROM news_links WHERE news_id = ?', (news_id,))
        item['links'] = [{'text': r[0], 'href': r[1]} for r in cursor.fetchall()]

        return item

    def search_news(self, query, limit=50, include_hidden=False):
        """
        Full-text search across news titles and content.

        Args:
            query: Search query string
            limit: Maximum results
            include_hidden: If False, filter out hidden items (default: False)

        Returns:
            List of matching news items
        """
        cursor = self.conn.cursor()

        query = prepare_fts_query(query)

        hidden_filter = 'AND (news.is_hidden IS NULL OR news.is_hidden = 0)' if not include_hidden else ''

        cursor.execute(f'''
            SELECT news.* FROM news
            JOIN news_fts ON news.id = news_fts.rowid
            WHERE news_fts MATCH ? {hidden_filter}
            ORDER BY rank
            LIMIT ?
        ''', (query, limit))

        rows = cursor.fetchall()

        results = []
        for row in rows:
            item = dict(row)
            cursor.execute('SELECT link_text, link_href FROM news_links WHERE news_id = ?', (item['id'],))
            item['links'] = [{'text': r[0], 'href': r[1]} for r in cursor.fetchall()]
            results.append(item)

        return results

    def update_news(self, news_id, title=None, content_text=None, content_html=None, admin_notes=None):
        """
        Update a news item.

        Args:
            news_id: News ID to update
            title: New title (optional)
            content_text: New plain text content (optional)
            content_html: New HTML content (optional)
            admin_notes: Admin notes (optional)

        Returns:
            True if successful, False otherwise
        """
        cursor = self.conn.cursor()

        # Build update query dynamically based on provided fields
        updates = []
        params = []

        if title is not None:
            updates.append('title = ?')
            params.append(title)

        if content_text is not None:
            updates.append('content_text = ?')
            params.append(content_text)

        if content_html is not None:
            updates.append('content_html = ?')
            params.append(content_html)

        if admin_notes is not None:
            updates.append('admin_notes = ?')
            params.append(admin_notes)

        if not updates:
            return False

        updates.append('updated_at = CURRENT_TIMESTAMP')
        params.append(news_id)

        query = f"UPDATE news SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, params)
        self.conn.commit()

        return cursor.rowcount > 0

    def toggle_hidden(self, news_id):
        """
        Toggle the hidden status of a news item.

        Args:
            news_id: News ID to toggle

        Returns:
            New hidden status (0 or 1), or None if item not found
        """
        cursor = self.conn.cursor()

        # Get current status
        cursor.execute('SELECT is_hidden FROM news WHERE id = ?', (news_id,))
        row = cursor.fetchone()

        if not row:
            return None

        current_status = row[0] if row[0] is not None else 0
        new_status = 0 if current_status else 1

        cursor.execute('UPDATE news SET is_hidden = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                      (new_status, news_id))
        self.conn.commit()

        return new_status

    def set_hidden(self, news_id, is_hidden):
        """
        Set the hidden status of a news item.

        Args:
            news_id: News ID
            is_hidden: True to hide, False to show

        Returns:
            True if successful, False otherwise
        """
        cursor = self.conn.cursor()
        cursor.execute('UPDATE news SET is_hidden = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                      (1 if is_hidden else 0, news_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_news_by_date_range(self, start_date=None, end_date=None, limit=None):
        """
        Get news within a date range.

        Note: Dates in the database are strings like "08/10/2015 9:03 AM"
        This does simple string comparison which works for same format dates.

        Args:
            start_date: Start date string
            end_date: End date string
            limit: Maximum results

        Returns:
            List of news items
        """
        cursor = self.conn.cursor()

        conditions = []
        params = []

        if start_date:
            conditions.append('date >= ?')
            params.append(start_date)

        if end_date:
            conditions.append('date <= ?')
            params.append(end_date)

        where_clause = ' AND '.join(conditions) if conditions else '1=1'
        query = f'SELECT * FROM news WHERE {where_clause} ORDER BY date DESC'

        if limit:
            query += f' LIMIT {limit}'

        cursor.execute(query, params)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            item = dict(row)
            cursor.execute('SELECT link_text, link_href FROM news_links WHERE news_id = ?', (item['id'],))
            item['links'] = [{'text': r[0], 'href': r[1]} for r in cursor.fetchall()]
            results.append(item)

        return results

    def get_stats(self):
        """Get database statistics."""
        cursor = self.conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM news')
        total_news = cursor.fetchone()[0]

        cursor.execute('SELECT MIN(id), MAX(id) FROM news')
        min_id, max_id = cursor.fetchone()

        cursor.execute('SELECT MIN(date), MAX(date) FROM news')
        earliest_date, latest_date = cursor.fetchone()

        return {
            'total_news': total_news,
            'min_id': min_id,
            'max_id': max_id,
            'earliest_date': earliest_date,
            'latest_date': latest_date
        }

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


def main():
    """Command-line interface for database operations."""
    import argparse

    parser = argparse.ArgumentParser(description='Manage news releases database')
    parser.add_argument('--import', dest='import_json', metavar='FILE',
                       help='Import news from JSON file')
    parser.add_argument('--search', metavar='QUERY',
                       help='Search news by text')
    parser.add_argument('--stats', action='store_true',
                       help='Show database statistics')
    parser.add_argument('--list', type=int, metavar='N',
                       help='List N most recent news items')
    parser.add_argument('--db', default='news_releases.db',
                       help='Database file path (default: news_releases.db)')

    args = parser.parse_args()

    db = NewsDatabase(args.db)

    try:
        if args.import_json:
            print(f"Importing from {args.import_json}...")
            stats = db.import_from_json(args.import_json)
            if 'error' in stats:
                print(f"❌ Error: {stats['error']}")
            else:
                print(f"✅ Import complete:")
                print(f"   New items: {stats['imported']}")
                print(f"   Updated items: {stats['updated']}")
                print(f"   Skipped: {stats['skipped']}")
                print(f"   Total processed: {stats['total']}")

        elif args.search:
            print(f"Searching for: {args.search}")
            results = db.search_news(args.search)
            print(f"\nFound {len(results)} results:\n")
            for item in results:
                print(f"  [{item['id']}] {item['title'][:70]}")
                print(f"      Date: {item['date']}")
                print()

        elif args.stats:
            stats = db.get_stats()
            print("Database Statistics:")
            print(f"  Total news items: {stats['total_news']}")
            print(f"  ID range: {stats['min_id']} - {stats['max_id']}")
            print(f"  Date range: {stats['earliest_date']} - {stats['latest_date']}")

        elif args.list:
            items = db.get_all_news(limit=args.list)
            print(f"Most recent {len(items)} news items:\n")
            for item in items:
                print(f"  [{item['id']}] {item['title'][:70]}")
                print(f"      Date: {item['date']}")
                print()

        else:
            parser.print_help()

    finally:
        db.close()


if __name__ == '__main__':
    main()
