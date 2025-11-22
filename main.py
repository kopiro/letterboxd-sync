import csv
import os
import sys
import requests
import time
import json
import re
import zipfile
import io
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from letterboxd_downloader import download_letterboxd_data, SCRAPER_HEADERS

# Load environment variables
load_dotenv()

# Configuration
tmdb_api_url = "https://api.themoviedb.org/3"
CACHE_FILE = "tmdb_id_cache.json"
SESSION_FILE = "tmdb_session.json"

# Headers for scraping to mimic a browser and avoid blocking
# Moved to letterboxd_downloader.py


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

def load_session():
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("session_id")
        except Exception as e:
            print(f"Warning: Could not load session file: {e}")
    return None

def save_session(session_id):
    try:
        with open(SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump({"session_id": session_id}, f, indent=2)
        print(f"Session ID saved to {SESSION_FILE}")
    except Exception as e:
        print(f"Warning: Could not save session file: {e}")

def authenticate(api_key):
    """
    Authenticates with TMDB. Checks for saved session first.
    If not found, guides the user through the authentication flow to generate one.
    """
    # Try to load from file first
    session_id = load_session()
    if session_id:
        print(f"Loaded Session ID from {SESSION_FILE}")
        return session_id

    print("\n--- TMDB Authentication Required ---")
    print("A Session ID is required to rate movies on your behalf.")
    
    # Step 1: Create a Request Token
    response = requests.get(f"{tmdb_api_url}/authentication/token/new", params={"api_key": api_key})
    if response.status_code != 200:
        print(f"Error creating request token: {response.text}")
        sys.exit(1)
    
    request_token = response.json().get("request_token")
    
    # Step 2: Ask the user to authorize the token
    auth_url = f"https://www.themoviedb.org/authenticate/{request_token}"
    print(f"\nPlease visit the following URL to authorize this application:\n{auth_url}")
    input("\nAfter approving, press Enter to continue...")
    
    # Step 3: Create a Session ID
    response = requests.get(f"{tmdb_api_url}/authentication/session/new", 
                            params={"api_key": api_key, "request_token": request_token})
    
    if response.status_code != 200:
        print(f"Error creating session ID: {response.text}")
        sys.exit(1)
        
    session_id = response.json().get("session_id")
    print(f"\nAuthentication successful! Your Session ID is: {session_id}")
    
    # Save to file
    save_session(session_id)
    
    return session_id

def get_account_id(api_key, session_id):
    """
    Retrieves the user's account ID.
    """
    url = f"{tmdb_api_url}/account"
    params = {"api_key": api_key, "session_id": session_id}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json().get("id")
    return None

def get_existing_ratings(api_key, session_id, account_id, media_type="movies"):
    """
    Fetches all existing ratings for a user to avoid re-rating.
    media_type can be 'movies' or 'tv'.
    Returns a dictionary mapping {tmdb_id: rating}
    """
    print(f"Fetching existing {media_type} ratings...")
    ratings = {}
    page = 1
    total_pages = 1
    
    endpoint = "rated/movies" if media_type == "movies" else "rated/tv"
    
    while page <= total_pages:
        url = f"{tmdb_api_url}/account/{account_id}/{endpoint}"
        params = {
            "api_key": api_key,
            "session_id": session_id,
            "page": page
        }
        
        try:
            response = requests.get(url, params=params)
            if response.status_code != 200:
                print(f"Warning: Failed to fetch existing ratings page {page}")
                break
                
            data = response.json()
            results = data.get("results", [])
            total_pages = data.get("total_pages", 1)
            
            for item in results:
                tmdb_id = str(item.get("id"))
                rating = item.get("rating")
                ratings[tmdb_id] = rating
                
            print(f"  Fetched page {page}/{total_pages} ({len(ratings)} total found)")
            page += 1
            time.sleep(0.2)
            
        except Exception as e:
            print(f"Error fetching ratings: {e}")
            break
            
    return ratings

def get_tmdb_id_from_url(letterboxd_url, cache):
    """
    Resolves a Letterboxd URL to a TMDB ID and Type.
    Uses caching to avoid repeated requests.
    """
    if not letterboxd_url:
        return None, None

    # Check cache first
    # Cache key logic: Use the URL as the key for simplicity and reliability
    if letterboxd_url in cache:
        cached_data = cache[letterboxd_url]
        return cached_data.get("id"), cached_data.get("type")

    print(f"Scraping {letterboxd_url}...")
    
    try:
        response = requests.get(letterboxd_url, headers=SCRAPER_HEADERS)
        if response.status_code != 200:
            print(f"  Warning: Failed to fetch URL (Status: {response.status_code})")
            return None, None

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for the TMDB button/link
        # Selector: .micro-button[data-track-action="TMDB"]
        tmdb_link = soup.select_one('a.micro-button[data-track-action="TMDB"]')
        
        if tmdb_link and tmdb_link.get('href'):
            href = tmdb_link.get('href')
            # Regex to extract type and id: /(movie|tv)/(\d+)/
            match = re.search(r'/(movie|tv)/(\d+)/?', href)
            if match:
                media_type = match.group(1)
                tmdb_id = match.group(2)
                
                # Normalize type
                if media_type == "movie":
                    api_media_type = "movie"
                else:
                    api_media_type = "tv"
                
                # Update cache
                cache[letterboxd_url] = {
                    "id": tmdb_id,
                    "type": api_media_type
                }
                # Auto-save cache periodically or let the main loop handle it? 
                # Let's just return values and let main loop handle saving periodically if needed, 
                # but for safety we can dirty the cache object.
                return tmdb_id, api_media_type
            else:
                print("  Warning: TMDB link found but could not parse ID/Type")
        else:
            print("  Warning: No TMDB link found on page.")

    except Exception as e:
        print(f"  Error scraping: {e}")
    
    return None, None

def rate_item(api_key, session_id, tmdb_id, media_type, rating, title):
    """
    Rates a movie or TV show on TMDB.
    """
    endpoint = "movie" if media_type.lower() == "movie" else "tv"
    url = f"{tmdb_api_url}/{endpoint}/{tmdb_id}/rating"
    
    params = {
        "api_key": api_key,
        "session_id": session_id
    }
    
    headers = {
        "Content-Type": "application/json;charset=utf-8"
    }
    
    data = {
        "value": float(rating)
    }
    
    try:
        response = requests.post(url, params=params, headers=headers, json=data)
        
        if response.status_code in [200, 201, 12]: # 12 is "The item/record was updated successfully."
            print(f"✓ Rated '{title}' ({media_type}): {rating}")
            return True
        else:
            # Try to print error message from body
            try:
                err_msg = response.json().get('status_message', response.text)
            except:
                err_msg = response.text
            print(f"✗ Failed to rate '{title}': {response.status_code} - {err_msg}")
            return False
            
    except Exception as e:
        print(f"✗ Error rating '{title}': {str(e)}")
        return False


def main():
    print("--- TMDB Ratings Importer (Letterboxd Edition) ---")
    
    csv_file_path = "ratings.csv"
    
    # Check for CLI arg first
    if len(sys.argv) > 1:
        csv_file_path = sys.argv[1]
    
    # Always try to download if credentials are present
    lb_user = get_env_variable("LETTERBOXD_USERNAME")
    lb_pass = get_env_variable("LETTERBOXD_PASSWORD")
    
    if lb_user and lb_pass:
         downloaded_file = download_letterboxd_data(lb_user, lb_pass)
         if downloaded_file:
             csv_file_path = downloaded_file
    elif not os.path.exists(csv_file_path):
         print("Tip: Set LETTERBOXD_USERNAME and LETTERBOXD_PASSWORD in .env to auto-download data.")
    
    if not os.path.exists(csv_file_path):
        print(f"Error: File '{csv_file_path}' not found and could not be downloaded.")
        # For debugging, if download failed, maybe we can create a dummy one or just exit
        sys.exit(1)

    # Get API Key
    api_key = get_env_variable("TMDB_API_KEY")
    if not api_key:
        api_key = input("Enter your TMDB API Key: ").strip()
        if not api_key:
            print("API Key is required.")
            sys.exit(1)

    # Authenticate (manages session ID persistence)
    session_id = authenticate(api_key)
    
    # Get Account ID
    account_id = get_account_id(api_key, session_id)
    if not account_id:
        print("Error: Could not retrieve TMDB Account ID.")
        sys.exit(1)
        
    # Fetch existing ratings
    print("\nChecking existing ratings on TMDB...")
    existing_movie_ratings = get_existing_ratings(api_key, session_id, account_id, "movies")
    existing_tv_ratings = get_existing_ratings(api_key, session_id, account_id, "tv")
    
    # Load cache
    cache = load_cache()
    initial_cache_size = len(cache)
    
    print(f"\nReading ratings from {csv_file_path}...")
    
    success_count = 0
    fail_count = 0
    
    try:
        with open(csv_file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            total_rows = len(rows)
            print(f"Found {total_rows} ratings to process.\n")
            
            # Identify columns
            # Standard Letterboxd: Name, Year, Letterboxd URI, Rating
            # Or variant: Title, Year, Letterboxd URI, Your Rating
            first_row = rows[0] if rows else {}
            
            col_uri = 'Letterboxd URI' if 'Letterboxd URI' in first_row else 'URL'
            col_rating = 'Rating' if 'Rating' in first_row else 'Your Rating'
            col_title = 'Name' if 'Name' in first_row else 'Title'
            
            if col_uri not in first_row:
                print(f"Error: Could not find '{col_uri}' column in CSV.")
                sys.exit(1)
            if col_rating not in first_row:
                print(f"Error: Could not find '{col_rating}' column in CSV.")
                sys.exit(1)
            
            for i, row in enumerate(rows):
                uri = row.get(col_uri)
                title = row.get(col_title, "Unknown Title")
                rating = row.get(col_rating)
                
                if not uri or not rating:
                    print(f"Skipping row {i+1}: Missing URI or Rating")
                    continue
                
                # Resolve ID
                tmdb_id, media_type = get_tmdb_id_from_url(uri, cache)
                
                if tmdb_id and media_type:
                    tmdb_id = str(tmdb_id)
                    
                    # Check if already rated
                    already_rated = False
                    existing_rating = None
                    
                    if media_type == "movie":
                        if tmdb_id in existing_movie_ratings:
                            already_rated = True
                            existing_rating = existing_movie_ratings[tmdb_id]
                    else:
                        if tmdb_id in existing_tv_ratings:
                            already_rated = True
                            existing_rating = existing_tv_ratings[tmdb_id]
                    
                    if already_rated:
                        try:
                            # Compare existing rating with new rating
                            # Letterboxd CSV rating is 0-5, TMDB existing is 1-10.
                            # Multiply Letterboxd rating by 2 to get TMDB scale.
                            current_rating_val = float(rating) * 2
                            
                            # Check difference (handling potential float imprecision)
                            if abs(current_rating_val - existing_rating) < 0.1:
                                print(f"- Skipping '{title}' ({media_type}): Already rated {existing_rating}")
                                continue
                            else:
                                print(f"  Updating rating for '{title}' ({media_type}): {existing_rating} -> {current_rating_val}")
                        except ValueError:
                            print(f"Warning: Could not parse rating '{rating}' for comparison.")
                            pass

                    # Rate it
                    # Multiply rating by 2 before sending to TMDB
                    tmdb_rating = float(rating) * 2
                    if rate_item(api_key, session_id, tmdb_id, media_type, tmdb_rating, title):
                        success_count += 1
                    else:
                        fail_count += 1
                    
                    # Sleep to be nice to APIs
                    time.sleep(0.5) # Bit slower because we might be scraping too
                else:
                    print(f"✗ Could not find TMDB ID for '{title}' ({uri})")
                    fail_count += 1
                
                # Save cache every 10 items to prevent data loss
                if (i + 1) % 10 == 0:
                    save_cache(cache)
                
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if len(cache) > initial_cache_size:
            print("\nSaving updated cache...")
            save_cache(cache)
        
    print(f"\n--- Summary ---")
    print(f"Total processed: {success_count + fail_count}")
    print(f"Successful: {success_count}")
    print(f"Failed: {fail_count}")

if __name__ == "__main__":
    main()
