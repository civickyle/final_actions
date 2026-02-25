#!/usr/bin/env python3
"""
Script to incrementally download Atlanta City Council legislation data by date.
Downloads data from 1984-01-03 to the current date.
"""

import requests
import json
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import logging
from typing import Optional, Dict, Any

# Configuration
API_BASE_URL = "https://test.atlantaga.gov/coawebapi/api/legislationsbydate/"
START_DATE = "1984-01-03"
OUTPUT_DIR = Path("meeting_dates")
LOG_FILE = "scrape_legislation.log"
PROGRESS_FILE = "download_progress.json"
DELAY_MONDAY = 1.0  # seconds - delay for Mondays (most legislation expected)
DELAY_OTHER_DAYS = 0.2  # seconds - faster delay for other days (typically no data)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class LegislationDownloader:
    """Downloads legislation data incrementally by date."""

    def __init__(self):
        self.output_dir = OUTPUT_DIR
        self.progress_file = Path(PROGRESS_FILE)
        self.output_dir.mkdir(exist_ok=True)

    def load_progress(self) -> Optional[str]:
        """Load the last successfully downloaded date."""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r') as f:
                    data = json.load(f)
                    return data.get('last_date')
            except Exception as e:
                logger.warning(f"Could not load progress file: {e}")
        return None

    def save_progress(self, date_str: str):
        """Save the last successfully downloaded date."""
        try:
            with open(self.progress_file, 'w') as f:
                json.dump({
                    'last_date': date_str,
                    'last_updated': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save progress: {e}")

    def fetch_legislation_by_date(self, date_str: str) -> Optional[Dict[str, Any]]:
        """
        Fetch legislation data for a specific date.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            JSON response data or None if request failed
        """
        url = f"{API_BASE_URL}?search={date_str}"
        try:
            logger.info(f"Fetching data for {date_str}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching data for {date_str}: {e}")
            return None

    def save_data(self, date_str: str, data: Dict[str, Any]) -> bool:
        """
        Save legislation data to a JSON file only if there's actual data.

        Args:
            date_str: Date in YYYY-MM-DD format
            data: JSON data to save

        Returns:
            True if data was saved, False if no data to save
        """
        # Check if data is empty (no legislation for this date)
        if not data or (isinstance(data, list) and len(data) == 0):
            logger.debug(f"No legislation data for {date_str}, skipping save")
            return False

        # Organize by year only
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        year_dir = self.output_dir / str(date_obj.year)
        year_dir.mkdir(parents=True, exist_ok=True)

        filename = year_dir / f"{date_str}.json"
        try:
            with open(filename, 'w') as f:
                json.dump({
                    'date': date_str,
                    'downloaded_at': datetime.now().isoformat(),
                    'data': data
                }, f, indent=2)
            logger.info(f"Saved data to {filename} ({len(data)} items)")
            return True
        except Exception as e:
            logger.error(f"Error saving data for {date_str}: {e}")
            return False

    def download_all(self, start_date: str = START_DATE, end_date: Optional[str] = None):
        """
        Download legislation data for all dates from start_date to end_date.

        Args:
            start_date: Starting date in YYYY-MM-DD format
            end_date: Ending date in YYYY-MM-DD format (defaults to today)
        """
        # Only resume from progress if using default start date (full download mode)
        # For specific date ranges (like single years), start fresh
        is_default_range = (start_date == START_DATE and end_date is None)

        if is_default_range:
            # Check if we should resume from a previous run
            last_date = self.load_progress()
            if last_date:
                logger.info(f"Resuming from {last_date}")
                start_date_obj = datetime.strptime(last_date, "%Y-%m-%d") + timedelta(days=1)
            else:
                start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")

        # Default end date is today
        if end_date:
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            end_date_obj = datetime.now()

        logger.info(f"Starting download from {start_date_obj.date()} to {end_date_obj.date()}")

        current_date = start_date_obj
        total_days = (end_date_obj - start_date_obj).days + 1
        processed = 0
        successful = 0

        while current_date <= end_date_obj:
            date_str = current_date.strftime("%Y-%m-%d")
            is_monday = current_date.weekday() == 0

            # Fetch data
            data = self.fetch_legislation_by_date(date_str)

            if data is not None:
                # Save data only if there's legislation for this date
                if self.save_data(date_str, data):
                    successful += 1

            # Always save progress (even if no data, to avoid re-checking empty dates)
            self.save_progress(date_str)

            processed += 1

            # Progress update
            if processed % 10 == 0:
                logger.info(f"Progress: {processed}/{total_days} days processed ({successful} with data)")

            # Move to next date
            current_date += timedelta(days=1)

            # Delay to be respectful to the server - longer for Mondays (most legislation)
            delay = DELAY_MONDAY if is_monday else DELAY_OTHER_DAYS
            time.sleep(delay)

        logger.info(f"Download complete! Processed {processed} days, {successful} days with legislation data")
        logger.info(f"Data saved in {self.output_dir}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Download Atlanta City Council legislation data by date'
    )
    parser.add_argument(
        '--year',
        type=int,
        help='Specific year to download (e.g., 1984, 2005, 2024). If not specified, downloads from 1984-01-03 to today.'
    )

    args = parser.parse_args()

    downloader = LegislationDownloader()

    try:
        if args.year:
            # Download only the specified year
            start_date = f"{args.year}-01-01"
            end_date = f"{args.year}-12-31"
            logger.info(f"Downloading data for year {args.year}")
            downloader.download_all(start_date=start_date, end_date=end_date)
        else:
            # Download all data from START_DATE to today
            downloader.download_all()
    except KeyboardInterrupt:
        logger.info("Download interrupted by user. Progress has been saved.")
        logger.info("Run the script again to resume from where you left off.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
