#!/usr/bin/env python3
"""
Flask web application to browse and search Atlanta City Council legislation data.
"""

from flask import Flask, render_template, request, jsonify, g, redirect, url_for, send_from_directory, Response
from pathlib import Path
import json
from datetime import datetime
import re
import shutil
import logging
from logging.handlers import RotatingFileHandler
from news_utils import strip_boilerplate, get_preview_text, get_editable_content
from search_utils import normalize_text, prepare_simple_query

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'

@app.after_request
def add_noindex_header(response):
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@app.route('/robots.txt')
def robots():
    return Response("User-agent: *\nDisallow: /\n", mimetype='text/plain')


@app.after_request
def suppress_password_managers(response):
    """Add data-1p-ignore to all inputs to prevent 1Password overlay."""
    if response.content_type and 'text/html' in response.content_type:
        data = response.get_data(as_text=True)
        snippet = '<script>document.querySelectorAll("input").forEach(i=>i.setAttribute("data-1p-ignore",""));new MutationObserver(m=>m.forEach(r=>r.addedNodes.forEach(n=>{if(n.querySelectorAll)n.querySelectorAll("input").forEach(i=>i.setAttribute("data-1p-ignore",""))}))).observe(document.body,{childList:true,subtree:true})</script>'
        data = data.replace('</body>', snippet + '</body>')
        response.set_data(data)
    return response

# Configure logging
if not app.debug:
    # File handler for errors
    file_handler = RotatingFileHandler('logs/error.log', maxBytes=10240000, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.ERROR)
    app.logger.addHandler(file_handler)

# Always log to console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
app.logger.addHandler(console_handler)
app.logger.setLevel(logging.INFO)

# Ensure logs directory exists
Path('logs').mkdir(exist_ok=True)

# Configuration
MEETING_DATES_DIR = Path("meeting_dates")
COUNCILMEMBERS_FILE = Path("councilmembers.json")
COMMITTEES_FILE = Path("committees.json")

def load_all_dates():
    """Load all available dates with data."""
    dates = []
    for json_file in sorted(MEETING_DATES_DIR.rglob("*.json")):
        if '.bak' in json_file.name:
            continue
        date_str = json_file.stem  # e.g., "1984-01-03"
        dates.append(date_str)
    return sorted(dates, reverse=True)  # Most recent first

def find_json_file_by_date(date_str):
    """Find the JSON file path for a specific date."""
    year = date_str.split('-')[0]
    json_file = MEETING_DATES_DIR / year / f"{date_str}.json"

    if json_file.exists():
        return json_file
    return None

def load_data_by_date(date_str):
    """Load legislation data for a specific date."""
    # Find the file
    json_file = find_json_file_by_date(date_str)

    if not json_file:
        return None

    with open(json_file, 'r') as f:
        content = json.load(f)
        return content.get('data', [])

def _normalize_date_from(s):
    """Expand a partial date string to the earliest possible full date."""
    if not s:
        return None
    s = s.strip()
    if re.match(r'^\d{4}$', s):
        return s + '-01-01'
    if re.match(r'^\d{4}-\d{2}$', s):
        return s + '-01'
    return s

def _normalize_date_to(s):
    """Expand a partial date string to the latest possible full date."""
    import calendar
    if not s:
        return None
    s = s.strip()
    if re.match(r'^\d{4}$', s):
        return s + '-12-31'
    if re.match(r'^\d{4}-\d{2}$', s):
        year, month = int(s[:4]), int(s[5:7])
        last_day = calendar.monthrange(year, month)[1]
        return f'{s}-{last_day:02d}'
    return s

def search_all_data(query, search_field='all', leg_type=None, date_from=None, date_to=None, sort_by='date_desc'):
    """
    Search all legislation data.

    Args:
        query: Search query string
        search_field: 'number', 'description', or 'all'
        leg_type: Optional legislation type filter (e.g. 'Resolution', 'Ordinance')
        date_from: Optional start date string 'YYYY-MM-DD' (inclusive)
        date_to:   Optional end date string 'YYYY-MM-DD' (inclusive)
        sort_by:   'date_desc' (default), 'date_asc', or 'relevance'

    Returns:
        List of matching items with date information
    """
    results = []
    q = prepare_simple_query(query)
    leg_type_lower = leg_type.lower() if leg_type else None

    for json_file in MEETING_DATES_DIR.rglob("*.json"):
        date_str = json_file.stem

        # Fast date-range discard on filename (YYYY-MM-DD)
        if date_from and date_str < date_from:
            continue
        if date_to and date_str > date_to:
            continue

        try:
            with open(json_file, 'r') as f:
                content = json.load(f)
                data = content.get('data', [])

                for item in data:
                    # Filter by legislation type first (fast discard)
                    if leg_type_lower:
                        item_type = item.get('legislationTypeName', '').lower()
                        if item_type != leg_type_lower:
                            continue

                    score = 0
                    match = False

                    if search_field in ['number', 'all']:
                        number = normalize_text(item.get('number', ''))
                        if q in number:
                            match = True
                            score += 10 if number == q else 5

                    if search_field in ['description', 'all']:
                        description = normalize_text(item.get('description', ''))
                        count = description.count(q)
                        if count > 0:
                            match = True
                            score += count

                    if match:
                        item_with_date = item.copy()
                        item_with_date['date'] = date_str
                        item_with_date['_score'] = score
                        results.append(item_with_date)
        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            continue

    if sort_by == 'relevance':
        results.sort(key=lambda x: x.get('_score', 0), reverse=True)
    elif sort_by == 'date_asc':
        results.sort(key=lambda x: x.get('date', ''))
    else:  # date_desc
        results.sort(key=lambda x: x.get('date', ''), reverse=True)

    return results

def load_all_sponsors():
    """Load all unique sponsors with their legislation counts."""
    sponsor_counts = {}

    for json_file in MEETING_DATES_DIR.rglob("*.json"):
        try:
            with open(json_file, 'r') as f:
                content = json.load(f)
                data = content.get('data', [])

                for item in data:
                    sponsors = item.get('sponsors', [])
                    for sponsor in sponsors:
                        if sponsor not in sponsor_counts:
                            sponsor_counts[sponsor] = 0
                        sponsor_counts[sponsor] += 1
        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            continue

    # Convert to list of dicts and sort by count
    sponsors_list = [
        {'name': name, 'count': count}
        for name, count in sponsor_counts.items()
    ]
    sponsors_list.sort(key=lambda x: x['count'], reverse=True)

    return sponsors_list

def load_committee_names():
    """Load committee names from committees.json."""
    try:
        if COMMITTEES_FILE.exists():
            with open(COMMITTEES_FILE, 'r') as f:
                data = json.load(f)
                return set(c['name'] for c in data.get('committees', []))
        return set()
    except Exception as e:
        print(f"Error loading committee names: {e}")
        return set()

def load_councilmember_names():
    """Load councilmember names from councilmembers.json."""
    try:
        if COUNCILMEMBERS_FILE.exists():
            with open(COUNCILMEMBERS_FILE, 'r') as f:
                data = json.load(f)
                return set(c['name'] for c in data.get('councilmembers', []))
        return set()
    except Exception as e:
        print(f"Error loading councilmember names: {e}")
        return set()

def classify_paper_type(sponsors, committee_names, councilmember_names):
    """Classify legislation as Committee Paper or Personal Paper."""
    if not sponsors:
        return None

    has_committee = any(s in committee_names for s in sponsors)
    has_councilmember = any(s in councilmember_names for s in sponsors)

    if has_committee and not has_councilmember:
        return "Committee Paper"
    elif has_councilmember and not has_committee:
        return "Personal Paper"
    elif has_committee and has_councilmember:
        return "Mixed"
    else:
        return "Unknown"

