#!/usr/bin/env python3
"""
Parse settlement and claim information from Atlanta City Council legislation data.

Identifies and extracts structured data from two types of settlements:
1. Individual claim settlements (claimType: "settlement") - e.g., property damage, bodily injury
2. Court litigation settlements ("settlement amount" in description)
"""

import json
import re
import csv
from pathlib import Path
from datetime import datetime

MEETING_DATES_DIR = Path('meeting_dates')
OUTPUT_JSON = Path('settlements.json')
OUTPUT_CSV = Path('settlements.csv')


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_dollar_amount(text):
    """Extract the first dollar amount from text. Returns float or None."""
    m = re.search(r'\$\s*([\d,]+(?:\.\d{2})?)', text)
    if m:
        return float(m.group(1).replace(',', ''))
    return None


def parse_individual_claim(item):
    """
    Parse an individual claim settlement.

    Description format (approximate):
    FOR [DAMAGE_TYPE] ALLEGED TO HAVE BEEN SUSTAINED AS A RESULT OF
    [INCIDENT_TYPE] ON [DATE] AT [LOCATION]. ([DEPT/CODE] - $[AMOUNT])
    #[CLAIM_NUM] CLAIM OF: [CLAIMANT_NAME]; [ADDRESS]
    """
    desc = item.get('description', '')

    result = {
        'settlement_category': 'individual_claim',
        'damage_type':         None,
        'incident_type':       None,
        'incident_date':       None,
        'incident_location':   None,
        'department_code':     None,
        'amount':              None,
        'claim_number':        None,
        'claimant_name':       None,
        'claimant_address':    None,
        'plaintiff':           None,
        'case_number':         None,
        'court':               None,
        'case_name':           None,
    }

    # Damage type: "FOR BODILY INJURY" / "FOR PROPERTY DAMAGE" / "FOR PERSONAL INJURY"
    m = re.search(r'^FOR\s+(.+?)\s+ALLEGED\s+TO\s+HAVE', desc, re.IGNORECASE)
    if m:
        result['damage_type'] = m.group(1).strip().title()

    # Incident type: "AS A RESULT OF A MOTOR VEHICLE ACCIDENT"
    m = re.search(r'AS A RESULT OF (?:A\s+)?(.+?)\s+ON\s+', desc, re.IGNORECASE)
    if m:
        result['incident_type'] = m.group(1).strip().title()

    # Incident date: "ON JANUARY 16, 2013" or "ON 01/16/2013"
    m = re.search(
        r'\bON\s+(\w+ \d{1,2},\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})',
        desc, re.IGNORECASE
    )
    if m:
        raw = m.group(1).strip()
        for fmt in ('%B %d, %Y', '%m/%d/%Y', '%m/%d/%y'):
            try:
                result['incident_date'] = datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
                break
            except ValueError:
                continue
        if result['incident_date'] is None:
            result['incident_date'] = raw  # keep raw if parsing fails

    # Incident location: "AT [LOCATION]." (between "ON [DATE] AT" and ".")
    m = re.search(r'\bAT\s+(.+?)\s*[\.\(]', desc, re.IGNORECASE)
    if m:
        loc = m.group(1).strip()
        # Avoid matching "AT AN UNKNOWN LOCATION" literally
        if loc.upper() != 'AN UNKNOWN LOCATION':
            result['incident_location'] = loc.title()
        else:
            result['incident_location'] = 'Unknown'

    # Department code and amount: "(APD/04 - $1,201.54)" or "(NA/UNK)"
    m = re.search(r'\(([A-Z0-9 /]+)\s*[-–]\s*\$([\d,]+(?:\.\d{2})?)\)', desc)
    if m:
        result['department_code'] = m.group(1).strip()
        result['amount'] = float(m.group(2).replace(',', ''))
    else:
        # Try "(NA/UNK)" with no amount
        m2 = re.search(r'\(([A-Z0-9 /]+)\)', desc)
        if m2:
            result['department_code'] = m2.group(1).strip()

    # Claim number: "#2414"
    m = re.search(r'#(\d+)', desc)
    if m:
        result['claim_number'] = m.group(1)

    # Claimant name and address: "CLAIM OF: Name; Address; City, State Zip"
    m = re.search(r'CLAIM OF\s*:?\s*(.+)', desc, re.IGNORECASE | re.DOTALL)
    if m:
        raw = m.group(1).strip()
        parts = [p.strip() for p in re.split(r'[;,]', raw) if p.strip()]
        if parts:
            result['claimant_name'] = parts[0].title()
        if len(parts) > 1:
            result['claimant_address'] = ', '.join(parts[1:]).strip().title()

    return result


