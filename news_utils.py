#!/usr/bin/env python3
"""
Utility functions for processing news content.
"""

import re


def strip_boilerplate(content_text):
    """
    Remove standard boilerplate text from news releases.

    Removes:
    - Top header (FOR IMMEDIATE RELEASE, Council Communications, address, date, title repeat)
    - Bottom footer (council member list, learn more section, social media, contact info)

    Returns:
        str: Cleaned content with boilerplate removed
    """
    if not content_text:
        return ""

    cleaned = content_text

    # Remove top boilerplate
    # Pattern: Everything from "FOR IMMEDIATE RELEASE" through date and title
    # Look for: FOR IMMEDIATE RELEASE ... up to first paragraph starting with ATLANTA or WHO: etc
    top_pattern = r'^FOR IMMEDIATE RELEASE.*?(?=\n(?:WHO:|WHAT:|WHEN:|WHERE:|ATLANTA\s*—|ATLANTA\s*–))'
    cleaned = re.sub(top_pattern, '', cleaned, flags=re.DOTALL | re.MULTILINE)

    # Also remove any remaining header elements at the start
    cleaned = re.sub(r'^Council Communications.*?Atlanta, GA.*?\n', '', cleaned, flags=re.DOTALL | re.MULTILINE)

    # Remove bottom boilerplate - multiple approaches to catch different formats
    # 1. Remove council member roster section
    # Pattern: Line containing "12 districts and three at-large" and everything after
    cleaned = re.sub(r'\n[^\n]*?(?:12 districts and three at-large posts|Council is comprised of|Council is composed of).*$', '', cleaned, flags=re.DOTALL | re.MULTILINE)

    # 2. Remove "To learn more" section
    cleaned = re.sub(r'\nTo learn more about the Atlanta City Council.*$', '', cleaned, flags=re.DOTALL | re.MULTILINE)

    # 3. Remove ### and everything after
    cleaned = re.sub(r'\n#{2,}.*$', '', cleaned, flags=re.DOTALL | re.MULTILINE)

    # 4. Remove standalone contact sections
    cleaned = re.sub(r'\n[^\n]*?Office of Council Communications Contact.*$', '', cleaned, flags=re.DOTALL | re.MULTILINE)
    cleaned = re.sub(r'\nContacts?:\s*\n.*$', '', cleaned, flags=re.DOTALL | re.MULTILINE)

    # 5. Remove any remaining council member lists (starts with "Council President:")
    cleaned = re.sub(r'\nCouncil President:.*$', '', cleaned, flags=re.DOTALL | re.MULTILINE)

    # Clean up extra whitespace
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)  # Multiple newlines to double
    cleaned = re.sub(r'^\s+', '', cleaned)  # Leading whitespace
    cleaned = re.sub(r'\s+$', '', cleaned)  # Trailing whitespace

    return cleaned


def get_preview_text(content_text, max_length=300):
    """
    Get preview text with boilerplate removed and truncated.

    Args:
        content_text: Full content text
        max_length: Maximum length of preview

    Returns:
        str: Preview text suitable for listing pages
    """
    # Strip boilerplate first
    cleaned = strip_boilerplate(content_text)

    # Truncate to max_length
    if len(cleaned) <= max_length:
        return cleaned

    # Find a good break point (end of sentence or word)
    truncated = cleaned[:max_length]

    # Try to break at last sentence
    last_period = truncated.rfind('. ')
    if last_period > max_length * 0.6:  # If we have at least 60% of desired length
        return truncated[:last_period + 1]

    # Otherwise break at last word
    last_space = truncated.rfind(' ')
    if last_space > 0:
        return truncated[:last_space] + '...'

    return truncated + '...'


def get_editable_content(content_text):
    """
    Get content suitable for editing (boilerplate removed).

    Args:
        content_text: Full content text

    Returns:
        str: Content with boilerplate removed for editing
    """
    return strip_boilerplate(content_text)
