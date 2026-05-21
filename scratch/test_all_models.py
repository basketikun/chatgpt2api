import sys
import requests
import time
import json

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
    
    print("\n" + "="*50)
    print(f"TESTING MODEL: {model}")
    print(f"QUERY: {query}")
    print("="*50)
    
    start_time = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        elapsed = time.time() - start_time
        print(f"Status Code: {resp.status_code} (took {elapsed:.2f}s)")
        
        if resp.status_code == 200:
            data = resp.json()
            answer = data["choices"][0]["message"]["content"]
            print("\nANSWER:")
            print(answer)
        else:
            print("\nERROR RESPONSE:")
            print(resp.text)
    except Exception as e:
        print(f"\nRequest failed: {e}")

def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
        
    models = ["ag/auto", "chatgpt/auto", "cx/auto", "gemini_free/auto", "oc/auto"]
    query = "Hôm nay là ngày bao nhiêu? Giá vàng SJC hiện tại khoảng bao nhiêu?"
    
    for m in models:
        test_query(m, query)
        time.sleep(2)

if __name__ == "__main__":
    main()
