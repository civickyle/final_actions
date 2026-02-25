#!/bin/bash
# Continue scraping from the highest ID in database

# Get highest ID from database
HIGHEST_ID=$(python3 -c "
from news_db import NewsDatabase
db = NewsDatabase('news_releases.db')
stats = db.get_stats()
print(stats['max_id'] if stats['max_id'] else 0)
db.close()
")

START_ID=$((HIGHEST_ID + 1))
END_ID=${1:-4444}  # Default to 4444, or use first argument

echo "📊 Current database has IDs up to: $HIGHEST_ID"
echo "🚀 Starting scrape from: $START_ID to $END_ID"
echo ""

# Run scraper directly to database
python3 scrape_news_to_db.py \
    --start $START_ID \
    --end $END_ID \
    --visible \
    --delay 0 \
    --batch-commit 20 \
    --max-failures 50

echo ""
echo "📊 Final statistics:"
python3 news_db.py --stats
