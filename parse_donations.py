#!/usr/bin/env python3
"""
Parse donation information from Atlanta City Council legislation data.

Identifies and extracts structured data from two types of donations:
1. Accepted donations (donation_direction: "accepted") - City receives cash/property/in-kind
2. Made/outgoing donations (donation_direction: "made") - City donates cash/property to others

Excludes:
- Easement donations (land donated for road/sewer construction at $1 nominal value)
- Generic "receive donations" authority resolutions with no specific donor or amount
"""

import json
import re
import csv
from pathlib import Path

MEETING_DATES_DIR = Path('meeting_dates')
OUTPUT_JSON = Path('donations.json')
OUTPUT_CSV  = Path('donations.csv')


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

# Patterns that indicate City is ACCEPTING a donation from someone
_ACCEPT_PATTERNS = [
    re.compile(r'\bACCEPT\b.{0,60}\bDONAT', re.IGNORECASE),
    re.compile(r'\bRECEIVE\b.{0,60}\bDONAT', re.IGNORECASE),
    re.compile(r'\bDONAT\b.{0,80}\bON BEHALF OF THE CITY', re.IGNORECASE),
    re.compile(r'\bDONAT\b.{0,80}\bTO THE CITY OF ATLANTA', re.IGNORECASE),
    re.compile(r'\bDONAT\b.{0,80}\bTO THE CITY\b', re.IGNORECASE),
    re.compile(r'\bACCEPTANCE OF.{0,30}\bDONAT', re.IGNORECASE),
]

# Patterns that indicate City is MAKING a donation to someone else
_MADE_PATTERNS = [
    re.compile(r'\bAUTHORIZING A DONATION.{0,60}\bTO\b', re.IGNORECASE),
    re.compile(r'\bAUTHORIZING THE DONATION.{0,60}\bTO\b', re.IGNORECASE),
    re.compile(r'\bCITY.{0,60}\bDONATE.{0,60}\bTO\b', re.IGNORECASE),
    re.compile(r'\bDONATE.{0,80}\bTO\b.{0,80}\bINC\b', re.IGNORECASE),
    re.compile(r'\bDONATE.{0,80}\bTO\b.{0,80}\bASSOCIAT', re.IGNORECASE),
    re.compile(r'\bDONATE.{0,80}\bTO\b.{0,80}\bFOUNDAT', re.IGNORECASE),
    re.compile(r'\bDONATE.{0,80}\bTO\b.{0,80}\bORGANIZAT', re.IGNORECASE),
    re.compile(r'\bDONATE AN AMOUNT', re.IGNORECASE),
    re.compile(r'\bDONATION.{0,30}NOT TO EXCEED.{0,60}\bTO\b', re.IGNORECASE),
]

# Patterns to skip (not real donations)
_SKIP_PATTERNS = [
    # Easement donations (land for infrastructure, nominal $1)
    re.compile(r'\bEASEMENT\b.{0,80}\bDONAT', re.IGNORECASE),
    re.compile(r'\bDONAT.{0,80}\bEASEMENT\b', re.IGNORECASE),
    # Right-of-way donations
    re.compile(r'\bRIGHT.OF.WAY\b.{0,60}\bDONAT', re.IGNORECASE),
    # Reconveyance of donated property (returning previously donated property)
    re.compile(r'\bRECONVEYANCE OF DONATED', re.IGNORECASE),
    # Surplus food program
    re.compile(r'\bDONATED SURPLUS FOOD', re.IGNORECASE),
    # Generic ongoing authority with no specific donor/amount
    re.compile(r'\bCOLLECT DONATIONS FROM ORGANIZATIONS AND INDIVIDUALS', re.IGNORECASE),
]


def classify_donation(item):
    """
    Return 'accepted', 'made', or None.
    """
    desc = item.get('description') or ''
    if not desc:
        return None
    if 'donat' not in desc.lower():
        return None

    # Skip non-donation items
    for pat in _SKIP_PATTERNS:
        if pat.search(desc):
            return None

    is_accepted = any(p.search(desc) for p in _ACCEPT_PATTERNS)
    is_made     = any(p.search(desc) for p in _MADE_PATTERNS)

    if is_accepted and not is_made:
        return 'accepted'
    if is_made and not is_accepted:
        return 'made'
    if is_made and is_accepted:
        # Ambiguous — prefer 'made' if "AUTHORIZING A DONATION ... TO" is explicit
        if re.search(r'AUTHORIZING.{0,30}DONATION.{0,60}TO\b', desc, re.IGNORECASE):
            return 'made'
        return 'accepted'
    return None