def load_data_by_sponsor(sponsor_name):
    """Load all legislation sponsored by a specific councilmember."""
    results = []

    for json_file in MEETING_DATES_DIR.rglob("*.json"):
        date_str = json_file.stem

        try:
            with open(json_file, 'r') as f:
                content = json.load(f)
                data = content.get('data', [])

                for item in data:
                    sponsors = item.get('sponsors', [])
                    if sponsor_name in sponsors:
                        item_with_date = item.copy()
                        item_with_date['date'] = date_str
                        results.append(item_with_date)
        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            continue

    # Sort by date (most recent first)
    results.sort(key=lambda x: x.get('date', ''), reverse=True)

    return results

# Dashboard-specific functions

def calculate_council_terms(min_year=1984, max_year=2026):
    """Calculate 4-year council terms (1982-1985, 1986-1989, ..., 2022-2025, 2026-)."""
    terms = []

    # Terms start in years where (year - 2) % 4 == 0
    # Find the first term start year at or before min_year
    current_start = min_year
    while (current_start - 2) % 4 != 0:
        current_start -= 1

    # Generate terms
    while current_start <= max_year:
        term_end = current_start + 3  # 4-year term (inclusive)
        terms.append({
            'label': f'{current_start}-{term_end}',
            'start': current_start,
            'end': term_end,
            'is_current': current_start <= 2022 <= term_end
        })
        current_start += 4

    return terms

def normalize_final_action(action_text):
    """Normalize final action into categories for aggregation."""
    if not action_text or action_text == "MISSING":
        return "MISSING"

    action_upper = action_text.upper()

    # Categories based on action patterns
    if "ADOPTED SUBSTITUTE AS AMENDED" in action_upper:
        return "ADOPTED_SUBSTITUTE_AMENDED"
    elif "ADOPTED AS AMENDED" in action_upper:
        return "ADOPTED_AMENDED"
    elif "ADOPTED SUBSTITUTE" in action_upper:
        return "ADOPTED_SUBSTITUTE"
    elif "ADOPTED ON CONSENT" in action_upper:
        return "ADOPTED_CONSENT"
    elif "ADOPTED" in action_upper:
        return "ADOPTED"
    elif "ADVERSED" in action_upper:
        return "ADVERSED"
    elif "FILED" in action_upper:
        return "FILED"
    elif "CONFIRMED" in action_upper:
        return "CONFIRMED"
    elif "ACCEPTED" in action_upper:
        return "ACCEPTED"
    else:
        return "OTHER"

def aggregate_legislation_data(start_date=None, end_date=None, group_by='year'):
    """Aggregate legislation across date range with grouping."""
    from collections import defaultdict

    # Initialize aggregation structures
    summary = {'total_items': 0, 'total_meetings': 0}
    final_actions = defaultdict(int)
    legislation_types = defaultdict(int)
    timeline = defaultdict(lambda: {
        'total_items': 0,
        'meetings': 0,
        'actions': defaultdict(int),
        'types': defaultdict(int)
    })

    # Iterate through all JSON files
    for json_file in sorted(MEETING_DATES_DIR.rglob("*.json")):
        if json_file.suffix != '.json' or '.bak' in json_file.name:
            continue

        try:
            # Load and parse
            with open(json_file, 'r') as f:
                meeting_data = json.load(f)

            meeting_date = meeting_data.get('date', '')

            # Apply date filter
            if start_date and meeting_date < start_date:
                continue
            if end_date and meeting_date > end_date:
                continue

            # Determine period key for grouping
            if group_by == 'year':
                period_key = meeting_date[:4]
            elif group_by == 'month':
                period_key = meeting_date[:7]
            elif group_by == 'date':
                period_key = meeting_date
            else:  # term
                period_key = meeting_date[:4]  # Will group by year within term

            summary['total_meetings'] += 1
            if period_key:
                timeline[period_key]['meetings'] += 1

            # Process each item
            for item in meeting_data.get('data', []):
                summary['total_items'] += 1

                # Aggregate final action
                action = normalize_final_action(item.get('finalAction', ''))
                final_actions[action] += 1

                # Aggregate legislation type
                leg_type = item.get('legislationTypeName') or 'Unknown'
                legislation_types[leg_type] += 1

                # Add to timeline
                if period_key:
                    timeline[period_key]['total_items'] += 1
                    timeline[period_key]['actions'][action] += 1
                    timeline[period_key]['types'][leg_type] += 1

        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            continue

    # Convert to percentages
    def add_percentages(counts_dict, total):
        return {
            key: {
                'count': count,
                'percentage': round((count / total * 100), 1) if total > 0 else 0
            }
            for key, count in counts_dict.items()
        }

    return {
        'summary': summary,
        'final_actions': add_percentages(dict(final_actions), summary['total_items']),
        'legislation_types': add_percentages(dict(legislation_types), summary['total_items']),
        'timeline': [
            {
                'period': period,
                'total_items': data['total_items'],
                'meetings': data['meetings'],
                'actions': dict(data['actions']),
                'types': dict(data['types'])
            }
            for period, data in sorted(timeline.items())
        ]
    }

# Dashboard cache
DASHBOARD_CACHE = {
    'last_updated': None,
    'terms': None,
    'all_stats': None,
    'ready': False
}

def refresh_dashboard_cache():
    """Pre-compute dashboard aggregations (runs in background thread)."""
    import os
    try:
        print("Building dashboard cache...", flush=True)
        start_time = datetime.now()

        # Lower priority so OCR workers aren't starved and vice versa
        try:
            os.nice(10)
        except OSError:
            pass

        # Get all available dates
        all_dates = load_all_dates()
        years = sorted(set(d.split('-')[0] for d in all_dates))
        min_year = int(years[0]) if years else 1984
        max_year = int(years[-1]) if years else 2026

        # Calculate terms
        terms = calculate_council_terms(min_year, max_year)
        print(f"  Terms calculated: {len(terms)}", flush=True)

        # Pre-compute all-time stats
        all_stats = aggregate_legislation_data()
        print(f"  Stats aggregated: {all_stats['summary']}", flush=True)

        # Store in cache
        DASHBOARD_CACHE['last_updated'] = datetime.now()
        DASHBOARD_CACHE['terms'] = terms
        DASHBOARD_CACHE['all_stats'] = all_stats
        DASHBOARD_CACHE['ready'] = True

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"Dashboard cache built in {elapsed:.2f} seconds", flush=True)
    except Exception as e:
        import traceback
        print(f"ERROR building dashboard cache: {e}", flush=True)
        traceback.print_exc()

@app.route('/')
def index():
    """Homepage with search and browse functionality."""
    return render_template('index.html')

@app.route('/api/dates')
def api_dates():
    """API endpoint to get all available dates."""
    dates = load_all_dates()

    # Group by year
    dates_by_year = {}
    for date in dates:
        year = date.split('-')[0]
        if year not in dates_by_year:
            dates_by_year[year] = []
        dates_by_year[year].append(date)

    # Count total legislation items across all dates
    total_items = 0
    for json_file in MEETING_DATES_DIR.rglob('*.json'):
        if '.bak' in json_file.name:
            continue
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
                total_items += len(data.get('data', []))
        except Exception:
            continue

    return jsonify({
        'dates': dates,
        'dates_by_year': dates_by_year,
        'total_count': len(dates),
        'total_items': total_items
    })

@app.route('/api/date/<date_str>')
def api_date(date_str):
    """API endpoint to get legislation for a specific date."""
    data = load_data_by_date(date_str)

    if data is None:
        return jsonify({'error': 'Date not found'}), 404

    return jsonify({
        'date': date_str,
        'count': len(data),
        'data': data
    })

