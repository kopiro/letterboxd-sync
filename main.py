import os
import sys
import common
from dotenv import load_dotenv
import tmdb
import trakt
import letterbox_downloader

def main():
    load_dotenv()
    
    # 1. Read config
    sync_services = os.environ.get("SYNC_SERVICES", "")
    services = [s.strip().lower() for s in sync_services.split(",") if s.strip()]
    
    if not services:
        print("No services configured in SYNC_SERVICES. Please add 'tmdb' or 'trakt' to your .env file.")
        print("Example: SYNC_SERVICES=tmdb,trakt")
        sys.exit(1)
        
    print(f"Enabled sync services: {', '.join(services)}")
    
    # 2. Prepare Data (Download & Scrape)
    # This ensures we have the latest data and populated cache before running syncs.
    lb_user = os.environ.get("LETTERBOXD_USERNAME")
    lb_pass = os.environ.get("LETTERBOXD_PASSWORD")
    
    csv_file_path = "ratings.csv" # default fallback
    
    if lb_user and lb_pass:
        print("\n=== Step 1: Preparing Data ===")
        zip_path = letterbox_downloader.download_letterboxd_data(lb_user, lb_pass, common.DATA_DIR)
        
        if zip_path:
            # Run the bulk scraper to populate/warm up the cache
            # This is more efficient than letting tmdb/trakt scripts do it sequentially
            letterbox_downloader.process_letterboxd_export(zip_path)
            csv_file_path = zip_path
        else:
            print("Warning: Download failed. checking for existing files...")
            if not os.path.exists(csv_file_path) and not os.path.exists(os.path.join(common.DATA_DIR, "letterboxd-export.zip")):
                 print("Error: No data file found.")
                 sys.exit(1)
    else:
        print("\n=== Step 1: Checking Data ===")
        # Check if a zip exists in data dir
        default_zip = os.path.join(common.DATA_DIR, "letterboxd-export.zip")
        if os.path.exists(default_zip):
             print(f"Using existing zip: {default_zip}")
             csv_file_path = default_zip
             # We can optionally run scraping here too if user wants to ensure cache is fresh?
             # But usually manual zip implies manual run. Let's do it to be safe/complete.
             print("Ensuring cache is populated...")
             letterbox_downloader.process_letterboxd_export(default_zip)
        elif os.path.exists(csv_file_path):
             print(f"Using local CSV: {csv_file_path}")
        else:
             print("Error: No data found. Configure credentials in .env or place 'ratings.csv'/'letterboxd-export.zip' in the folder.")
             sys.exit(1)

    # 3. Run Sync Services
    if "tmdb" in services:
        print("\n=== Step 2: Running TMDB Sync ===")
        tmdb.sync_tmdb(csv_file_path)
        
    if "trakt" in services:
        print("\n=== Step 3: Running Trakt Sync ===")
        trakt.sync_trakt(csv_file_path)
        
    print("\n=== All Operations Completed ===")

if __name__ == "__main__":
    main()

