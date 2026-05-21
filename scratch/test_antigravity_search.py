import json
import requests
import uuid

def main():
    import paramiko
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610")
    
    stdin, stdout, stderr = ssh.exec_command("docker exec chatgpt2api cat /app/data/accounts.json")
    accounts = json.loads(stdout.read().decode('utf-8'))
    ssh.close()
    
    ag_token = None
    for acc in accounts:
        if acc.get("type") and "antigravity" in acc.get("type") and acc.get("status") == "active":
            ag_token = acc["access_token"]
            break
            
    if not ag_token:
        print("No antigravity token found")
        return
        
    print("Testing Antigravity with googleSearch tool...")
    
    url = "https://cloudcode-pa.googleapis.com/v1internal:generateContent"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ag_token}",
        "User-Agent": "antigravity/1.107.0 Windows/x64",
    }
    
    body = {
        "project": "test-project",
        "model": "gemini-3.1-pro-high",
        "userAgent": "antigravity",
        "requestType": "agent",
        "requestId": f"agent-{uuid.uuid4()}",
        "request": {
            "contents": [{"role": "user", "parts": [{"text": "thời tiết hà nội hôm nay"}]}],
            "tools": [{"googleSearch": {}}]
        }
    }
    
    resp = requests.post(url, headers=headers, json=body)
    print("Status:", resp.status_code)
    
    try:
        data = resp.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print("Error parsing json:", e)
        print(resp.text)

if __name__ == "__main__":
    main()