def parse_court_settlement(item):
    """
    Parse a court litigation settlement.

    Description format (approximate):
    A Resolution... Authorizing the Settlement of All Claims Against the City of
    Atlanta in the Case of [PLAINTIFF] V. City of Atlanta, Civil Action File No.
    [CASE_NUM], [COURT], in the Total Amount of $[AMOUNT]; ...
    """
    desc = item.get('description', '')

    result = {
        'settlement_category': 'court_litigation',
        'damage_type':         None,
        'incident_type':       None,
        'incident_date':       None,
        'incident_location':   None,
        'department_code':     None,
        'amount':              None,
        'claim_number':        None,
        'claimant_name':       None,
        'claimant_address':    None,
        'plaintiff':           None,
        'case_number':         None,
        'court':               None,
        'case_name':           None,
    }

    # Plaintiff / case name: "Case of X v. City of Atlanta"
    m = re.search(
        r'[Cc]ase of\s+(.+?)\s+[Vv]\.?\s+[Cc]ity of Atlanta',
        desc, re.IGNORECASE
    )
    if m:
        result['plaintiff'] = m.group(1).strip().title()
        result['case_name'] = f"{result['plaintiff']} v. City of Atlanta"

    # Civil action / case number
    m = re.search(
        r'Civil Action (?:File )?No\.?\s*([A-Z0-9\-]+)',
        desc, re.IGNORECASE
    )
    if m:
        result['case_number'] = m.group(1).strip()

    # Court name - look for known patterns anywhere in description
    court_pattern = re.search(
        r'((?:Superior|State|Magistrate|Civil|Municipal|Federal|U\.?S\.? District|Fulton|DeKalb|Gwinnett|Clayton)\s+'
        r'(?:Court|County Superior Court|County State Court|County Magistrate Court)[^,;\.]*)',
        desc, re.IGNORECASE
    )
    if court_pattern:
        result['court'] = court_pattern.group(1).strip().title()

    # Total settlement amount
    m = re.search(
        r'[Tt]otal (?:Settlement )?[Aa]mount\s*(?:of\s*)?\$?\s*([\d,]+(?:\.\d{2})?)',
        desc
    )
    if m:
        result['amount'] = float(m.group(1).replace(',', ''))
    else:
        result['amount'] = parse_dollar_amount(desc)

    return result


def classify_and_parse(item):
    """
    Determine settlement type and parse accordingly.
    Returns a parsed dict, or None if not a settlement.
    """
    claim_type = item.get('claimType', '').lower()
    desc = (item.get('description') or '').upper()

    is_individual_settlement = (claim_type == 'settlement')
    is_court_settlement = (
        claim_type == '' and 'SETTLEMENT AMOUNT' in desc
    )

    if not (is_individual_settlement or is_court_settlement):
        return None

    # Build common fields
    common = {
        'id':                 item.get('id'),
        'meeting_doc_id':     item.get('meetingDocId'),
        'number':             item.get('number'),
        'legislation_date':   item.get('legislationDate', '')[:10],
        'legislation_type':   item.get('legislationTypeName'),
        'final_action':       item.get('finalAction', ''),
        'pdf_url':            item.get('pdfUrl'),
        'sponsors':           ', '.join(item.get('sponsors') or []),
        'description':        item.get('description', ''),
        'claim_type_raw':     item.get('claimType', ''),
    }

    if is_individual_settlement:
        parsed = parse_individual_claim(item)
    else:
        parsed = parse_court_settlement(item)

    common.update(parsed)
    return common


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def scan_all_meetings():
    settlements = []
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
                settlements.append(parsed)

    return settlements, files_scanned, items_scanned


def write_outputs(settlements):
    # JSON output
    OUTPUT_JSON.write_text(json.dumps(settlements, indent=2, ensure_ascii=False))
    print(f"Wrote {len(settlements)} settlements → {OUTPUT_JSON}")

    # CSV output
    if not settlements:
        return

    fieldnames = [
        'id', 'number', 'legislation_date', 'legislation_type',
        'settlement_category', 'claim_type_raw',
        'damage_type', 'incident_type', 'incident_date', 'incident_location',
        'department_code', 'amount',
        'claim_number', 'claimant_name', 'claimant_address',
        'plaintiff', 'case_name', 'case_number', 'court',
        'final_action', 'sponsors', 'pdf_url', 'description',
    ]

    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(settlements)

    print(f"Wrote {len(settlements)} settlements → {OUTPUT_CSV}")


def print_summary(settlements, files_scanned, items_scanned):
    individual = [s for s in settlements if s['settlement_category'] == 'individual_claim']
    court      = [s for s in settlements if s['settlement_category'] == 'court_litigation']

    individual_amounts = [s['amount'] for s in individual if s['amount']]
    court_amounts      = [s['amount'] for s in court if s['amount']]

    print(f"\n{'='*70}")
    print("SETTLEMENT SCAN SUMMARY")
    print(f"{'='*70}")
    print(f"Files scanned:          {files_scanned:,}")
    print(f"Items scanned:          {items_scanned:,}")
    print(f"Total settlements:      {len(settlements):,}")
    print()
    print(f"Individual claims:      {len(individual):,}")
    if individual_amounts:
        print(f"  With amounts parsed:  {len(individual_amounts):,}")
        print(f"  Total paid:          ${sum(individual_amounts):>14,.2f}")
        print(f"  Average:             ${sum(individual_amounts)/len(individual_amounts):>14,.2f}")
        print(f"  Median:              ${sorted(individual_amounts)[len(individual_amounts)//2]:>14,.2f}")
        print(f"  Max:                 ${max(individual_amounts):>14,.2f}")
    print()
    print(f"Court litigation:       {len(court):,}")
    if court_amounts:
        print(f"  With amounts parsed:  {len(court_amounts):,}")
        print(f"  Total paid:          ${sum(court_amounts):>14,.2f}")
        print(f"  Average:             ${sum(court_amounts)/len(court_amounts):>14,.2f}")
        print(f"  Median:              ${sorted(court_amounts)[len(court_amounts)//2]:>14,.2f}")
        print(f"  Max:                 ${max(court_amounts):>14,.2f}")
    print()

    # Top damage types
    from collections import Counter
    damage_types = Counter(
        s['damage_type'] for s in individual if s['damage_type']
    )
    if damage_types:
        print("Top damage types (individual claims):")
        for dtype, count in damage_types.most_common(10):
            print(f"  {dtype:<45} {count:>5}")
    print(f"{'='*70}\n")


if __name__ == '__main__':
    print("Scanning all meeting files for settlements...")
    settlements, files_scanned, items_scanned = scan_all_meetings()
    write_outputs(settlements)
    print_summary(settlements, files_scanned, items_scanned)
