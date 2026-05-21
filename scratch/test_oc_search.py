import requests
import json
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

def test_query(model: str, query: str):
    url = "http://172.16.10.38:3030/v1/chat/completions"
    headers = {
        "Authorization": "Bearer AnhNhi@0610",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": query}
        ],
        "stream": False
    }
    
    print(f"\nTESTING MODEL: {model}")
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    print(f"Status Code: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        print(data["choices"][0]["message"]["content"])
    else:
        print(resp.text)

if __name__ == "__main__":
    test_query("oc/auto", "giá vàng hôm nay")
    test_query("cx/auto", "giá vàng hôm nay")
