import requests
import zipfile
import io
import re
import os
import csv
import json
import time
import sys
import concurrent.futures
from bs4 import BeautifulSoup

# Headers for scraping to mimic a browser and avoid blocking
SCRAPER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "DNT": "1"
}

DATA_DIR = "data"
CACHE_FILE = os.path.join(DATA_DIR, "tmdb_id_cache.json")

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

def get_tmdb_id_from_url(letterboxd_url, cache=None):
    """
    Resolves a Letterboxd URL to a TMDB ID and Type.
    Uses caching to avoid repeated requests.
    cache parameter is optional to allow thread-safe usage without modifying shared dict in place
    (though for read check it is fine).
    """
    if not letterboxd_url:
        return None, None

    # Check cache first if provided
    if cache and letterboxd_url in cache:
        cached_data = cache[letterboxd_url]
        return cached_data.get("id"), cached_data.get("type")

    # print(f"Scraping {letterboxd_url}...") # Verbose
    
    try:
        response = requests.get(letterboxd_url, headers=SCRAPER_HEADERS)
        if response.status_code != 200:
            print(f"  Warning: Failed to fetch URL {letterboxd_url} (Status: {response.status_code})")
            return None, None

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for the TMDB button/link
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
                
                # Return data, let caller handle cache update
                return tmdb_id, api_media_type
            else:
                print(f"  Warning: TMDB link found on {letterboxd_url} but could not parse ID/Type")
        else:
            print(f"  Warning: No TMDB link found on page {letterboxd_url}")

    except Exception as e:
        print(f"  Error scraping {letterboxd_url}: {e}")
    
    return None, None

def download_letterboxd_data(username, password, output_dir="data"):
    """
    Logs in to Letterboxd and downloads the data export zip.
    Returns the file path to the saved zip file or None.
    """
    # Ensure output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    print(f"\nAttempting to download Letterboxd data for user '{username}'...")
    session = requests.Session()
    session.headers.update(SCRAPER_HEADERS)
    
    # 1. Get login page for CSRF
    login_url = "https://letterboxd.com/sign-in/"
    try:
        r = session.get(login_url)
        if r.status_code != 200:
            print("Error: Failed to load login page")
            return None
            
        soup = BeautifulSoup(r.text, 'html.parser')
        form = soup.find('form', id='signin-form') or soup.find('form') # Fallback
        if not form:
            print("Error: Could not find login form")
            return None
            
        csrf_tag = form.find('input', {'name': '__csrf'})
        if not csrf_tag:
             print("Error: Could not find CSRF token")
             return None
             
        csrf = csrf_tag.get('value')
        
        # 2. Post login
        post_url = "https://letterboxd.com/user/login.do"
        data = {
            "username": username,
            "password": password,
            "__csrf": csrf,
            "remember": "true",
            "authenticationCode": "" # Try empty
        }
        
        r = session.post(post_url, data=data)
        
        # Check for successful login (Letterboxd usually redirects to homepage or user profile)
        if "sign-in" in r.url or r.status_code != 200: 
             # If still on sign-in page, likely failed.
             print("Error: Login failed. Check your username and password.")
             return None
             
        print("✓ Logged in to Letterboxd!")
        
        # 3. Go to export page
        export_page_url = "https://letterboxd.com/data/export/"
        print("Requesting export page...")
        r = session.get(export_page_url)
        
        if r.status_code != 200:
             print("Error: Failed to access export page")
             return None
        
        # Check content-type to see if we got the zip directly
        content_type = r.headers.get('Content-Type', '').lower()
        is_zip_header = 'zip' in content_type or 'octet-stream' in content_type
        
        # Check for magic bytes (PK..)
        is_zip_magic = r.content.startswith(b'PK\x03\x04')

        if is_zip_header or is_zip_magic:
             print("Got zip file directly from export page URL (detected via headers or magic bytes).")
             download_url = export_page_url
             file_content = r.content
        else:
             # Parse page to find the link
             soup = BeautifulSoup(r.text, 'html.parser')
             
             # Try finding the link again with better heuristic
             download_url = None
             
             # Look for any link that href contains 'export' and ends in 'zip'
             for a in soup.find_all('a', href=True):
                 href = a['href']
                 if 'data/export' in href and href.endswith('.zip'):
                     download_url = href
                     break
             
             if not download_url:
                 # Try finding a link that says "Download"
                 for a in soup.find_all('a', href=True):
                     if "download" in a.text.lower() and "export" in a['href']:
                         download_url = a['href']
                         break
             
             if not download_url:
                  print("Error: Could not find download link. Dumping page for debug...")
                  # Write page to file for inspection if running locally
                  with open("debug_export_page.html", "w") as f:
                      f.write(r.text)
                  print("Saved export page to debug_export_page.html")
                  return None
             
             if not download_url.startswith('http'):
                download_url = "https://letterboxd.com" + download_url

             print(f"Downloading export from {download_url}...")
             r = session.get(download_url, stream=True)
             if r.status_code != 200:
                 print(f"Error downloading file: {r.status_code}")
                 return None
             file_content = r.content

        # 4. Save zip
        zip_filename = "letterboxd-export.zip"
        zip_path = os.path.join(output_dir, zip_filename)
        
        try:
            # Verify it's a valid zip first
            z = zipfile.ZipFile(io.BytesIO(file_content))
            if z.testzip() is not None:
                print("Error: Downloaded zip file is corrupted.")
                return None
                
            with open(zip_path, "wb") as f:
                f.write(file_content)
            
            print(f"✓ Saved export to {zip_path}")
            return zip_path
                 
        except zipfile.BadZipFile:
            print("Error: Downloaded file is not a valid zip.")
            return None
            
    except Exception as e:
        print(f"Error during Letterboxd download: {e}")
        import traceback
        traceback.print_exc()
        return None

