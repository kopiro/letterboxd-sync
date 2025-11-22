import os
import sys
import requests
import time
import json
import common

# Configuration
tmdb_api_url = "https://api.themoviedb.org/3"
SESSION_FILE = os.path.join(common.DATA_DIR, "tmdb_session.json")

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
    
    # Setup data file (download or check existence)
    csv_file_path = common.setup_letterboxd_export(csv_file_path)

    # Get API Key
    api_key = common.get_env_variable("TMDB_API_KEY")
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
    cache = common.load_cache()
    initial_cache_size = len(cache)
    
    print(f"\nReading ratings from {csv_file_path}...")
    
    success_count = 0
    fail_count = 0
    
    try:
        rows = common.read_csv_rows(csv_file_path)
        total_rows = len(rows)
        print(f"Found {total_rows} ratings to process.\n")
        
        for i, row in enumerate(rows):
            parsed = common.parse_csv_row(row)
            
            if not parsed:
                # Could verify if it was a missing column or just invalid row, but this is fine
                # Actually parse_csv_row returns None if essential columns missing, which might imply bad CSV format
                # But here we iterate rows, so maybe check first row structure?
                # For simplicity we just skip invalid rows if any.
                # Wait, parse_csv_row returns None if uri or rating missing.
                print(f"Skipping row {i+1}: Missing URI or Rating")
                continue

            title = parsed['title']
            rating = parsed['rating']
            uri = parsed['uri']
            
            # Resolve ID
            tmdb_id, media_type = common.get_tmdb_id_from_url(uri, cache)
            
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
                time.sleep(0.5)
            else:
                print(f"✗ Could not find TMDB ID for '{title}' ({uri})")
                fail_count += 1
            
            # Save cache every 10 items to prevent data loss
            if (i + 1) % 10 == 0:
                common.save_cache(cache)
                
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if len(cache) > initial_cache_size:
            print("\nSaving updated cache...")
            common.save_cache(cache)
        
    print(f"\n--- Summary ---")
    print(f"Total processed: {success_count + fail_count}")
    print(f"Successful: {success_count}")
    print(f"Failed: {fail_count}")

if __name__ == "__main__":
    main()
