#!/bin/bash
# Update news releases: scrape new items and import to database

set -e  # Exit on error

cd "$(dirname "$0")"

# Default values
DB_FILE="news_releases.db"
JSON_FILE="news_releases.json"
VISIBLE="--visible"
MAX_FAILURES=10
LIMIT=100

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --headless)
            VISIBLE=""
            shift
            ;;
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --max-failures)
            MAX_FAILURES="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--headless] [--limit N] [--max-failures N]"
            exit 1
            ;;
    esac
done

echo "=================================="
echo "NEWS RELEASES UPDATE SCRIPT"
echo "=================================="
echo

# Get the highest ID currently in database
if [ -f "$DB_FILE" ]; then
    MAX_ID=$(sqlite3 "$DB_FILE" "SELECT COALESCE(MAX(id), 0) FROM news" 2>/dev/null || echo "0")
    START_ID=$((MAX_ID + 1))
    echo "📊 Current database: $MAX_ID items"
    echo "🔍 Starting scrape from ID: $START_ID"
else
    START_ID=1
    echo "📊 No existing database found"
    echo "🔍 Starting fresh scrape from ID: 1"
fi

echo "⚙️  Settings:"
echo "   - Mode: ${VISIBLE:+visible browser}${VISIBLE:-headless}"
echo "   - Limit: $LIMIT items"
echo "   - Max consecutive failures: $MAX_FAILURES"
echo

# Scrape new items
echo "🌐 Scraping news releases..."
python scrape_news_releases.py \
    --update \
    --start "$START_ID" \
    --limit "$LIMIT" \
    --max-failures "$MAX_FAILURES" \
    $VISIBLE

echo

# Import to database
if [ -f "$JSON_FILE" ]; then
    echo "💾 Importing to database..."
    python news_db.py --import "$JSON_FILE" --db "$DB_FILE"
    echo

    # Show updated stats
    echo "📈 Updated statistics:"
    python news_db.py --stats --db "$DB_FILE"
else
    echo "⚠️  Warning: JSON file not found, skipping import"
fi

echo
echo "✅ Update complete!"