def scrape_worker(url):
    """
    Worker function for parallel scraping.
    Returns (url, tmdb_id, media_type) or None on failure.
    """
    # We don't pass the cache here because we want to avoid lock contention in workers,
    # or just simple independent scraping. We can check cache in the main loop before submitting.
    tmdb_id, media_type = get_tmdb_id_from_url(url, cache=None)
    if tmdb_id:
        return (url, tmdb_id, media_type)
    return None

def process_letterboxd_export(zip_path):
    """
    Extracts ratings from the downloaded zip and scrapes TMDB IDs for all items.
    Uses parallel execution for scraping.
    """
    print(f"\nProcessing export file: {zip_path}")
    cache = load_cache()
    initial_cache_size = len(cache)
    
    rows = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            # Find ratings.csv
            ratings_filename = None
            for name in z.namelist():
                if "ratings.csv" in name:
                    ratings_filename = name
                    break
            
            if not ratings_filename:
                 print("Error: ratings.csv not found in zip file.")
                 return
            
            print(f"Found {ratings_filename}. Reading entries...")
            with z.open(ratings_filename) as f:
                with io.TextIOWrapper(f, encoding='utf-8') as text_file:
                    reader = csv.DictReader(text_file)
                    rows = list(reader)
                    
        total_rows = len(rows)
        print(f"Found {total_rows} ratings to process.\n")
        
        # Identify items needing scraping
        to_scrape = []
        for i, row in enumerate(rows):
            col_uri = 'Letterboxd URI' if 'Letterboxd URI' in row else 'URL'
            col_title = 'Name' if 'Name' in row else 'Title'
            
            uri = row.get(col_uri)
            title = row.get(col_title, "Unknown Title")
            
            if not uri:
                continue
                
            # Check if already in cache
            if uri not in cache:
                to_scrape.append((uri, title))
        
        total_to_scrape = len(to_scrape)
        print(f"Items needing scraping: {total_to_scrape}")
        
        if total_to_scrape == 0:
            print("All items already cached.")
            return

        # Parallel Execution
        MAX_WORKERS = 10
        print(f"Starting scraping with {MAX_WORKERS} threads...")
        
        count_new = 0
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Create a map of futures to their URLs
            future_to_url = {
                executor.submit(scrape_worker, uri): (uri, title) 
                for uri, title in to_scrape
            }
            
            for i, future in enumerate(concurrent.futures.as_completed(future_to_url)):
                uri, title = future_to_url[future]
                try:
                    result = future.result()
                    if result:
                        _, tmdb_id, media_type = result
                        cache[uri] = {
                            "id": tmdb_id,
                            "type": media_type
                        }
                        count_new += 1
                        # print(f"[{i+1}/{total_to_scrape}] Resolved: {title}")
                    else:
                        print(f"[{i+1}/{total_to_scrape}] Failed to resolve: {title}")
                        
                    # Periodic save and status update
                    if (i + 1) % 10 == 0:
                        print(f"Progress: {i+1}/{total_to_scrape} ({count_new} found)...")
                        save_cache(cache)
                        
                except Exception as exc:
                    print(f"Generated an exception for {title}: {exc}")

    except Exception as e:
        print(f"Error processing export: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if len(cache) > initial_cache_size:
            print(f"\nSaving updated cache with {len(cache) - initial_cache_size} new entries...")
            save_cache(cache)
        else:
            print("\nCache is up to date.")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    username = os.environ.get("LETTERBOXD_USERNAME")
    password = os.environ.get("LETTERBOXD_PASSWORD")
    
    if not username or not password:
        print("Error: LETTERBOXD_USERNAME and LETTERBOXD_PASSWORD env vars required.")
        sys.exit(1)
    
    zip_path = download_letterboxd_data(username, password)
    
    if zip_path:
        process_letterboxd_export(zip_path)
