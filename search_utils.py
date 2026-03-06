"""Shared search query normalization for all search types."""


def prepare_fts_query(query: str) -> str:
    """Normalize a query for SQLite FTS5 MATCH.

    Supports full FTS5 syntax: "exact phrase", word*, -exclude, AND/OR/NOT.

    - Curly double quotes → straight (so macOS autocorrected quotes still work
      as FTS5 phrase delimiters, e.g. typing "city budget" finds that exact phrase)
    - All apostrophe variants → curly U+2019, because the stored content (scraped
      web text) uses curly apostrophes and FTS5's unicode61 tokenizer treats
      straight apostrophe as a syntax error.
    """
    return (query
            .replace('\u201c', '"').replace('\u201d', '"')        # curly → straight double quotes
            .replace('\u2018', '\u2019').replace("'", '\u2019'))  # all apostrophes → curly


def normalize_text(text: str) -> str:
    """Normalize text for simple substring matching.

    Folds all apostrophe and double-quote variants to ASCII equivalents
    so that straight/curly quotes match each other regardless of source.
    """
    return (text
            .lower()
            .replace('\u2018', "'").replace('\u2019', "'")    # curly apostrophes → straight
            .replace('\u201c', '"').replace('\u201d', '"'))   # curly double quotes → straight


def prepare_simple_query(query: str) -> str:
    """Normalize a query for simple substring (Python `in`) matching.

    Strips surrounding double quotes (treating them as phrase intent, which
    substring matching already satisfies) and normalizes all quote variants
    so searches work regardless of straight vs curly input.
    """
    q = normalize_text(query).strip()
    # Strip surrounding double quotes — substring match is already a phrase match
    if q.startswith('"') and q.endswith('"') and len(q) > 2:
        q = q[1:-1].strip()
    return q
