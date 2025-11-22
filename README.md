# Letterboxd Sync: TMDB & Trakt

A powerful toolset to sync your **Letterboxd** ratings and watched history to **The Movie Database (TMDB)** and **Trakt**.

## Features

### Core Capabilities
- **Letterboxd Data Download**: Automatically logs in and downloads your latest export data.
- **TMDB ID Resolution**: Scrapes Letterboxd pages to find the corresponding TMDB IDs for movies and TV shows.
- **Caching System**: Caches resolved IDs locally (`data/tmdb_id_cache.json`) to speed up future runs and minimize scraping.
- **Parallel Processing**: Uses multi-threading to resolve TMDB IDs quickly.

### Platform Support

#### 1. The Movie Database (TMDB)
- **Ratings Sync**: Imports your ratings to your TMDB account.
- **Smart Updates**: Checks your existing TMDB ratings first to avoid duplicates or unnecessary API calls.
- **Scale Conversion**: Automatically converts Letterboxd's 5-star scale to TMDB's 10-point scale.
- **Session Management**: Persists your session so you only authenticate once.

#### 2. Trakt.tv
- **Ratings & History**: Syncs both your ratings and your watched history.
- **Backdating**: Preserves the "Watched Date" from your Letterboxd diary entries.
- **Batch Syncing**: Uploads data in batches for efficiency.
- **Device Flow Auth**: Secure OAuth device flow authentication.

## Prerequisites

- **Python 3.9+**
- **Letterboxd Account**
- **TMDB Account** + API Key (free at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api))
- **Trakt Account** + API App (free at [trakt.tv/oauth/applications](https://trakt.tv/oauth/applications))

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/flaviod/letterboxd-sync.git
   cd letterboxd-sync
   ```

2. **Create a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Create a `.env` file in the project root with your credentials:

```env
# Letterboxd (Required for auto-download)
LETTERBOXD_USERNAME=your_username
LETTERBOXD_PASSWORD=your_password

# TMDB (Required for TMDB sync)
TMDB_API_KEY=your_tmdb_api_key

# Trakt (Required for Trakt sync)
TRAKT_CLIENT_ID=your_trakt_client_id
TRAKT_CLIENT_SECRET=your_trakt_client_secret

# Sync Configuration (for main.py)
SYNC_SERVICES=tmdb,trakt
```

## Usage

### Option 1: All-in-One Sync (Recommended)

Configure `SYNC_SERVICES` in your `.env` file (e.g., `tmdb,trakt`) and run:

```bash
python main.py
```

This will:
1. Download your latest Letterboxd data.
2. Resolve/Cache TMDB IDs.
3. Sync to all configured services sequentially.

### Option 2: Manual / Individual Steps

**1. Prepare Data:**
```bash
python letterbox_downloader.py
```
*Downloads export zip to `data/` and populates `data/tmdb_id_cache.json`.*

**2. Sync with TMDB:**
```bash
python tmdb.py
```

**3. Sync with Trakt:**
```bash
python trakt.py
```

## File Structure

- `main.py`: Main entry point that orchestrates the full sync process based on config.
- `letterbox_downloader.py`: Handles downloading export data and scraping/caching TMDB IDs.
- `tmdb.py`: Syncs data to TMDB.
- `trakt.py`: Syncs data to Trakt.
- `common.py`: Shared utilities and configuration.
- `data/`: Stores downloaded zips, cache files, and session tokens.

## Notes

- **Rate Limits**: The scripts include delays to respect API rate limits.
- **TV Shows**: Letterboxd recently added TV shows. This tool supports them by detecting the media type (movie/tv) during the scraping phase.
- **Manual Data**: If you prefer not to use your Letterboxd password, you can manually download your export zip, place it in the `data/` folder as `letterboxd-export.zip`, and run the scripts.
