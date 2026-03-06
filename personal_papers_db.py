#!/usr/bin/env python3
"""
SQLite database module for Personal Papers packages and items.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "personal_papers.db"


def get_conn(db_path=None):
    conn = sqlite3.connect(str(db_path or DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path=None):
    conn = get_conn(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pp_packages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source_url      TEXT,
            meeting_date    TEXT,
            filename        TEXT,
            pdf_path        TEXT,
            toc_pdf_path    TEXT,
            downloaded_at   TEXT DEFAULT (datetime('now')),
            processed_at    TEXT,
            item_count      INTEGER DEFAULT 0,
            notes           TEXT
        );


        CREATE TABLE IF NOT EXISTS pp_items (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            package_id   INTEGER NOT NULL REFERENCES pp_packages(id),
            row_num      INTEGER,
            elms_id      TEXT,
            leg_id       TEXT,
            sponsor      TEXT,
            description  TEXT,
            leg_type     TEXT,
            committee    TEXT,
            page_start   INTEGER,
            page_end     INTEGER,
            pdf_path     TEXT,
            ocr_text     TEXT,
            UNIQUE(package_id, elms_id)
        );

        CREATE INDEX IF NOT EXISTS idx_pp_packages_date ON pp_packages(meeting_date);
        CREATE INDEX IF NOT EXISTS idx_pp_items_package  ON pp_items(package_id);
        CREATE INDEX IF NOT EXISTS idx_pp_items_leg_id   ON pp_items(leg_id);
        CREATE INDEX IF NOT EXISTS idx_pp_items_elms     ON pp_items(elms_id);
    """)
    # Migrate existing DBs
    for col_sql in [
        "ALTER TABLE pp_packages ADD COLUMN toc_pdf_path TEXT",
        "ALTER TABLE pp_packages ADD COLUMN enriched_pdf_path TEXT",
    ]:
        try:
            conn.execute(col_sql)
            conn.commit()
        except Exception:
            pass  # Column already exists
    conn.close()


def insert_package(source_url, meeting_date, filename, pdf_path, notes=None, db_path=None):
    conn = get_conn(db_path)
    cur = conn.execute(
        """INSERT INTO pp_packages (source_url, meeting_date, filename, pdf_path, notes)
           VALUES (?, ?, ?, ?, ?)""",
        (source_url, meeting_date, filename, pdf_path, notes),
    )
    pkg_id = cur.lastrowid
    conn.commit()
    conn.close()
    return pkg_id


def set_toc_pdf_path(package_id, toc_pdf_path, db_path=None):
    conn = get_conn(db_path)
    conn.execute(
        "UPDATE pp_packages SET toc_pdf_path = ? WHERE id = ?",
        (toc_pdf_path, package_id),
    )
    conn.commit()
    conn.close()


def set_enriched_pdf_path(package_id, enriched_pdf_path, db_path=None):
    conn = get_conn(db_path)
    conn.execute(
        "UPDATE pp_packages SET enriched_pdf_path = ? WHERE id = ?",
        (enriched_pdf_path, package_id),
    )
    conn.commit()
    conn.close()


def url_already_downloaded(source_url, db_path=None):
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT id FROM pp_packages WHERE source_url = ?", (source_url,)
    ).fetchone()
    conn.close()
    return row is not None


def insert_item(package_id, row_num, elms_id, leg_id, sponsor, description,
                leg_type, committee, page_start, page_end, pdf_path=None,
                ocr_text=None, db_path=None):
    conn = get_conn(db_path)
    conn.execute(
        """INSERT OR REPLACE INTO pp_items
           (package_id, row_num, elms_id, leg_id, sponsor, description,
            leg_type, committee, page_start, page_end, pdf_path, ocr_text)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (package_id, row_num, elms_id, leg_id, sponsor, description,
         leg_type, committee, page_start, page_end, pdf_path, ocr_text),
    )
    conn.commit()
    conn.close()


def mark_package_processed(package_id, item_count, db_path=None):
    conn = get_conn(db_path)
    conn.execute(
        """UPDATE pp_packages
           SET processed_at = datetime('now'), item_count = ?
           WHERE id = ?""",
        (item_count, package_id),
    )
    conn.commit()
    conn.close()


def get_all_packages(db_path=None):
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM pp_packages ORDER BY meeting_date DESC, id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_package(package_id, db_path=None):
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT * FROM pp_packages WHERE id = ?", (package_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_items(package_id, db_path=None):
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM pp_items WHERE package_id = ? ORDER BY row_num",
        (package_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_item(item_id, db_path=None):
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT * FROM pp_items WHERE id = ?", (item_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
