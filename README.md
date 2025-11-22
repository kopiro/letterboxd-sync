# Letterboxd to TMDb Ratings Importer

This script allows you to import your Letterboxd ratings into your TMDb (The Movie Database) account. It parses your Letterboxd export file, resolves the movies and TV shows to their TMDb IDs, and applies your ratings to your TMDb account.

## Features

- **Movies & TV Support:** Handles both movies and TV shows.
- **Smart Caching:** Caches TMDb IDs to avoid repeated scraping of Letterboxd pages.
- **Duplicate Prevention:** Checks your existing TMDb ratings to avoid re-rating items you've already rated.
- **Session Management:** Saves your TMDb session so you only need to authenticate once.

## Prerequisites

- Python 3.6 or higher
- A [TMDb Account](https://www.themoviedb.org/)
- A [TMDb API Key](https://www.themoviedb.org/settings/api) (free to generate)
- Your Letterboxd export data (`ratings.csv`)

## Installation

1. **Clone the repository** (or download the files):
   ```bash
   git clone <repository-url>
   cd letterboxd-to-tmdb
   ```

2. **Set up a virtual environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. **Credentials:**
   Create a `.env` file in the project root with the following:
   ```
   TMDB_API_KEY=your_api_key_here
   # Optional: For automatic Letterboxd export download
   LETTERBOXD_USERNAME=your_username
   LETTERBOXD_PASSWORD=your_password
   ```

2. **Letterboxd Data:**
   - **Automatic:** If you provide your Letterboxd credentials in `.env`, the script will automatically login and download your latest data to the `data/` directory.
   - **Manual:** 
     - Export your data from Letterboxd (Settings > Import & Export > Export Data).
     - You can pass the downloaded ZIP file directly to the script:
       ```bash
       python main.py path/to/letterboxd-export.zip
       ```
     - Or extract `ratings.csv` and run normally.

## Usage

Run the script:

```bash
python main.py
```

Or specify a different input file (CSV or ZIP):

```bash
python main.py path/to/your/ratings.csv
# OR
python main.py path/to/letterboxd-export.zip
```

### First Run
On the first run, the script will:
1. Ask for your TMDb API Key (if not in `.env`).
2. generate a Request Token.
3. Ask you to visit a URL to approve the application.
4. Generate and save a Session ID (`data/tmdb_session.json`).

### Subsequent Runs
The script will reuse the saved session and ID cache.

## Files

- `main.py`: The main script.
- `requirements.txt`: Python dependencies.
- `data/tmdb_session.json`: Stores your TMDb session ID (generated after login).
- `data/tmdb_id_cache.json`: Cache file mapping Letterboxd URLs to TMDb IDs (generated during run).
- `ratings.csv` or `letterboxd-export.zip`: Your Letterboxd export data (input).

## Note
Letterboxd ratings are on a scale of 0.5-5, while TMDb uses 1-10. The script sends the rating value directly from the CSV (which is usually 0.5-5 in the export). TMDb API accepts values from 0.5 to 10.0.

