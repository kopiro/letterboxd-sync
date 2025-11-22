import os
import sys
import requests
import time
import json
import common

# Configuration
TRAKT_API_URL = "https://api.trakt.tv"
SESSION_FILE = os.path.join(common.DATA_DIR, "trakt_session.json")

def load_session():
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load session file: {e}")
    return None

def save_session(data):
    try:
        with open(SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f"Session saved to {SESSION_FILE}")
    except Exception as e:
        print(f"Warning: Could not save session file: {e}")

def authenticate(client_id, client_secret):
    """
    Authenticates with Trakt using Device Flow.
    """
    session = load_session()
    if session and session.get("access_token"):
        # TODO: Check expiration and refresh if needed
        # specific check for expiry if available in session data
        # For now, assume valid if present, or let API fail and re-auth
        print(f"Loaded Session from {SESSION_FILE}")
        return session

    print("\n--- Trakt Authentication Required ---")
    
    # Step 1: Get Device Code
    url = f"{TRAKT_API_URL}/oauth/device/code"
    headers = {"Content-Type": "application/json"}
    data = {"client_id": client_id}
    
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code != 200:
            print(f"Error getting device code: {response.text}")
            return None
            
        code_data = response.json()
        device_code = code_data["device_code"]
        user_code = code_data["user_code"]
        verification_url = code_data["verification_url"]
        interval = code_data["interval"]
        expires_in = code_data["expires_in"]
        
        print(f"\nPlease visit: {verification_url}")
        print(f"Enter this code: {user_code}")
        
        # Poll for token
        print("Waiting for authorization...", end="", flush=True)
        
        token_url = f"{TRAKT_API_URL}/oauth/device/token"
        poll_data = {
            "code": device_code,
            "client_id": client_id,
            "client_secret": client_secret
        }
        
        start_time = time.time()
        while time.time() - start_time < expires_in:
            time.sleep(interval)
            print(".", end="", flush=True)
            
            r = requests.post(token_url, json=poll_data, headers=headers)
            if r.status_code == 200:
                print("\nAuthentication successful!")
                token_data = r.json()
                save_session(token_data)
                return token_data
            elif r.status_code == 400:
                # Pending
                continue
            elif r.status_code == 404:
                print("\nInvalid device code.")
                return None
            elif r.status_code == 409:
                print("\nAlready used.")
                return None
            elif r.status_code == 410:
                print("\nExpired.")
                return None
            elif r.status_code == 418:
                print("\nDenied.")
                return None
            else:
                print(f"\nError: {r.status_code} {r.text}")
                return None
                
    except Exception as e:
        print(f"\nError during authentication: {e}")
        return None

def get_headers(client_id, access_token):
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "trakt-api-version": "2",
        "trakt-api-key": client_id
    }

