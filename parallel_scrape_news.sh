#!/bin/bash
# Parallel news scraper - runs multiple scraper instances simultaneously

START=${1:-51}
END=${2:-4444}
BATCH_SIZE=500
PARALLEL_JOBS=4

echo "================================================"
echo "PARALLEL NEWS SCRAPER"
echo "================================================"
echo "Range: $START to $END"
echo "Batch size: $BATCH_SIZE"
echo "Parallel jobs: $PARALLEL_JOBS"
echo

# Create a temporary directory for batch outputs
TEMP_DIR=$(mktemp -d)
echo "Temp directory: $TEMP_DIR"

# Function to scrape a batch
scrape_batch() {
    local start=$1
    local end=$2
    local batch_num=$3

    echo "[Batch $batch_num] Scraping IDs $start to $end..."
    python3 scrape_news_releases.py --ids $start $end --delay 0.1 > "$TEMP_DIR/batch_$batch_num.log" 2>&1
    echo "[Batch $batch_num] Complete!"
}

export -f scrape_batch

# Generate batch ranges
current=$START
batch_num=1
batches=()

while [ $current -le $END ]; do
    batch_end=$((current + BATCH_SIZE - 1))
    if [ $batch_end -gt $END ]; then
        batch_end=$END
    fi
    batches+=("$current $batch_end $batch_num")
    current=$((batch_end + 1))
    batch_num=$((batch_num + 1))
done

echo "Total batches: ${#batches[@]}"
echo

# Run batches in parallel using xargs
printf '%s\n' "${batches[@]}" | xargs -n 3 -P $PARALLEL_JOBS bash -c 'scrape_batch "$@"' _

echo
echo "================================================"
echo "ALL BATCHES COMPLETE"
echo "================================================"
echo

# Import all to database
echo "Importing to database..."
python3 news_db.py --import news_releases.json

echo
echo "Final statistics:"
python3 news_db.py --stats

# Cleanup
rm -rf "$TEMP_DIR"
echo
echo "✅ Done!"
