import requests

def main():
    url = "http://172.16.10.38:3030/api/oauth/antigravity/start"
    headers = {
        "Authorization": "Bearer AnhNhi@0610"
    }
    
    print(f"Sending GET request to {url}...")
    try:
        import sys
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print("Response JSON:")
            import json
            print(json.dumps(data, ensure_ascii=False, indent=2))
            auth_url = data.get("auth_url")
            if auth_url:
                print("\nSuccessfully generated authorization URL!")
        else:
            print(f"Error: {resp.text}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    main()