def sync_ratings_batch(client_id, access_token, batch):
    """
    Sends a batch of ratings to Trakt.
    batch is a dict with 'movies' and 'shows' lists.
    """
    url = f"{TRAKT_API_URL}/sync/ratings"
    headers = get_headers(client_id, access_token)
    
    try:
        r = requests.post(url, headers=headers, json=batch)
        if r.status_code in [200, 201]:
            data = r.json()
            added = data.get("added", {})
            not_found = data.get("not_found", {})
            print(f"✓ Synced Ratings: Movies: {added.get('movies')} added, Shows: {added.get('shows')} added")
            if not_found.get("movies") or not_found.get("shows"):
                print(f"  Warning: Some items not found: {not_found}")
            return True
        else:
            print(f"✗ Failed to sync ratings batch: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        print(f"✗ Error syncing ratings batch: {e}")
        return False

def sync_history_batch(client_id, access_token, batch):
    """
    Sends a batch of history (watched status) to Trakt.
    batch is a dict with 'movies' and 'shows' lists.
    """
    url = f"{TRAKT_API_URL}/sync/history"
    headers = get_headers(client_id, access_token)
    
    try:
        r = requests.post(url, headers=headers, json=batch)
        if r.status_code in [200, 201]:
            data = r.json()
            added = data.get("added", {})
            print(f"✓ Synced History: Movies: {added.get('movies')} added, Shows: {added.get('shows')} added")
            return True
        else:
            print(f"✗ Failed to sync history batch: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        print(f"✗ Error syncing history batch: {e}")
        return False

def sync_trakt(csv_file_path=None):
    print("--- Trakt Ratings Importer (Letterboxd Edition) ---")
    
    if not csv_file_path:
        csv_file_path = "ratings.csv"
        if len(sys.argv) > 1:
            csv_file_path = sys.argv[1]
        # Setup data
        csv_file_path = common.setup_letterboxd_export(csv_file_path)
    
    # Env vars
    client_id = common.get_env_variable("TRAKT_CLIENT_ID")
    client_secret = common.get_env_variable("TRAKT_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        print("Error: TRAKT_CLIENT_ID and TRAKT_CLIENT_SECRET are required in .env")
        return False
        
    # Auth
    auth_data = authenticate(client_id, client_secret)
    if not auth_data:
        return False
        
    access_token = auth_data["access_token"]
    
    # Cache
    cache = common.load_cache()
    initial_cache_size = len(cache)
    
    print(f"\nReading ratings from {csv_file_path}...")
    rows = common.read_csv_rows(csv_file_path)
    print(f"Found {len(rows)} ratings to process.\n")
    
    # Prepare batches
    batch_movies_rating = []
    batch_shows_rating = []
    
    batch_movies_history = []
    batch_shows_history = []
    
    # Config
    BATCH_SIZE = 50
    
    count_processed = 0
    count_queued = 0
    
    try:
        for i, row in enumerate(rows):
            parsed = common.parse_csv_row(row)
            if not parsed:
                continue
                
            uri = parsed['uri']
            title = parsed['title']
            rating = parsed['rating']
            
            tmdb_id, media_type = common.get_tmdb_id_from_url(uri, cache)
            
            if tmdb_id and media_type:
                tmdb_id = str(tmdb_id)
                tmdb_rating = int(float(rating) * 2) # Trakt uses integer 1-10
                
                print(f"  Queueing '{title}': {tmdb_rating}")
                
                # 1. Rating Item
                rating_item = {
                    "ids": {"tmdb": int(tmdb_id)},
                    "rating": tmdb_rating,
                    "rated_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
                }
                
                # 2. History Item
                history_item = {
                    "ids": {"tmdb": int(tmdb_id)},
                    "watched_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
                }
                
                # Try to parse date from row if available
                if 'Date' in row:
                    try:
                         # Letterboxd Date: YYYY-MM-DD
                         date_str = row['Date']
                         formatted_date = f"{date_str}T12:00:00.000Z"
                         rating_item["rated_at"] = formatted_date
                         history_item["watched_at"] = formatted_date
                    except:
                        pass
                
                if media_type == "movie":
                    batch_movies_rating.append(rating_item)
                    batch_movies_history.append(history_item)
                else:
                    batch_shows_rating.append(rating_item)
                    batch_shows_history.append(history_item)
                    
                count_queued += 1
                
                # Flush if full
                if len(batch_movies_rating) >= BATCH_SIZE:
                    sync_ratings_batch(client_id, access_token, {"movies": batch_movies_rating})
                    sync_history_batch(client_id, access_token, {"movies": batch_movies_history})
                    count_processed += len(batch_movies_rating)
                    batch_movies_rating = []
                    batch_movies_history = []
                    time.sleep(1)
                    
                if len(batch_shows_rating) >= BATCH_SIZE:
                    sync_ratings_batch(client_id, access_token, {"shows": batch_shows_rating})
                    sync_history_batch(client_id, access_token, {"shows": batch_shows_history})
                    count_processed += len(batch_shows_rating)
                    batch_shows_rating = []
                    batch_shows_history = []
                    time.sleep(1)
            
            # Save cache periodically
            if (i + 1) % 20 == 0:
                common.save_cache(cache)
                
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return False
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Flush remaining
        if batch_movies_rating:
            print(f"Syncing remaining {len(batch_movies_rating)} movies...")
            sync_ratings_batch(client_id, access_token, {"movies": batch_movies_rating})
            sync_history_batch(client_id, access_token, {"movies": batch_movies_history})

        if batch_shows_rating:
            print(f"Syncing remaining {len(batch_shows_rating)} shows...")
            sync_ratings_batch(client_id, access_token, {"shows": batch_shows_rating})
            sync_history_batch(client_id, access_token, {"shows": batch_shows_history})
            
        if len(cache) > initial_cache_size:
            print("Saving cache...")
            common.save_cache(cache)

    print("\nDone.")
    return True

if __name__ == "__main__":
    sync_trakt()