@app.route('/api/search')
def api_search():
    """API endpoint to search legislation."""
    query       = request.args.get('q', '')
    search_field = request.args.get('field', 'all')
    leg_type    = request.args.get('type', '') or None
    date_from   = _normalize_date_from(request.args.get('date_from', ''))
    date_to     = _normalize_date_to(request.args.get('date_to', ''))
    sort_by     = request.args.get('sort', 'date_desc')

    if not query:
        return jsonify({'error': 'Query required'}), 400

    results = search_all_data(query, search_field, leg_type, date_from, date_to, sort_by)

    return jsonify({
        'query': query,
        'field': search_field,
        'count': len(results),
        'results': results  # Return all results (pagination handled client-side)
    })

@app.route('/browse')
def browse():
    """Browse page."""
    return render_template('browse.html')

@app.route('/search')
def search_page():
    """Search page."""
    return render_template('search.html')

@app.route('/councilmembers/timeline')
def councilmembers_timeline():
    """Council office timeline view."""
    return render_template('councilmember_timeline.html')

@app.route('/councilmembers')
def councilmembers():
    """Councilmembers directory page."""
    return render_template('councilmembers.html')

@app.route('/councilmember/<path:sponsor_name>')
def councilmember(sponsor_name):
    """Individual councilmember page."""
    return render_template('councilmember.html', sponsor_name=sponsor_name)

@app.route('/committees')
def committees():
    """Committees directory page."""
    return render_template('committees.html')

@app.route('/committee/<path:committee_name>')
def committee(committee_name):
    """Individual committee page."""
    return render_template('committee.html', committee_name=committee_name)

@app.route('/paper-types')
def paper_types():
    """Paper type analysis page."""
    return render_template('paper_types.html')

SETTLEMENTS_FILE = Path('settlements.json')
DONATIONS_FILE   = Path('donations.json')

@app.route('/donations')
def donations_page():
    """Render the donations browser page."""
    return render_template('donations.html')


