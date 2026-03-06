#!/bin/bash
# Check for and process new Personal Papers PDFs.
# Run daily (or after each full council meeting) via cron:
#   0 9 * * 1-5 cd /path/to/final_actions && ./update_personal_papers.sh >> logs/personal_papers.log 2>&1

set -e
cd "$(dirname "$0")"

VISIBLE="--visible"

while [[ $# -gt 0 ]]; do
    case $1 in
        --headless) VISIBLE=""; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "=================================="
echo "PERSONAL PAPERS UPDATE"
echo "$(date)"
echo "=================================="
echo

python scrape_personal_papers.py --auto $VISIBLE

echo
echo "✅ Done"
