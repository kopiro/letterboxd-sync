import requests
import zipfile
import io
import re
import os
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

def download_letterboxd_data(username, password):
    """
    Logs in to Letterboxd and downloads the data export.
    Returns the file path to the extracted ratings.csv or None.
    """
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
        # The previous attempts failed because the export URL logic might be simpler or trickier.
        # Research suggests simply visiting https://letterboxd.com/data/export/ while logged in SHOULD trigger it?
        # Or maybe we need to verify if there is an intermediate page.
        
        # Let's try one more approach: 
        # It seems for some users it is /data/export/request ? No.
        
        # Let's do a more robust check on the export page content.
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

        # 4. Extract zip
        try:
            z = zipfile.ZipFile(io.BytesIO(file_content))
            # Look for ratings.csv
            csv_name = None
            for name in z.namelist():
                if "ratings.csv" in name:
                    csv_name = name
                    break
            
            if csv_name:
                print(f"Extracting {csv_name}...")
                z.extract(csv_name, ".")
                return csv_name
            else:
                 print("Error: ratings.csv not found in zip file.")
                 print(f"Contents: {z.namelist()}")
                 return None
                 
        except zipfile.BadZipFile:
            print("Error: Downloaded file is not a valid zip.")
            return None
            
    except Exception as e:
        print(f"Error during Letterboxd download: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    username = os.environ.get("LETTERBOXD_USERNAME")
    password = os.environ.get("LETTERBOXD_PASSWORD")
    
    if not username or not password:
        print("Error: LETTERBOXD_USERNAME and LETTERBOXD_PASSWORD env vars required.")
    else:
        download_letterboxd_data(username, password)