@app.route('/api/donations/summary')
def api_donations_summary():
    """Return aggregate stats for donations without the full records."""
    try:
        if not DONATIONS_FILE.exists():
            return jsonify({'error': 'donations.json not found - run parse_donations.py first'}), 404
        data = json.loads(DONATIONS_FILE.read_text())
        accepted  = [d for d in data if d.get('donation_direction') == 'accepted']
        made      = [d for d in data if d.get('donation_direction') == 'made']
        monetary  = [d for d in data if d.get('donation_type') == 'monetary']
        inkind    = [d for d in data if d.get('donation_type') == 'in_kind']
        acc_amts  = [d['amount'] for d in accepted if d.get('amount')]
        made_amts = [d['amount'] for d in made     if d.get('amount')]
        mon_amts  = [d['amount'] for d in monetary if d.get('amount')]
        ink_amts  = [d['amount'] for d in inkind   if d.get('amount')]
        acc_total  = sum(acc_amts)
        made_total = sum(made_amts)
        return jsonify({
            'accepted_count':  len(accepted),
            'accepted_total':  acc_total,
            'made_count':      len(made),
            'made_total':      made_total,
            'grand_total':     acc_total + made_total,
            'total_count':     len(data),
            'monetary_count':  len(monetary),
            'monetary_total':  sum(mon_amts),
            'inkind_count':    len(inkind),
            'inkind_total':    sum(ink_amts),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/donations')
def api_donations():
    """API endpoint for parsed donation data."""
    try:
        if not DONATIONS_FILE.exists():
            return jsonify({'error': 'donations.json not found - run parse_donations.py first'}), 404
        data = json.loads(DONATIONS_FILE.read_text())

        direction  = request.args.get('direction')      # 'accepted' or 'made'
        min_amount = request.args.get('min_amount', type=float)
        max_amount = request.args.get('max_amount', type=float)
        year_from  = request.args.get('year_from')
        year_to    = request.args.get('year_to')
        donor      = request.args.get('donor')
        recipient  = request.args.get('recipient')

        if direction:
            data = [d for d in data if d.get('donation_direction') == direction]
        if min_amount is not None:
            data = [d for d in data if d.get('amount') and d['amount'] >= min_amount]
        if max_amount is not None:
            data = [d for d in data if d.get('amount') and d['amount'] <= max_amount]
        if year_from:
            data = [d for d in data if d.get('legislation_date', '') >= year_from]
        if year_to:
            data = [d for d in data if d.get('legislation_date', '') <= year_to + '-12-31']
        if donor:
            data = [d for d in data if donor.lower() in (d.get('donor') or '').lower()]
        if recipient:
            data = [d for d in data if recipient.lower() in (d.get('recipient') or '').lower()]

        total_amount = sum(d['amount'] for d in data if d.get('amount'))
        return jsonify({
            'count':        len(data),
            'total_amount': total_amount,
            'donations':    data,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin')
def admin_dashboard():
    """Admin dashboard — links to all admin sections."""
    return render_template('admin.html')


@app.route('/admin/donations')
def admin_donations():
    """Render donations admin page."""
    return render_template('admin_donations.html')


@app.route('/api/admin/donations/update', methods=['POST'])
def api_admin_donations_update():
    """Update one or more fields on a donation record in donations.json."""
    try:
        payload = request.get_json(force=True)
        donation_id = payload.get('id')
        if donation_id is None:
            return jsonify({'error': 'id is required'}), 400

        if not DONATIONS_FILE.exists():
            return jsonify({'error': 'donations.json not found'}), 404

        data = json.loads(DONATIONS_FILE.read_text())

        # Find by id
        found = None
        for record in data:
            if record.get('id') == donation_id:
                found = record
                break

        if found is None:
            return jsonify({'error': f'Donation id {donation_id} not found'}), 404

        # Allowed editable fields
        editable = {'donation_direction', 'donation_type', 'amount', 'donor', 'recipient', 'item_donated', 'purpose', 'excluded'}
        updates = {k: v for k, v in payload.items() if k in editable}

        if not updates:
            return jsonify({'error': 'No valid fields to update'}), 400

        # Coerce amount to float or None
        if 'amount' in updates:
            raw_amount = updates['amount']
            if raw_amount is None or raw_amount == '':
                updates['amount'] = None
            else:
                try:
                    updates['amount'] = float(str(raw_amount).replace(',', ''))
                except ValueError:
                    return jsonify({'error': f'Invalid amount: {raw_amount}'}), 400

        # Apply updates
        found.update(updates)

        # Write back atomically
        tmp = DONATIONS_FILE.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        tmp.replace(DONATIONS_FILE)

        return jsonify({'success': True, 'updated': found})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/donations/delete', methods=['POST'])
def api_admin_donations_delete():
    """Permanently remove a donation record from donations.json."""
    try:
        payload = request.get_json(force=True)
        donation_id = payload.get('id')
        if donation_id is None:
            return jsonify({'error': 'id is required'}), 400

        if not DONATIONS_FILE.exists():
            return jsonify({'error': 'donations.json not found'}), 404

        data = json.loads(DONATIONS_FILE.read_text())
        original_count = len(data)
        data = [r for r in data if r.get('id') != donation_id]

        if len(data) == original_count:
            return jsonify({'error': f'Donation id {donation_id} not found'}), 404

        tmp = DONATIONS_FILE.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        tmp.replace(DONATIONS_FILE)

        return jsonify({'success': True, 'deleted_id': donation_id})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/settlements')
def settlements_page():
    """Render the settlements browser page."""
    return render_template('settlements.html')


@app.route('/api/settlements')
def api_settlements():
    """API endpoint for parsed settlement data."""
    try:
        if not SETTLEMENTS_FILE.exists():
            return jsonify({'error': 'settlements.json not found - run parse_settlements.py first'}), 404
        data = json.loads(SETTLEMENTS_FILE.read_text())

        # Optional filters via query params
        category = request.args.get('category')      # 'individual_claim' or 'court_litigation'
        min_amount = request.args.get('min_amount', type=float)
        max_amount = request.args.get('max_amount', type=float)
        year_from = request.args.get('year_from')
        year_to = request.args.get('year_to')
        damage_type = request.args.get('damage_type')
        court = request.args.get('court')

        if category:
            data = [s for s in data if s.get('settlement_category') == category]
        if min_amount is not None:
            data = [s for s in data if s.get('amount') and s['amount'] >= min_amount]
        if max_amount is not None:
            data = [s for s in data if s.get('amount') and s['amount'] <= max_amount]
        if year_from:
            data = [s for s in data if s.get('legislation_date', '') >= year_from]
        if year_to:
            data = [s for s in data if s.get('legislation_date', '') <= year_to + '-12-31']
        if damage_type:
            data = [s for s in data if damage_type.lower() in (s.get('damage_type') or '').lower()]
        if court:
            data = [s for s in data if court.lower() in (s.get('court') or '').lower()]

        total_amount = sum(s['amount'] for s in data if s.get('amount'))
        return jsonify({
            'count': len(data),
            'total_amount': total_amount,
            'settlements': data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/settlements/summary')
def api_settlements_summary():
    """Return aggregate stats for settlements without the full records."""
    try:
        if not SETTLEMENTS_FILE.exists():
            return jsonify({'error': 'settlements.json not found'}), 404
        data = json.loads(SETTLEMENTS_FILE.read_text())
        individual = [s for s in data if s.get('settlement_category') == 'individual_claim']
        court      = [s for s in data if s.get('settlement_category') == 'court_litigation']
        ind_amounts   = [s['amount'] for s in individual if s.get('amount')]
        court_amounts = [s['amount'] for s in court      if s.get('amount')]
        ind_total   = sum(ind_amounts)
        court_total = sum(court_amounts)
        return jsonify({
            'individual_count':  len(individual),
            'individual_total':  ind_total,
            'court_count':       len(court),
            'court_total':       court_total,
            'grand_total':       ind_total + court_total,
            'total_count':       len(data),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/sponsors')
def api_sponsors():
    """API endpoint to get all sponsors."""
    sponsors = load_all_sponsors()

    return jsonify({
        'sponsors': sponsors,
        'total_count': len(sponsors)
    })

@app.route('/api/councilmembers-terms')
def api_councilmembers_terms():
    """API endpoint to get councilmember term dates, enriched with meeting counts."""
    try:
        if not COUNCILMEMBERS_FILE.exists():
            return jsonify({'councilmembers': []})

        with open(COUNCILMEMBERS_FILE, 'r') as f:
            data = json.load(f)

        # Collect all meeting dates once
        all_meeting_dates = []
        for json_file in sorted(MEETING_DATES_DIR.rglob('*.json')):
            if json_file.suffix == '.bak' or json_file.name.endswith('.bak'):
                continue
            try:
                d = json.loads(json_file.read_text())
                date_str = d.get('date') or json_file.stem
                all_meeting_dates.append(date_str)
            except Exception:
                continue

        # Count meetings within each councilmember's tenure,
        # excluding terms where the member served as President
        for cm in data.get('councilmembers', []):
            terms = cm.get('terms', [])
            member_terms = [t for t in terms if t.get('office') != 'President']
            meetings = sum(
                1 for d in all_meeting_dates
                if any(
                    t.get('start') and d >= t['start'] and (t['end'] is None or d <= t['end'])
                    for t in member_terms
                )
            )
            cm['meetings_during_tenure'] = meetings
            # Expose convenience start/end derived from terms for the JS layer
            if terms:
                cm['start'] = terms[0].get('start')
                cm['end'] = terms[-1].get('end')

        return jsonify(data)
    except Exception as e:
        print(f"Error loading councilmembers terms: {e}")
        return jsonify({'councilmembers': []})

@app.route('/api/committees-terms')
def api_committees_terms():
    """API endpoint to get committee term dates."""
    try:
        if COMMITTEES_FILE.exists():
            with open(COMMITTEES_FILE, 'r') as f:
                data = json.load(f)
                return jsonify(data)
        else:
            return jsonify({'committees': []})
    except Exception as e:
        print(f"Error loading committees: {e}")
        return jsonify({'committees': []})

@app.route('/api/admin/save-committees', methods=['POST'])
def api_save_committees():
    """API endpoint to save committees to file."""
    try:
        data = request.get_json()
        committees = data.get('committees', [])

        # Prepare the data structure with metadata
        output_data = {
            "_note": "This file tracks the various committees that sponsor legislation in the Atlanta City Council. Dates represent when committees were active based on available data.",
            "_usage": "Set end to null for currently active committees.",
            "committees": committees
        }

        # Save to file
        with open(COMMITTEES_FILE, 'w') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error saving committees: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sponsor/<path:sponsor_name>')
def api_sponsor(sponsor_name):
    """API endpoint to get legislation by sponsor."""
    data = load_data_by_sponsor(sponsor_name)

    return jsonify({
        'sponsor': sponsor_name,
        'count': len(data),
        'data': data
    })

@app.route('/api/committees-with-counts')
def api_committees_with_counts():
    """API endpoint to get all committees with their legislation counts."""
    # Load committee definitions
    committees_data = {}
    if COMMITTEES_FILE.exists():
        with open(COMMITTEES_FILE, 'r') as f:
            data = json.load(f)
            for committee in data.get('committees', []):
                committees_data[committee['name']] = {
                    'name': committee['name'],
                    'start': committee.get('start'),
                    'end': committee.get('end'),
                    'active': committee.get('end') is None,
                    'count': 0
                }

    # Count legislation for each committee
    for json_file in MEETING_DATES_DIR.rglob("*.json"):
        try:
            with open(json_file, 'r') as f:
                content = json.load(f)
                data = content.get('data', [])

                for item in data:
                    sponsors = item.get('sponsors', [])
                    for sponsor in sponsors:
                        if sponsor in committees_data:
                            committees_data[sponsor]['count'] += 1
        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            continue

    # Convert to list and sort by count
    committees_list = list(committees_data.values())
    committees_list.sort(key=lambda x: x['count'], reverse=True)

    return jsonify({
        'committees': committees_list,
        'total_count': len(committees_list)
    })

@app.route('/api/committee/<path:committee_name>')
def api_committee(committee_name):
    """API endpoint to get legislation introduced by a specific committee."""
    data = load_data_by_sponsor(committee_name)

    # Load committee and councilmember names for classification
    committee_names = load_committee_names()
    councilmember_names = load_councilmember_names()

    # Add paper type classification to each item
    for item in data:
        sponsors = item.get('sponsors', [])
        item['paperType'] = classify_paper_type(sponsors, committee_names, councilmember_names)

    return jsonify({
        'committee': committee_name,
        'count': len(data),
        'data': data
    })

@app.route('/api/paper-type-analysis')
def api_paper_type_analysis():
    """API endpoint to analyze Committee Papers vs Personal Papers."""
    # Load committee and councilmember names
    committee_names = load_committee_names()
    councilmember_names = load_councilmember_names()

    # Initialize counters
    total_items = 0
    committee_papers = 0
    personal_papers = 0
    mixed_papers = 0
    unknown_papers = 0

    # Iterate through all legislation
    for json_file in MEETING_DATES_DIR.rglob("*.json"):
        try:
            with open(json_file, 'r') as f:
                content = json.load(f)
                data = content.get('data', [])

                for item in data:
                    total_items += 1
                    sponsors = item.get('sponsors', [])
                    paper_type = classify_paper_type(sponsors, committee_names, councilmember_names)

                    if paper_type == "Committee Paper":
                        committee_papers += 1
                    elif paper_type == "Personal Paper":
                        personal_papers += 1
                    elif paper_type == "Mixed":
                        mixed_papers += 1
                    else:
                        unknown_papers += 1

        except Exception as e:
            print(f"Error processing {json_file}: {e}")
            continue

    return jsonify({
        'total_items': total_items,
        'committee_papers': committee_papers,
        'personal_papers': personal_papers,
        'mixed_papers': mixed_papers,
        'unknown_papers': unknown_papers
    })

@app.route('/admin/sponsors')
def admin_sponsors():
    """Admin page to edit sponsor information."""
    return render_template('admin_sponsors.html')

@app.route('/admin/merge-sponsors')
def admin_merge_sponsors():
    """Admin page to merge sponsor name variations."""
    return render_template('admin_merge_sponsors.html')

@app.route('/api/admin/update-sponsors', methods=['POST'])
def api_update_sponsors():
    """API endpoint to update sponsor information for a specific item."""
    try:
        data = request.get_json()

        date_str = data.get('date')
        item_id = data.get('id')
        new_sponsors = data.get('sponsors', [])

        if not date_str or not item_id:
            return jsonify({'success': False, 'error': 'Missing date or id'}), 400

        # Find the file
        year = date_str.split('-')[0]
        json_file = MEETING_DATES_DIR / year / f"{date_str}.json"

        if not json_file.exists():
            return jsonify({'success': False, 'error': 'File not found'}), 404

        # Create backup
        backup_file = json_file.with_suffix('.json.bak')
        shutil.copy2(json_file, backup_file)

        # Load and update
        with open(json_file, 'r') as f:
            content = json.load(f)

        items = content.get('data', [])
        item_found = False

        for item in items:
            if item.get('id') == item_id:
                item['sponsors'] = new_sponsors
                # Update sponsor confidence if we're modifying sponsors
                if new_sponsors:
                    item['sponsorConfidence'] = 'manual'
                item_found = True
                break

        if not item_found:
            return jsonify({'success': False, 'error': 'Item not found'}), 404

        # Save
        content['data'] = items
        with open(json_file, 'w') as f:
            json.dump(content, f, indent=2)

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error updating sponsors: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/merge-sponsors', methods=['POST'])
def api_merge_sponsors():
    """API endpoint to merge multiple sponsor name variations into one canonical name."""
    try:
        data = request.get_json()

        variations = data.get('variations', [])
        canonical_name = data.get('canonical_name', '')

        if not variations or not canonical_name:
            return jsonify({'success': False, 'error': 'Missing variations or canonical_name'}), 400

        if len(variations) < 2:
            return jsonify({'success': False, 'error': 'Need at least 2 variations to merge'}), 400

        files_updated = 0
        items_updated = 0

        # Process all JSON files
        for json_file in MEETING_DATES_DIR.rglob("*.json"):
            try:
                # Create backup
                backup_file = json_file.with_suffix('.json.bak')
                shutil.copy2(json_file, backup_file)

                # Load file
                with open(json_file, 'r') as f:
                    content = json.load(f)

                items = content.get('data', [])
                file_modified = False

                # Update items
                for item in items:
                    sponsors = item.get('sponsors', [])
                    if sponsors:
                        updated_sponsors = []
                        item_modified = False

                        for sponsor in sponsors:
                            if sponsor in variations:
                                # Replace with canonical name
                                if canonical_name not in updated_sponsors:
                                    updated_sponsors.append(canonical_name)
                                item_modified = True
                            else:
                                if sponsor not in updated_sponsors:
                                    updated_sponsors.append(sponsor)

                        if item_modified:
                            item['sponsors'] = updated_sponsors
                            item['sponsorConfidence'] = 'manual'
                            items_updated += 1
                            file_modified = True

                # Save if modified
                if file_modified:
                    content['data'] = items
                    with open(json_file, 'w') as f:
                        json.dump(content, f, indent=2)
                    files_updated += 1

            except Exception as e:
                print(f"Error processing {json_file}: {e}")
                continue

        return jsonify({
            'success': True,
            'files_updated': files_updated,
            'items_updated': items_updated
        })

    except Exception as e:
        print(f"Error merging sponsors: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/delete-sponsor', methods=['POST'])
def api_delete_sponsor():
    """API endpoint to delete a sponsor from all legislation data."""
    try:
        data = request.get_json()
        sponsor_name = data.get('sponsor_name', '')

        if not sponsor_name:
            return jsonify({'success': False, 'error': 'Missing sponsor_name'}), 400

        files_updated = 0
        items_updated = 0

        # Process all JSON files
        for json_file in MEETING_DATES_DIR.rglob("*.json"):
            try:
                # Create backup
                backup_file = json_file.with_suffix('.json.bak')
                shutil.copy2(json_file, backup_file)

                # Load file
                with open(json_file, 'r') as f:
                    content = json.load(f)

                items = content.get('data', [])
                file_modified = False

                # Update items
                for item in items:
                    sponsors = item.get('sponsors', [])
                    if sponsor_name in sponsors:
                        # Remove the sponsor
                        item['sponsors'] = [s for s in sponsors if s != sponsor_name]
                        item['sponsorConfidence'] = 'manual'
                        items_updated += 1
                        file_modified = True

                # Save if modified
                if file_modified:
                    content['data'] = items
                    with open(json_file, 'w') as f:
                        json.dump(content, f, indent=2)
                    files_updated += 1

            except Exception as e:
                print(f"Error processing {json_file}: {e}")
                continue

        return jsonify({
            'success': True,
            'files_updated': files_updated,
            'items_updated': items_updated,
            'sponsor_name': sponsor_name
        })

    except Exception as e:
        print(f"Error deleting sponsor: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Final Action admin routes

@app.route('/admin/final-actions')
def admin_final_actions():
    """Render final actions admin page."""
    return render_template('admin_final_actions.html')

@app.route('/api/admin/final-actions')
def api_final_actions():
    """API endpoint to get all unique final actions with counts."""
    try:
        from collections import defaultdict
        final_actions_count = defaultdict(int)

        # Count occurrences of each final action
        for json_file in MEETING_DATES_DIR.rglob("*.json"):
            if '.bak' in json_file.name:
                continue
            try:
                with open(json_file, 'r') as f:
                    content = json.load(f)

                for item in content.get('data', []):
                    final_action = item.get('finalAction', '')
                    if final_action:
                        final_actions_count[final_action] += 1
                    else:
                        final_actions_count['(empty)'] += 1

            except Exception as e:
                print(f"Error processing {json_file}: {e}")
                continue

        # Convert to list format
        final_actions = [
            {'action': action, 'count': count}
            for action, count in final_actions_count.items()
        ]

        return jsonify({'final_actions': final_actions})

    except Exception as e:
        print(f"Error loading final actions: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/merge-final-actions', methods=['POST'])
def api_merge_final_actions():
    """API endpoint to merge multiple final action variations into one canonical value."""
    try:
        data = request.get_json()
        variations = data.get('variations', [])
        canonical_action = data.get('canonical_action', '')

        if not variations or not canonical_action:
            return jsonify({'success': False, 'error': 'Missing variations or canonical_action'}), 400

        files_updated = 0
        items_updated = 0

        # Process all JSON files
        for json_file in MEETING_DATES_DIR.rglob("*.json"):
            if '.bak' in json_file.name:
                continue

            try:
                # Create backup
                backup_file = json_file.with_suffix('.json.bak')
                shutil.copy2(json_file, backup_file)

                # Load file
                with open(json_file, 'r') as f:
                    content = json.load(f)

                items = content.get('data', [])
                file_modified = False

                # Update items
                for item in items:
                    final_action = item.get('finalAction', '')
                    # Check if this item's final action is in the variations list
                    if final_action in variations:
                        item['finalAction'] = canonical_action
                        items_updated += 1
                        file_modified = True

                # Save if modified
                if file_modified:
                    content['data'] = items
                    with open(json_file, 'w') as f:
                        json.dump(content, f, indent=2)
                    files_updated += 1

            except Exception as e:
                print(f"Error processing {json_file}: {e}")
                continue

        return jsonify({
            'success': True,
            'files_updated': files_updated,
            'items_updated': items_updated
        })

    except Exception as e:
        print(f"Error merging final actions: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/update-final-action', methods=['POST'])
def api_update_final_action():
    """API endpoint to update a specific item's final action."""
    try:
        data = request.get_json()
        date = data.get('date')
        item_id = data.get('item_id')
        new_final_action = data.get('final_action', '')

        if not date or item_id is None:
            return jsonify({'success': False, 'error': 'Missing date or item_id'}), 400

        # Find and update the item
        json_file = find_json_file_by_date(date)
        if not json_file:
            return jsonify({'success': False, 'error': 'Date file not found'}), 404

        # Create backup
        backup_file = json_file.with_suffix('.json.bak')
        shutil.copy2(json_file, backup_file)

        # Load file
        with open(json_file, 'r') as f:
            content = json.load(f)

        items = content.get('data', [])
        item_found = False

        for item in items:
            if item.get('id') == item_id:
                item['finalAction'] = new_final_action
                item_found = True
                break

        if not item_found:
            return jsonify({'success': False, 'error': 'Item not found'}), 404

        # Save
        content['data'] = items
        with open(json_file, 'w') as f:
            json.dump(content, f, indent=2)

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error updating final action: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/final-action/<path:action_value>')
def final_action_page(action_value):
    """Render page showing all items with a specific final action."""
    return render_template('final_action.html', action_value=action_value)

@app.route('/api/final-action/<path:action_value>')
def api_final_action(action_value):
    """API endpoint to get all items with a specific final action."""
    try:
        items = []

        # Handle special case for empty actions
        search_value = '' if action_value == '(empty)' else action_value

        # Search through all JSON files
        for json_file in MEETING_DATES_DIR.rglob("*.json"):
            if '.bak' in json_file.name:
                continue

            try:
                with open(json_file, 'r') as f:
                    content = json.load(f)

                meeting_date = content.get('date', '')

                for item in content.get('data', []):
                    final_action = item.get('finalAction', '')

                    # Match the final action
                    if final_action == search_value:
                        # Add meeting date for context
                        item_copy = item.copy()
                        item_copy['date'] = meeting_date
                        items.append(item_copy)

            except Exception as e:
                print(f"Error processing {json_file}: {e}")
                continue

        # Sort by date (most recent first)
        items.sort(key=lambda x: x.get('date', ''), reverse=True)

        return jsonify({
            'action': action_value,
            'count': len(items),
            'data': items
        })

    except Exception as e:
        print(f"Error loading items for final action: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/update-item', methods=['POST'])
def api_update_item():
    """API endpoint to update an item's description and/or final action."""
    try:
        data = request.get_json()
        date = data.get('date')
        item_id = data.get('item_id')
        new_description = data.get('description')
        new_final_action = data.get('final_action')

        if not date or item_id is None:
            return jsonify({'success': False, 'error': 'Missing date or item_id'}), 400

        # Find and update the item
        json_file = find_json_file_by_date(date)
        if not json_file:
            return jsonify({'success': False, 'error': 'Date file not found'}), 404

        # Create backup
        backup_file = json_file.with_suffix('.json.bak')
        shutil.copy2(json_file, backup_file)

        # Load file
        with open(json_file, 'r') as f:
            content = json.load(f)

        items = content.get('data', [])
        item_found = False

        for item in items:
            if item.get('id') == item_id:
                # Update fields if provided
                if new_description is not None:
                    item['description'] = new_description
                if new_final_action is not None:
                    item['finalAction'] = new_final_action
                item_found = True
                break

        if not item_found:
            return jsonify({'success': False, 'error': 'Item not found'}), 404

        # Save
        content['data'] = items
        with open(json_file, 'w') as f:
            json.dump(content, f, indent=2)

        return jsonify({'success': True})

    except Exception as e:
        print(f"Error updating item: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Dashboard routes

@app.route('/dashboard')
def dashboard_page():
    """Render dashboard page."""
    return render_template('dashboard.html')

@app.route('/api/dashboard/terms')
def dashboard_terms():
    """Get all available council terms."""
    if not DASHBOARD_CACHE['ready']:
        return jsonify({'terms': [], 'loading': True})
    return jsonify({
        'terms': DASHBOARD_CACHE['terms']
    })

@app.route('/api/dashboard/stats')
def dashboard_stats():
    """Get dashboard statistics with optional filtering."""
    import calendar

    if not DASHBOARD_CACHE['ready']:
        return jsonify({'loading': True, 'summary': {'total_items': 0, 'total_meetings': 0}, 'final_actions': {}, 'legislation_types': {}, 'timeline': [], 'drill_down': []})

    level = request.args.get('level', 'all')  # all|term|year|month
    filter_value = request.args.get('filter')

    if level == 'all':
        # Return cached all-time stats
        stats = DASHBOARD_CACHE['all_stats'].copy()
        # Add drill-down items (terms)
        stats['drill_down'] = [
            {
                'value': t['label'],
                'label': t['label'],
                'type': 'term'
            }
            for t in DASHBOARD_CACHE['terms']
        ]
        stats['level'] = level
        stats['filter'] = None
        return jsonify(stats)

    # Determine date range from filter
    start_date = None
    end_date = None
    group_by = 'year'

    if level == 'term' and filter_value:
        # Parse term like "2022-2025"
        start, end = filter_value.split('-')
        start_date = f'{start}-01-01'
        end_date = f'{int(end)}-12-31'
        group_by = 'year'
    elif level == 'year' and filter_value:
        start_date = f'{filter_value}-01-01'
        end_date = f'{filter_value}-12-31'
        group_by = 'month'
    elif level == 'month' and filter_value:
        year, month = filter_value.split('-')
        start_date = f'{filter_value}-01'
        # Calculate last day of month
        last_day = calendar.monthrange(int(year), int(month))[1]
        end_date = f'{filter_value}-{last_day:02d}'
        group_by = 'date'

    # Compute on-demand
    stats = aggregate_legislation_data(start_date, end_date, group_by)

    # Add drill-down items
    drill_down = []
    if level == 'term' and filter_value:
        # Years within term (inclusive of end year)
        start_year, end_year = map(int, filter_value.split('-'))
        drill_down = [
            {'value': str(year), 'label': str(year), 'type': 'year'}
            for year in range(start_year, end_year + 1)
        ]
    elif level == 'year' and filter_value:
        # Months within year
        drill_down = [
            {'value': f'{filter_value}-{month:02d}', 'label': datetime(int(filter_value), month, 1).strftime('%B'), 'type': 'month'}
            for month in range(1, 13)
        ]
    elif level == 'month' and filter_value:
        # Dates within month - get from timeline
        drill_down = [
            {'value': item['period'], 'label': item['period'], 'type': 'date'}
            for item in stats['timeline']
        ]

    stats['drill_down'] = drill_down
    stats['level'] = level
    stats['filter'] = filter_value

    return jsonify(stats)

# Legislation detail routes

@app.route('/legislation/<int:legislation_id>')
def legislation_detail(legislation_id):
    """Render legislation detail page."""
    # Search through all meeting files to find this ID
    # First search by meetingDocId (which matches IQM2 system), then by internal id
    item = None
    item_date = None
    details = None

    # If caller explicitly requests search by internal id, skip meetingDocId search
    # (prevents collision when an old item's internal id matches a newer item's meetingDocId)
    search_by = request.args.get('by', '')

    # First pass: search by meetingDocId (unless caller forced by=id)
    if search_by != 'id':
        for json_file in MEETING_DATES_DIR.rglob("*.json"):
            if '.bak' in json_file.name:
                continue
            try:
                with open(json_file, 'r') as f:
                    content = json.load(f)

                for data_item in content.get('data', []):
                    if data_item.get('meetingDocId') == legislation_id:
                        item = data_item
                        item_date = content.get('date')
                        break

                if item:
                    break
            except Exception:
                continue

    # Second pass: if not found by meetingDocId, search by internal id
    if not item:
        for json_file in MEETING_DATES_DIR.rglob("*.json"):
            if '.bak' in json_file.name:
                continue
            try:
                with open(json_file, 'r') as f:
                    content = json.load(f)

                for data_item in content.get('data', []):
                    if data_item.get('id') == legislation_id:
                        item = data_item
                        item_date = content.get('date')
                        break

                if item:
                    break
            except Exception:
                continue

    if not item:
        return render_template('error.html', message='Legislation not found'), 404

    # Check if we have scraped details for this ID
    details_file = Path('legislation_details') / f'{legislation_id}.json'
    if details_file.exists():
        try:
            with open(details_file, 'r') as f:
                scraped_data = json.load(f)
                # Extract the content if it's in the expected format
                if 'content' in scraped_data:
                    details = scraped_data['content']
                elif 'results' in scraped_data and len(scraped_data['results']) > 0:
                    # Handle the format from scrape_legislation_details.py
                    result = scraped_data['results'][0]
                    if 'content' in result:
                        details = result['content']
        except Exception as e:
            print(f"Error loading scraped details for ID {legislation_id}: {e}")

    return render_template('legislation_detail.html', item=item, details=details)

@app.route('/api/legislation/<int:legislation_id>')
def api_legislation_detail(legislation_id):
    """API endpoint to get detailed legislation information."""
    # Check if we have scraped details for this ID
    details_file = Path('legislation_details') / f'{legislation_id}.json'

    if details_file.exists():
        try:
            with open(details_file, 'r') as f:
                details = json.load(f)
            return jsonify(details)
        except Exception as e:
            print(f"Error loading legislation details: {e}")
            return jsonify({'error': 'Failed to load details'}), 500
    else:
        # Return basic info from meeting data if available
        # Search through all meeting files to find this ID
        for json_file in MEETING_DATES_DIR.rglob("*.json"):
            if '.bak' in json_file.name:
                continue
            try:
                with open(json_file, 'r') as f:
                    content = json.load(f)

                for item in content.get('data', []):
                    if item.get('id') == legislation_id or item.get('meetingDocId') == legislation_id:
                        return jsonify({
                            'id': legislation_id,
                            'item': item,
                            'date': content.get('date'),
                            'details': None  # No scraped details available
                        })
            except Exception:
                continue

        return jsonify({'error': 'Legislation not found'}), 404

# News releases routes
try:
    from news_db import NewsDatabase
    NEWS_DB_AVAILABLE = True
except Exception as e:
    print(f"Warning: News database module not available: {e}")
    NEWS_DB_AVAILABLE = False

def get_news_db():
    """Get or create a NewsDatabase instance for this request."""
    if 'news_db' not in g:
        g.news_db = NewsDatabase('news_releases.db')
    return g.news_db

@app.teardown_appcontext
def close_news_db(error):
    """Close the database connection at the end of the request."""
    news_db = g.pop('news_db', None)
    if news_db is not None:
        news_db.close()

@app.route('/news')
def news_releases():
    """Display news releases list."""
    if not NEWS_DB_AVAILABLE:
        return render_template('error.html', message='News database not available'), 503

    page = request.args.get('page', 1, type=int)
    news_type = request.args.get('type', None)  # Filter by type
    per_page = 20
    offset = (page - 1) * per_page

    db = get_news_db()
    news_items = db.get_all_news(limit=per_page, offset=offset, order_by='id DESC', news_type=news_type)

    # Always get stats for the header display
    stats = db.get_stats()

    # Get type-specific count
    if news_type:
        cursor = db.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM news WHERE type = ? AND (is_hidden IS NULL OR is_hidden = 0)', (news_type,))
        total_count = cursor.fetchone()[0]
    else:
        total_count = stats['total_news']

    # Get type statistics
    cursor = db.conn.cursor()
    cursor.execute('SELECT type, COUNT(*) FROM news WHERE (is_hidden IS NULL OR is_hidden = 0) GROUP BY type')
    type_stats = {row[0]: row[1] for row in cursor.fetchall()}

    # Add preview text to each news item (strip boilerplate)
    for item in news_items:
        item['preview_text'] = get_preview_text(item.get('content_text', ''), max_length=300)

    total_pages = (total_count + per_page - 1) // per_page

    return render_template('news.html',
                          news=news_items,
                          total=total_count,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          stats=stats,
                          type_filter=news_type,
                          type_stats=type_stats)

@app.route('/news/<int:news_id>')
def news_detail(news_id):
    """Display single news item."""
    if not NEWS_DB_AVAILABLE:
        return render_template('error.html', message='News database not available'), 503

    db = get_news_db()
    item = db.get_news_by_id(news_id)
    if not item:
        return render_template('error.html', message='News release not found'), 404

    return render_template('news_detail.html', news=item)

@app.route('/news/search')
def news_search():
    """Search news releases."""
    if not NEWS_DB_AVAILABLE:
        return render_template('error.html', message='News database not available'), 503

    query = request.args.get('q', '')
    db = get_news_db()
    results = db.search_news(query, limit=100) if query else []

    return render_template('news_search.html', results=results, query=query)

@app.route('/api/news')
def api_news_list():
    """API endpoint for news list."""
    if not NEWS_DB_AVAILABLE:
        return jsonify({'error': 'News database not available'}), 503

    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)

    db = get_news_db()
    news_items = db.get_all_news(limit=limit, offset=offset)
    stats = db.get_stats()

    return jsonify({
        'news': news_items,
        'total': stats['total_news'],
        'limit': limit,
        'offset': offset
    })

# Admin routes for news management
@app.route('/admin/news')
def admin_news_list():
    """Admin view of all news (including hidden)."""
    if not NEWS_DB_AVAILABLE:
        return render_template('error.html', message='News database not available'), 503

    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort_by', 'id')
    order = request.args.get('order', 'desc')
    type_filter = request.args.get('type')

    per_page = 50
    offset = (page - 1) * per_page

    # Build order_by clause
    valid_sort_fields = {'id', 'title', 'date', 'type'}
    if sort_by not in valid_sort_fields:
        sort_by = 'id'

    order_direction = 'ASC' if order == 'asc' else 'DESC'
    order_by = f'{sort_by} {order_direction}'

    db = get_news_db()
    news_items = db.get_all_news(
        limit=per_page,
        offset=offset,
        order_by=order_by,
        include_hidden=True,
        news_type=type_filter
    )

    # Get type statistics
    cursor = db.conn.cursor()
    cursor.execute('SELECT type, COUNT(*) FROM news GROUP BY type')
    type_counts = {row[0]: row[1] for row in cursor.fetchall()}

    # Build stats dictionary for template
    stats = {
        'total': sum(type_counts.values()),
        'news_releases': type_counts.get('News Release', 0),
        'media_advisories': type_counts.get('Media Advisory', 0),
        'unknown': type_counts.get('Unknown', 0)
    }

    # Get total count based on filter
    if type_filter:
        cursor.execute('SELECT COUNT(*) FROM news WHERE type = ?', (type_filter,))
        total_count = cursor.fetchone()[0]
    else:
        total_count = stats['total']

    total_pages = (total_count + per_page - 1) // per_page

    return render_template('admin_news.html',
                          news=news_items,
                          total=total_count,
                          page=page,
                          per_page=per_page,
                          total_pages=total_pages,
                          sort_by=sort_by,
                          order=order,
                          type_filter=type_filter,
                          stats=stats)

@app.route('/admin/news/<int:news_id>/edit', methods=['GET', 'POST'])
def admin_news_edit(news_id):
    """Edit a news item."""
    if not NEWS_DB_AVAILABLE:
        return render_template('error.html', message='News database not available'), 503

    db = get_news_db()

    if request.method == 'POST':
        try:
            title = request.form.get('title')
            content_html = request.form.get('content_html')
            admin_notes = request.form.get('admin_notes')

            # Update the news item
            success = db.update_news(
                news_id,
                title=title if title else None,
                content_html=content_html if content_html else None,
                admin_notes=admin_notes if admin_notes else None
            )

            if success:
                app.logger.info(f"Updated news item {news_id}")
                return redirect(url_for('admin_news_list'))
            else:
                app.logger.error(f"Failed to update news item {news_id}")
                return render_template('error.html', message='Failed to update news item'), 500

        except Exception as e:
            app.logger.error(f"Error updating news {news_id}: {e}")
            return render_template('error.html', message=f'Error updating news: {str(e)}'), 500

    # GET request - show edit form
    item = db.get_news_by_id(news_id)
    if not item:
        return render_template('error.html', message='News release not found'), 404

    # Add editable content (with boilerplate stripped)
    item['editable_content'] = get_editable_content(item.get('content_text', ''))

    return render_template('admin_news_edit.html', news=item)

@app.route('/admin/news/<int:news_id>/toggle-hidden', methods=['POST'])
def admin_news_toggle_hidden(news_id):
    """Toggle hidden status of a news item."""
    if not NEWS_DB_AVAILABLE:
        return jsonify({'error': 'News database not available'}), 503

    try:
        db = get_news_db()
        new_status = db.toggle_hidden(news_id)

        if new_status is None:
            app.logger.error(f"News item {news_id} not found for toggle")
            return jsonify({'error': 'News item not found'}), 404

        app.logger.info(f"Toggled news item {news_id} hidden status to {new_status}")
        return jsonify({'success': True, 'is_hidden': new_status})

    except Exception as e:
        app.logger.error(f"Error toggling hidden status for news {news_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/news/<int:news_id>/change-type', methods=['POST'])
def admin_news_change_type(news_id):
    """Change the type of a news item."""
    if not NEWS_DB_AVAILABLE:
        return jsonify({'error': 'News database not available'}), 503

    try:
        data = request.get_json()
        new_type = data.get('type')

        if new_type not in ['News Release', 'Media Advisory', 'Unknown']:
            return jsonify({'error': 'Invalid type'}), 400

        db = get_news_db()
        cursor = db.conn.cursor()
        cursor.execute('UPDATE news SET type = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (new_type, news_id))
        db.conn.commit()

        app.logger.info(f"Changed news item {news_id} type to {new_type}")
        return jsonify({'success': True, 'type': new_type})

    except Exception as e:
        app.logger.error(f"Error changing type for news {news_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/logs')
def admin_logs():
    """View error logs."""
    log_file = Path('logs/error.log')

    if not log_file.exists():
        return render_template('admin_logs.html', logs=[], message='No error log file found')

    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
            # Get last 500 lines, reversed (newest first)
            logs = list(reversed(lines[-500:]))

        return render_template('admin_logs.html', logs=logs)

    except Exception as e:
        app.logger.error(f"Error reading log file: {e}")
        return render_template('error.html', message=f'Error reading logs: {str(e)}'), 500

# Full-text search routes
try:
    from legislation_search_db import LegislationSearchDB
    FTS_DB_AVAILABLE = Path('legislation_fts.db').exists()
except Exception as e:
    print(f"Warning: Legislation search module not available: {e}")
    FTS_DB_AVAILABLE = False

def get_fts_db():
    """Get or create a LegislationSearchDB instance for this request."""
    if 'fts_db' not in g:
        g.fts_db = LegislationSearchDB('legislation_fts.db')
    return g.fts_db

@app.teardown_appcontext
def close_fts_db(error):
    """Close the FTS database connection at the end of the request."""
    fts_db = g.pop('fts_db', None)
    if fts_db is not None:
        fts_db.close()

LOCAL_PDF_DIR = Path('/Volumes/Sandisk/Final Action Legislation \u2013 processed')

@app.route('/pdf/<paper_number>')
def serve_pdf(paper_number):
    """Serve a processed PDF from local storage."""
    # Sanitize: only allow alphanumeric characters
    if not re.match(r'^[a-zA-Z0-9_-]+$', paper_number):
        return 'Invalid paper number', 400
    filename = f'{paper_number}.pdf'
    if not (LOCAL_PDF_DIR / filename).exists():
        return 'PDF not found', 404
    return send_from_directory(LOCAL_PDF_DIR, filename)

@app.route('/fulltext-search')
def fulltext_search_page():
    """Full-text search page."""
    if not FTS_DB_AVAILABLE:
        return render_template('error.html', message='Full-text search database not available. Run build_fts_index.py first.'), 503
    return render_template('fulltext_search.html')

@app.route('/api/fulltext-search')
def api_fulltext_search():
    """API endpoint for full-text search across OCR-extracted legislation text."""
    if not FTS_DB_AVAILABLE:
        return jsonify({'error': 'Full-text search database not available'}), 503

    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'Query required'}), 400

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = min(per_page, 100)  # Cap at 100
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    leg_type = request.args.get('type', '')
    sort = request.args.get('sort', 'relevance')

    offset = (page - 1) * per_page

    try:
        db = get_fts_db()
        result = db.search(
            query,
            limit=per_page,
            offset=offset,
            date_from=date_from or None,
            date_to=date_to or None,
            leg_type=leg_type or None,
            sort=sort,
        )

        return jsonify({
            'query': query,
            'total': result['total'],
            'page': page,
            'per_page': per_page,
            'results': result['results'],
        })

    except Exception as e:
        app.logger.error(f"Full-text search error: {e}")
        return jsonify({'error': f'Search error: {str(e)}'}), 500

# ── PERSONAL PAPERS ──────────────────────────────────────────────────────────

import personal_papers_db as pp_db

pp_db.init_db()

@app.route('/personal-papers')
def personal_papers_list():
    packages = pp_db.get_all_packages()
    return render_template('personal_papers.html', packages=packages)


@app.route('/personal-papers/<int:package_id>')
def personal_papers_detail(package_id):
    pkg = pp_db.get_package(package_id)
    if not pkg:
        return render_template('error.html', message='Package not found'), 404
    items = pp_db.get_items(package_id)
    return render_template('personal_papers_detail.html', pkg=pkg, items=items)


@app.route('/personal-papers/<int:package_id>/pdf')
def personal_papers_pdf(package_id):
    pkg = pp_db.get_package(package_id)
    if not pkg:
        return 'PDF not found', 404
    # Prefer the enriched (linked TOC) version when available
    path_key = 'enriched_pdf_path' if pkg.get('enriched_pdf_path') else 'pdf_path'
    if not pkg.get(path_key):
        return 'PDF not found', 404
    p = Path(pkg[path_key])
    return send_from_directory(str(p.parent), p.name)


@app.route('/personal-papers/<int:package_id>/toc')
def personal_papers_toc(package_id):
    pkg = pp_db.get_package(package_id)
    if not pkg or not pkg.get('toc_pdf_path'):
        return 'TOC PDF not found', 404
    p = Path(pkg['toc_pdf_path'])
    return send_from_directory(str(p.parent), p.name)


@app.route('/personal-papers/items/<int:item_id>/pdf')
def personal_papers_item_pdf(item_id):
    item = pp_db.get_item(item_id)
    if not item or not item.get('pdf_path'):
        return 'PDF not found', 404
    p = Path(item['pdf_path'])
    return send_from_directory(str(p.parent), p.name)


# Build dashboard cache in background thread on startup
import threading
_cache_thread = threading.Thread(target=refresh_dashboard_cache, daemon=True)
_cache_thread.start()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5003)
