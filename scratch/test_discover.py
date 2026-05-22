import paramiko
import requests
import json

def main():
    # Make a POST request to the API
    url = "http://172.16.10.38:3030/api/mcp/discover"
    headers = {
        "Authorization": "Bearer AnhNhi@0610",
        "Content-Type": "application/json"
    }
    payload = {
        "hub_url": "http://172.16.10.38:8005"
    }
    
    try:
        print(f"POST {url}")
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"Status Code: {resp.status_code}")
        with open(r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\scratch\discover_resp.json", "w", encoding="utf-8") as f:
            json.dump(resp.json(), f, ensure_ascii=False, indent=2)
        print("Response saved to scratch/discover_resp.json")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    main()
