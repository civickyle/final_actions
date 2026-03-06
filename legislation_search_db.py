#!/usr/bin/env python3
"""
Full-text search database for OCR-extracted legislation text.

Uses SQLite FTS5 to provide fast full-text search across 71K+ legislation PDFs.
"""

import sqlite3
import json

from search_utils import prepare_fts_query


class LegislationSearchDB:
    """Manage full-text search over OCR-extracted legislation text."""

    def __init__(self, db_path='legislation_fts.db'):
        self.db_path = db_path
        self.conn = None
        self._connect()

    def _connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def init_database(self):
        """Create tables and FTS5 virtual table."""
        cursor = self.conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_number TEXT UNIQUE NOT NULL,
                legislation_number TEXT,
                description TEXT,
                legislation_date TEXT,
                legislation_type TEXT,
                sponsors TEXT,
                pdf_url TEXT,
                text_content TEXT NOT NULL,
                char_count INTEGER,
                final_action TEXT
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_doc_paper ON documents(paper_number)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_doc_date ON documents(legislation_date)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_doc_type ON documents(legislation_type)
        ''')

        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                text_content,
                description,
                content='documents',
                content_rowid='id'
            )
        ''')

        self.conn.commit()

    def rebuild_fts(self):
        """Rebuild the FTS index from the documents table."""
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO documents_fts(documents_fts) VALUES('rebuild')")
        self.conn.commit()

    def insert_document(self, paper_number, text_content, legislation_number=None,
                        description=None, legislation_date=None, legislation_type=None,
                        sponsors=None, pdf_url=None, char_count=None, final_action=None):
        """Insert a single document. Returns True if inserted, False if already exists."""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO documents (paper_number, legislation_number, description,
                    legislation_date, legislation_type, sponsors, pdf_url,
                    text_content, char_count, final_action)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                paper_number, legislation_number, description,
                legislation_date, legislation_type,
                json.dumps(sponsors) if sponsors else None,
                pdf_url, text_content, char_count, final_action
            ))
            return True
        except sqlite3.IntegrityError:
            return False

    def search(self, query, limit=20, offset=0, date_from=None, date_to=None,
               leg_type=None, sort='relevance'):
        """
        Full-text search with snippet extraction.

        sort: 'relevance', 'date_desc', 'date_asc'
        Phrase search: wrap terms in double quotes, e.g. "city budget"
        Returns list of dicts with metadata and highlighted snippet.
        """
        query = prepare_fts_query(query)
        cursor = self.conn.cursor()

        conditions = []
        params = []

        if date_from:
            conditions.append('d.legislation_date >= ?')
            params.append(date_from)
        if date_to:
            conditions.append('d.legislation_date <= ?')
            params.append(date_to)
        if leg_type:
            conditions.append('d.legislation_type = ?')
            params.append(leg_type)

        where_extra = ''
        if conditions:
            where_extra = 'AND ' + ' AND '.join(conditions)

        order_clause = {
            'date_desc': 'd.legislation_date DESC, rank',
            'date_asc': 'd.legislation_date ASC, rank',
        }.get(sort, 'rank')

        # Count total matches
        count_sql = f'''
            SELECT COUNT(*) FROM documents d
            JOIN documents_fts ON d.id = documents_fts.rowid
            WHERE documents_fts MATCH ? {where_extra}
        '''
        cursor.execute(count_sql, [query] + params)
        total_count = cursor.fetchone()[0]

        # Fetch page of results with snippets
        search_sql = f'''
            SELECT d.*,
                snippet(documents_fts, 0, '<mark>', '</mark>', '...', 40) as snippet
            FROM documents d
            JOIN documents_fts ON d.id = documents_fts.rowid
            WHERE documents_fts MATCH ? {where_extra}
            ORDER BY {order_clause}
            LIMIT ? OFFSET ?
        '''
        cursor.execute(search_sql, [query] + params + [limit, offset])
        rows = cursor.fetchall()

        results = []
        for row in rows:
            item = dict(row)
            item.pop('text_content', None)
            if item.get('sponsors'):
                try:
                    item['sponsors'] = json.loads(item['sponsors'])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(item)

        return {'total': total_count, 'results': results}

    def get_stats(self):
        """Get database statistics."""
        cursor = self.conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM documents')
        total = cursor.fetchone()[0]

        cursor.execute('SELECT SUM(char_count) FROM documents')
        total_chars = cursor.fetchone()[0] or 0

        cursor.execute('SELECT MIN(legislation_date), MAX(legislation_date) FROM documents WHERE legislation_date IS NOT NULL')
        min_date, max_date = cursor.fetchone()

        cursor.execute('SELECT COUNT(DISTINCT legislation_type) FROM documents WHERE legislation_type IS NOT NULL')
        type_count = cursor.fetchone()[0]

        return {
            'total_documents': total,
            'total_characters': total_chars,
            'earliest_date': min_date,
            'latest_date': max_date,
            'legislation_type_count': type_count
        }

    def close(self):
        if self.conn:
            self.conn.close()
