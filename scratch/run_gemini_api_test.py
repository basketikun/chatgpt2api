import json

def main():
    try:
        with open("/opt/chatgpt2api-data/accounts.json", "r") as f:
            accounts = json.load(f)
            
        gemini_keys = [a.get("access_token") for a in accounts if "gemini" in str(a.get("type")) and a.get("status") == "active"]
        print("Found active Gemini keys:", [k[:10] + "..." for k in gemini_keys if k])
        
        if gemini_keys:
            print("\nUsing key:", gemini_keys[0][:10] + "...")
            import subprocess
            subprocess.run(["uv", "run", "scratch/test_gemini_api_search.py", gemini_keys[0]])
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
