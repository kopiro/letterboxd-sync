import os
import json
import csv
import sys
import zipfile
import io
from dotenv import load_dotenv
from letterbox_downloader import download_letterboxd_data, SCRAPER_HEADERS, get_tmdb_id_from_url

# Load environment variables
load_dotenv()

DATA_DIR = "data"
CACHE_FILE = os.path.join(DATA_DIR, "tmdb_id_cache.json")

# Ensure data directory exists
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def get_env_variable(var_name):
    return os.environ.get(var_name)

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load cache file: {e}")
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save cache file: {e}")

def setup_letterboxd_export(csv_file_path="ratings.csv"):
    """
    Checks for Letterboxd export file. Downloads if credentials are set and file missing.
    Returns valid file path or exits if failed.
    """
    # Check for CLI arg first (handled by caller usually, but we can allow override)
    # Here we assume csv_file_path is the default or passed arg.
    
    # Always try to download if credentials are present and file doesn't exist or we want to update?
    # For now, consistent with previous logic: download if credentials present.
    lb_user = get_env_variable("LETTERBOXD_USERNAME")
    lb_pass = get_env_variable("LETTERBOXD_PASSWORD")
    
    # Determine file path. Ideally should be consistent with where downloader saves it.
    # The downloader saves to "letterboxd-export.zip" inside DATA_DIR usually.
    # But here we respect the csv_file_path arg if provided.
    
    default_export_path = os.path.join(DATA_DIR, "letterboxd-export.zip")
    
    if lb_user and lb_pass:
         # Only download if not existing? Or if requested? 
         # The previous logic was somewhat implicit.
         # If we rely on letterbox_downloader.py to be the main entry point for downloading/caching,
         # then here we should just check for the file.
         
         # However, to maintain compatibility:
         # If the file doesn't exist, try to download it.
         if not os.path.exists(csv_file_path):
             print("Downloading Letterboxd data...")
             # We use the module function directly, but wait!
             # If we want to FORCE cache population as per request "Remove this functionality elsewhere but here",
             # we should rely on letterbox_downloader being run SEPARATELY or call its main logic?
             # The user said "Make sure that when I run python letterbox_downloader.py I also scrape and download... Remove this functionality elsewhere"
             
             # So here in common/tmdb/trakt, we should probably NOT be downloading anymore?
             # Or at least, if we do download, we should use the shared function but maybe NOT do the scraping here?
             # The scraping happens inside get_tmdb_id_from_url which IS shared.
             
             # The user wants "python letterbox_downloader.py" to be the one-stop-shop for getting data ready (download + cache).
             # So scripts like tmdb.py and trakt.py should probably just EXPECT the data to be ready or fail gracefully/ask user to run downloader.
             
             # But convenience is nice. Let's keep the download trigger if missing, but rely on the cache which letterbox_downloader populates.
             downloaded_file = download_letterboxd_data(lb_user, lb_pass, DATA_DIR)
             if downloaded_file:
                 return downloaded_file
    elif not os.path.exists(csv_file_path):
         print("Tip: Set LETTERBOXD_USERNAME and LETTERBOXD_PASSWORD in .env to auto-download data.")
         print("Or run 'python letterbox_downloader.py' to prepare data.")
    
    if not os.path.exists(csv_file_path):
        print(f"Error: File '{csv_file_path}' not found.")
        print("Please run 'python letterbox_downloader.py' first to download and prepare your data.")
        sys.exit(1)
        
    return csv_file_path

def read_csv_rows(csv_file_path):
    """
    Reads rows from a CSV file, handling zip files if necessary.
    Returns a list of dicts.
    """
    rows = []
    try:
        if zipfile.is_zipfile(csv_file_path):
             print(f"Extracting data from zip archive: {csv_file_path}")
             with zipfile.ZipFile(csv_file_path, 'r') as z:
                # Find ratings.csv
                ratings_filename = None
                for name in z.namelist():
                    if "ratings.csv" in name:
                        ratings_filename = name
                        break
                
                if not ratings_filename:
                     print("Error: ratings.csv not found in zip file.")
                     sys.exit(1)
                
                with z.open(ratings_filename) as f:
                    with io.TextIOWrapper(f, encoding='utf-8') as text_file:
                        reader = csv.DictReader(text_file)
                        rows = list(reader)
        else:
            with open(csv_file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
    except Exception as e:
        print(f"Error reading CSV data: {e}")
        sys.exit(1)
        
    return rows

def parse_csv_row(row):
    """
    Extracts standard fields from a Letterboxd CSV row.
    Returns (title, year, uri, rating)
    """
    col_uri = 'Letterboxd URI' if 'Letterboxd URI' in row else 'URL'
    col_rating = 'Rating' if 'Rating' in row else 'Your Rating'
    col_title = 'Name' if 'Name' in row else 'Title'
    col_year = 'Year'
    
    if col_uri not in row or col_rating not in row:
        return None
        
    uri = row.get(col_uri)
    title = row.get(col_title, "Unknown Title")
    rating = row.get(col_rating)
    year = row.get(col_year)
    
    return {
        "title": title,
        "year": year,
        "uri": uri,
        "rating": rating
    }