# ---------------------------------------------------------------------------
# Amount parsing
# ---------------------------------------------------------------------------

def parse_dollar_amount(text):
    """Extract dollar amount — tries 'not to exceed', then total, then first."""
    def to_float(s):
        s = s.replace(',', '').strip()
        return float(s) if s else None

    # "not to exceed $X"
    m = re.search(r'NOT TO EXCEED\s*\$?\s*([\d,]+(?:\.\d{2})?)', text, re.IGNORECASE)
    if m:
        v = to_float(m.group(1)); return v if v else None
    # "in the amount of $X" / "totaling $X" / "amount of $X"
    m = re.search(r'(?:AMOUNT OF|TOTALING|TOTAL OF|TOTAL AMOUNT OF)\s*\$?\s*([\d,]+(?:\.\d{2})?)', text, re.IGNORECASE)
    if m:
        v = to_float(m.group(1)); return v if v else None
    # "$X,XXX.XX"
    m = re.search(r'\$\s*([\d,]+(?:\.\d{2})?)', text)
    if m:
        v = to_float(m.group(1)); return v if v else None
    return None


def parse_written_amount(text):
    """Parse written dollar amounts like 'FIFTEEN THOUSAND DOLLARS ($15,000.00)'."""
    # Written amounts usually appear with parenthetical figure — rely on parse_dollar_amount
    return None


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

_ORG_SUFFIXES = r'(?:INC|LLC|LTD|CORP|CO|COMPANY|FOUNDATION|ASSOCIATION|ASSOC|AUTHORITY|CENTER|CENTRE|FUND|TRUST|COMMISSION|DEPARTMENT|DEPT|UNIVERSITY|COLLEGE|SCHOOL|CHURCH|HOSPITAL|SOCIETY|CLUB|COMMITTEE|ALLIANCE|INSTITUTE|INTERNATIONAL|BANK|GROUP)'

def extract_donor(desc):
    """Extract donor name from accepted-donation descriptions."""
    # "FROM [DONOR] IN THE AMOUNT" / "FROM [DONOR] FOR" / "FROM [DONOR],"
    m = re.search(
        r'\bFROM\s+((?:[A-Z][A-Z&\-\'\.\, ]+?)'
        r'(?:' + _ORG_SUFFIXES + r'\.?)?)'
        r'\s*(?:IN THE AMOUNT|FOR|,|\.|TOTALING|AND|TO PROVIDE|TO FUND)',
        desc, re.IGNORECASE
    )
    if m:
        name = m.group(1).strip().rstrip(',. ')
        # Remove leading articles
        name = re.sub(r'^(?:THE|A|AN)\s+', '', name, flags=re.IGNORECASE)
        return name.title() if len(name) > 2 else None

    # "A DONATION OF [ITEM] FROM [DONOR]"
    m = re.search(
        r'\bFROM\s+((?:[A-Z][A-Z&\-\'\.\, ]+?)(?:' + _ORG_SUFFIXES + r'\.?)?)'
        r'\s*(?:FOR|,|\.|\s*$)',
        desc, re.IGNORECASE
    )
    if m:
        name = m.group(1).strip().rstrip(',. ')
        name = re.sub(r'^(?:THE|A|AN)\s+', '', name, flags=re.IGNORECASE)
        return name.title() if len(name) > 2 else None

    return None


