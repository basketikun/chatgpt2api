import requests
import json
import sys

def main():
    api_key = sys.argv[1] if len(sys.argv) > 1 else ""
    if not api_key:
        print("Please provide Gemini API key")
        return
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={api_key}"
    
    # Test 1: googleSearch
    body1 = {
        "contents": [{"role": "user", "parts": [{"text": "thời tiết hà nội"}]}],
        "tools": [{"googleSearch": {}}]
    }
    resp1 = requests.post(url, headers={"Content-Type": "application/json"}, json=body1)
    print("Test 1 googleSearch status:", resp1.status_code)
    print(resp1.text[:200])
    
    # Test 2: googleSearchRetrieval
    body2 = {
        "contents": [{"role": "user", "parts": [{"text": "thời tiết hà nội"}]}],
        "tools": [{"googleSearchRetrieval": {}}]
    }
    resp2 = requests.post(url, headers={"Content-Type": "application/json"}, json=body2)
    print("\nTest 2 googleSearchRetrieval status:", resp2.status_code)
    print(resp2.text[:200])

if __name__ == "__main__":
    main()
