# Atlanta City Council Legislation Downloader

This script incrementally downloads Atlanta City Council legislation data by date from the API, starting from 1984-01-03.

## Features

- **Incremental Downloads**: Downloads data one day at a time from 1984-01-03 to today
- **Resume Capability**: Automatically resumes from the last successful download if interrupted
- **Organized Storage**: Saves data organized by year/month/date in JSON format
- **Progress Tracking**: Logs progress and saves state to allow resuming
- **Error Handling**: Gracefully handles network errors and continues processing
- **Smart Rate Limiting**: Uses slower delays for Mondays (when most legislation occurs) and faster delays for other days to optimize download speed

## Installation

1. Create and activate a virtual environment:
```bash
# Create virtual environment
python3 -m venv .venv

# Activate it (macOS/Linux)
source .venv/bin/activate

# On Windows, use:
# .venv\Scripts\activate
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Download All Data (1984-01-03 to today)

Run the script without arguments:
```bash
python scrape_legislation.py
```

The script will:
1. Check if there's a previous run to resume from
2. Download legislation data for each date from 1984-01-03 (or last checkpoint) to today
3. Save each day's data as a JSON file in `meeting_dates/YYYY/YYYY-MM-DD.json`
4. Log progress to both console and `scrape_legislation.log`
5. Save checkpoint after each successful download in `download_progress.json`

### Download Specific Year

To download data for a specific year only:
```bash
python scrape_legislation.py --year 2024
```

This will download all data from January 1 to December 31 of the specified year. Examples:
```bash
python scrape_legislation.py --year 1984  # Download 1984 only
python scrape_legislation.py --year 2005  # Download 2005 only
python scrape_legislation.py --year 2024  # Download 2024 only
```

**Note**: When using `--year`, the resume functionality is disabled and the script will download the entire year fresh.

### Command-Line Options

View all available options:
```bash
python scrape_legislation.py --help
```

### Interrupting and Resuming

You can safely interrupt the script at any time (Ctrl+C). When you run it again, it will automatically resume from the last successfully downloaded date.

## Output Structure

```
meeting_dates/
├── 1984/
│   ├── 1984-01-03.json
│   ├── 1984-01-09.json
│   └── ...
├── 1985/
│   ├── 1985-01-07.json
│   └── ...
└── ...
```

**Note**: Only dates with actual legislation data will have JSON files saved.

Each JSON file contains:
- `date`: The date of the legislation
- `downloaded_at`: Timestamp of when it was downloaded
- `data`: The actual API response data

## Configuration

You can modify these variables at the top of `scrape_legislation.py`:

- `API_BASE_URL`: The API endpoint URL
- `START_DATE`: The starting date (default: 1984-01-03)
- `OUTPUT_DIR`: Directory where data will be saved
- `DELAY_MONDAY`: Delay in seconds for Mondays when most legislation occurs (default: 1.0)
- `DELAY_OTHER_DAYS`: Delay in seconds for other days with typically no data (default: 0.2)

## Logs

Progress and errors are logged to:
- Console (stdout)
- `scrape_legislation.log` file