def extract_recipient(desc):
    """Extract recipient from made-donation descriptions."""
    # "DONATION ... TO [RECIPIENT] FOR" / "DONATE TO [RECIPIENT],"
    m = re.search(
        r'\bTO\s+((?:[A-Z][A-Z&\-\'\.\, ]+?)(?:' + _ORG_SUFFIXES + r'\.?)?)'
        r'\s*(?:FOR|,|\.|ON BEHALF|IN ORDER|TO PROVIDE|\s*$)',
        desc, re.IGNORECASE
    )
    if m:
        name = m.group(1).strip().rstrip(',. ')
        name = re.sub(r'^(?:THE|A|AN)\s+', '', name, flags=re.IGNORECASE)
        # Skip short fragments / prepositions
        if len(name) < 3 or name.upper() in ('THE CITY', 'CITY OF ATLANTA', 'CITY', 'ATLANTA'):
            return None
        return name.title()
    return None


def extract_purpose(desc):
    """Extract what the donation is for."""
    # "FOR THE PURPOSE OF [PURPOSE]" / "FOR [PURPOSE];"
    m = re.search(r'\bFOR THE PURPOSE OF\s+(.+?)(?:\.|;|,\s+(?:AND|SAID|AUTHORIZ))', desc, re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip(';,. ').title()

    m = re.search(r'\bTO BE USED FOR\s+(.+?)(?:\.|;|,)', desc, re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip(';,. ').title()

    # "FOR [purpose phrase]" — pick the first meaningful one
    m = re.search(r'\bFOR\s+((?:THE\s+)?(?:SUMMER|PARKS?|PROGRAM|RECREATION|ARTS?|FUND|BENEFIT|SUPPORT|BENEFIT|ENRICH|CAMP|FESTIVAL|FILM|YOUTH|HOMELESS|VIOLENCE|FIRE|MUSIC|COMMUNITY|CHILDREN|CITY|HOUSING|PUBLIC|POLICE|HISTORIC|STREET|CULTURE|GARDEN|TRAIL|SENIOR|VETERAN|HEALTH).+?)(?:\.|;|,| AND FOR)', desc, re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip(';,. ').title()

    return None


def extract_item_donated(desc):
    """For in-kind donations, what was donated (property/equipment/etc)."""
    # "DONATION OF A [ITEM]" / "DONATION OF [ITEMS]"
    m = re.search(r'\bDONATION OF\s+(?:A\s+|AN\s+|THE\s+)?(.+?)\s+(?:FROM\b|TO\b|FOR\b|;|\.|,\s+(?:AND|SAID|AUTHOR))', desc, re.IGNORECASE)
    if m:
        item = m.group(1).strip().rstrip(';,. ')
        # Skip if it's just a dollar amount phrase
        if re.match(r'(?:AN AMOUNT|FUNDS?|\$)', item, re.IGNORECASE):
            return None
        return item.title() if len(item) > 2 else None
    # "DONATE [ITEM] TO"
    m = re.search(r'\bDONATE\s+(?:A\s+|AN\s+|THE\s+)?(.+?)\s+TO\b', desc, re.IGNORECASE)
    if m:
        item = m.group(1).strip()
        if re.match(r'(?:AN AMOUNT|FUNDS?|\$)', item, re.IGNORECASE):
            return None
        return item.title() if len(item) > 2 else None
    return None


# ---------------------------------------------------------------------------
# Parse one item
# ---------------------------------------------------------------------------

_IN_KIND_SIGNALS = re.compile(
    r'\bVALUED AT\b|\bIN[-\s]KIND\b|\bNON[-\s]MONETARY\b',
    re.IGNORECASE,
)


def classify_donation_type(desc, item_donated, amount):
    """Return 'in_kind' or 'monetary'."""
    if item_donated:
        return 'in_kind'
    if _IN_KIND_SIGNALS.search(desc):
        return 'in_kind'
    return 'monetary'


def parse_donation(item, direction):
    desc = item.get('description', '')
    amount = parse_dollar_amount(desc)

    # Always extract item_donated — needed to detect in-kind donations
    # even when a "valued at $X" amount is also present.
    item_donated = extract_item_donated(desc)

    donation_type = classify_donation_type(desc, item_donated, amount)

    result = {
        'donation_direction': direction,
        'donation_type':      donation_type,
        'amount':             amount,
        'donor':              None,
        'recipient':          None,
        'item_donated':       item_donated,
        'purpose':            None,
    }

    if direction == 'accepted':
        result['donor']    = extract_donor(desc)
        result['purpose']  = extract_purpose(desc)
    else:  # made
        result['recipient'] = extract_recipient(desc)
        result['purpose']   = extract_purpose(desc)

    return result


def classify_and_parse(item):
    direction = classify_donation(item)
    if direction is None:
        return None

    common = {
        'id':               item.get('id'),
        'meeting_doc_id':   item.get('meetingDocId'),
        'number':           item.get('number'),
        'legislation_date': item.get('legislationDate', '')[:10],
        'legislation_type': item.get('legislationTypeName'),
        'final_action':     item.get('finalAction', ''),
        'pdf_url':          item.get('pdfUrl'),
        'sponsors':         ', '.join(item.get('sponsors') or []),
        'description':      item.get('description', ''),
    }

    parsed = parse_donation(item, direction)
    common.update(parsed)
    return common


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def scan_all_meetings():
    donations = []
    files_scanned = 0
    items_scanned = 0

    for json_file in sorted(MEETING_DATES_DIR.rglob('*.json')):
        if json_file.name.endswith('.bak'):
            continue
        try:
            data = json.loads(json_file.read_text())
        except Exception:
            continue

        items = data.get('data', [])
        files_scanned += 1
        items_scanned += len(items)

        for item in items:
            parsed = classify_and_parse(item)
            if parsed:
                donations.append(parsed)

    return donations, files_scanned, items_scanned


def write_outputs(donations):
    OUTPUT_JSON.write_text(json.dumps(donations, indent=2, ensure_ascii=False))
    print(f"Wrote {len(donations)} donations → {OUTPUT_JSON}")

    if not donations:
        return

    fieldnames = [
        'id', 'meeting_doc_id', 'number', 'legislation_date', 'legislation_type',
        'donation_direction', 'donation_type', 'amount', 'donor', 'recipient', 'item_donated', 'purpose',
        'final_action', 'sponsors', 'pdf_url', 'description',
    ]
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(donations)
    print(f"Wrote {len(donations)} donations → {OUTPUT_CSV}")


def print_summary(donations, files_scanned, items_scanned):
    accepted = [d for d in donations if d['donation_direction'] == 'accepted']
    made     = [d for d in donations if d['donation_direction'] == 'made']
    acc_amts  = [d['amount'] for d in accepted if d['amount']]
    made_amts = [d['amount'] for d in made     if d['amount']]

    print(f"\n{'='*70}")
    print("DONATION SCAN SUMMARY")
    print(f"{'='*70}")
    print(f"Files scanned:            {files_scanned:,}")
    print(f"Items scanned:            {items_scanned:,}")
    print(f"Total donations found:    {len(donations):,}")
    print()
    print(f"Accepted (City received): {len(accepted):,}")
    if acc_amts:
        print(f"  With amounts parsed:  {len(acc_amts):,}")
        print(f"  Total received:      ${sum(acc_amts):>14,.2f}")
        print(f"  Average:             ${sum(acc_amts)/len(acc_amts):>14,.2f}")
        print(f"  Max:                 ${max(acc_amts):>14,.2f}")
    print()
    print(f"Made (City donated):      {len(made):,}")
    if made_amts:
        print(f"  With amounts parsed:  {len(made_amts):,}")
        print(f"  Total donated:       ${sum(made_amts):>14,.2f}")
        print(f"  Average:             ${sum(made_amts)/len(made_amts):>14,.2f}")
        print(f"  Max:                 ${max(made_amts):>14,.2f}")
    print()

    # Top donors
    from collections import Counter
    donors = Counter(d['donor'] for d in accepted if d['donor'])
    if donors:
        print("Top donors to City (by # of donations):")
        for name, count in donors.most_common(15):
            print(f"  {name:<50} {count:>4}")
    print()

    # Top recipients
    recipients = Counter(d['recipient'] for d in made if d['recipient'])
    if recipients:
        print("Top recipients of City donations (by # of donations):")
        for name, count in recipients.most_common(15):
            print(f"  {name:<50} {count:>4}")
    print(f"{'='*70}\n")


if __name__ == '__main__':
    print("Scanning all meeting files for donations...")
    donations, files_scanned, items_scanned = scan_all_meetings()
    write_outputs(donations)
    print_summary(donations, files_scanned, items_scanned)
