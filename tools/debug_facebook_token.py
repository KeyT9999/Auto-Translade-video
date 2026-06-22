import os
import sys
import requests
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

load_dotenv()

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    
    token = os.getenv("FACEBOOK_PAGE_TOKEN") or os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
    if not token:
        print("ERROR: FACEBOOK_PAGE_TOKEN is not configured in .env")
        sys.exit(1)
        
    print("Debugging Facebook Token...")
    print(f"Token length: {len(token)}")
    print(f"Token prefix: {token[:10]}...")

    # 1. Get info about current node (me)
    try:
        me_url = f"https://graph.facebook.com/v20.0/me?access_token={token}"
        resp = requests.get(me_url)
        if resp.status_code == 200:
            me_data = resp.json()
            print(f"\n--- Token Node Info ---")
            print(f"Name: {me_data.get('name')}")
            print(f"ID: {me_data.get('id')}")
        else:
            print(f"\n--- Token Node Info Error ---")
            print(f"Status code: {resp.status_code}")
            print(f"Response: {resp.text}")
    except Exception as e:
        print(f"Failed to query /me: {e}")

    # 2. Get permissions
    try:
        perms_url = f"https://graph.facebook.com/v20.0/me/permissions?access_token={token}"
        resp = requests.get(perms_url)
        if resp.status_code == 200:
            perms_data = resp.json().get("data", [])
            print(f"\n--- Granted Permissions ---")
            active_perms = [p["permission"] for p in perms_data if p["status"] == "granted"]
            declined_perms = [p["permission"] for p in perms_data if p["status"] != "granted"]
            print(f"Granted: {', '.join(active_perms) if active_perms else 'None'}")
            if declined_perms:
                print(f"Declined/Expired: {', '.join(declined_perms)}")
        else:
            print(f"\n--- Permissions Query Error ---")
            print(f"Status code: {resp.status_code}")
            print(f"Response: {resp.text}")
    except Exception as e:
        print(f"Failed to query /me/permissions: {e}")

    # 3. Get accounts (pages) - only works if user token
    page_id_to_find = os.getenv("FACEBOOK_PAGE_ID")
    page_token_found = None
    try:
        accounts_url = f"https://graph.facebook.com/v20.0/me/accounts?access_token={token}"
        resp = requests.get(accounts_url)
        if resp.status_code == 200:
            accounts_data = resp.json().get("data", [])
            print(f"\n--- Pages accessible by this token (if User Token) ---")
            if not accounts_data:
                print("No pages found. This might be a Page Access Token already, or the user has no pages.")
            for acc in accounts_data:
                p_id = str(acc.get('id'))
                p_name = acc.get('name')
                p_token = acc.get('access_token')
                print(f"- Page Name: {p_name} | ID: {p_id}")
                print(f"  Permissions: {acc.get('tasks', [])}")
                print(f"  Access Token (truncated): {p_token[:15]}...")
                
                if page_id_to_find and p_id == str(page_id_to_find):
                    page_token_found = p_token
                    print(f"  => Match found! This is the token we need.")
        else:
            # If it's already a Page Access Token, /me/accounts might fail with permission or return empty/error.
            print(f"\n--- Accounts Query Response (Status {resp.status_code}) ---")
            print(f"Response: {resp.text}")
    except Exception as e:
        print(f"Failed to query /me/accounts: {e}")

    # 4. If a page token was found, automatically update .env
    if page_token_found:
        print(f"\nUpdating .env with the actual Page Access Token...")
        env_path = os.path.join(REPO_ROOT, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            updated = False
            for i, line in enumerate(lines):
                if line.startswith("FACEBOOK_PAGE_TOKEN="):
                    lines[i] = f"FACEBOOK_PAGE_TOKEN={page_token_found}\n"
                    updated = True
                    break
            
            if updated:
                with open(env_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                print("SUCCESS: Updated FACEBOOK_PAGE_TOKEN in .env with the Page Access Token!")
            else:
                print("WARNING: Could not find FACEBOOK_PAGE_TOKEN line in .env to update.")
        else:
            print("ERROR: .env file not found.")

if __name__ == "__main__":
    main()
