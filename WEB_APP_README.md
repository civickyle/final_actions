# Atlanta City Council Legislation Web Browser

An interactive web application to browse and search Atlanta City Council legislation data from 1984 to present.

## Features

- 🔍 **Full-text search** across all legislation descriptions
- 🔢 **Search by legislation number** (e.g., "84-R-15428")
- 📅 **Browse by date** with year and month navigation
- 📄 **View PDF documents** (when available)
- 📊 **Statistics** showing total meetings and legislation items
- 🎨 **Clean, modern interface** with responsive design

## Installation

Dependencies are already installed in the virtual environment. If starting fresh:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the App

1. **Activate the virtual environment:**
   ```bash
   source .venv/bin/activate
   ```

2. **Start the Flask server:**
   ```bash
   python app.py
   ```

3. **Open your browser to:**
   ```
   http://localhost:5000
   ```

The app will be accessible on your local network at `http://0.0.0.0:5000`

## Usage

### Search Functionality

1. **Search All Fields**: Searches both legislation number and description
2. **Search by Number**: Search for specific legislation numbers (e.g., "84-R-15428")
3. **Search by Description**: Full-text search in descriptions (e.g., "airport", "budget")

### Browse by Date

1. Click "Browse by Date" on the homepage
2. Select a year from the list
3. Select a specific date to view all legislation from that meeting
4. View details and click PDF links to see source documents

### Example Searches

- **"airport"** - Find all airport-related legislation
- **"budget"** - Find all budget-related items
- **"84-R-15428"** - Find specific legislation by number
- **"Underground Atlanta"** - Find mentions of Underground Atlanta project

## API Endpoints

The app provides a RESTful API:

### Get All Dates
```
GET /api/dates
```
Returns all available dates organized by year.

### Get Legislation by Date
```
GET /api/date/YYYY-MM-DD
```
Returns all legislation for a specific date.

### Search Legislation
```
GET /api/search?q=<query>&field=<all|number|description>
```
Search legislation with query and field filter.

## Data Source

The app reads from the `meeting_dates/` directory containing deduplicated, normalized legislation data in JSON format.

## Performance Notes

- Initial search may take a few seconds as it scans all JSON files
- Results are limited to 100 items for performance
- Browse by date is optimized for fast loading

## Stopping the App

Press `Ctrl+C` in the terminal to stop the Flask server.
