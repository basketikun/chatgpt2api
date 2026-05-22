import sys
import requests
import time

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
    
    print("\n" + "="*60)
    print(f"TESTING MODEL: {model}")
    print(f"QUERY: {query}")
    print("="*60)
    
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
        
    model = "cx/auto"
    
    print(f"BẮT ĐẦU TEST {model}...")
    
    # Test 1: Khả năng chat thông thường
    test_query(model, "Xin chào, bạn là AI gì và bạn có thể làm được những gì? Trả lời ngắn gọn.")
    
    # Test 2: Khả năng tìm kiếm (để chứng minh nó không có internet)
    test_query(model, "Thời tiết tại Hà Nội hôm nay thế nào?")
    
    # Test 3: Khả năng lập trình / tư duy logic
    test_query(model, "Viết một hàm Python tính giai thừa của một số n.")

if __name__ == "__main__":
    main()
