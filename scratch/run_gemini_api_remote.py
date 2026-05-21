import paramiko
import json

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610", timeout=10)
        
        stdin, stdout, stderr = ssh.exec_command("cat /opt/chatgpt2api-data/config.json")
        config_data = stdout.read().decode('utf-8')
        config = json.loads(config_data)
        
        gemini_key = (config.get("providers") or {}).get("gemini_free", {}).get("api_key")
        if not gemini_key:
            print("No Gemini key in config.json")
            return
            
        print(f"Testing with key from config: {gemini_key[:10]}...")
        
        test_script = f"""
import urllib.request
import json

url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro-latest:generateContent?key={gemini_key}'
headers = {{'Content-Type': 'application/json'}}

print('--- Test 1: googleSearch ---')
body1 = json.dumps({{
    "contents": [{{"role": "user", "parts": [{{"text": "thời tiết hà nội"}}]}}],
    "tools": [{{"googleSearch": {{}}}}]
}}).encode('utf-8')
try:
    req = urllib.request.Request(url, data=body1, headers=headers)
    resp1 = urllib.request.urlopen(req)
    print(resp1.getcode())
    print(resp1.read().decode('utf-8')[:300])
except Exception as e:
    print(e)
    if hasattr(e, 'read'): print(e.read().decode('utf-8')[:300])

print('\\n--- Test 2: googleSearchRetrieval ---')
body2 = json.dumps({{
    "contents": [{{"role": "user", "parts": [{{"text": "thời tiết hà nội"}}]}}],
    "tools": [{{"googleSearchRetrieval": {{}}}}]
}}).encode('utf-8')
try:
    req2 = urllib.request.Request(url, data=body2, headers=headers)
    resp2 = urllib.request.urlopen(req2)
    print(resp2.getcode())
    print(resp2.read().decode('utf-8')[:300])
except Exception as e:
    print(e)
    if hasattr(e, 'read'): print(e.read().decode('utf-8')[:300])
"""
        stdin, stdout, stderr = ssh.exec_command(f'docker exec chatgpt2api python -c "{test_script.replace('"', '\\"').replace('$', '\\$')}"')
        print(stdout.read().decode('utf-8'))
        err = stderr.read().decode('utf-8')
        if err:
            print("Errors:", err)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
