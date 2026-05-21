import requests
import json
import uuid

def test_project(access_token: str, project_id: str):
    print(f"\nTesting with Project ID: {project_id}")
    url = "https://cloudcode-pa.googleapis.com/v1internal:generateContent"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "antigravity/1.107.0 Windows/x64",
        "x-request-source": "local",
    }
    body = {
        "project": project_id,
        "model": "gemini-3.1-pro-high",
        "userAgent": "antigravity",
        "requestType": "agent",
        "requestId": f"agent-{uuid.uuid4()}",
        "request": {
            "contents": [{"role": "user", "parts": [{"text": "Hello, answer in exactly 1 word: YES"}]}]
        }
    }
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=15)
        print(f"Status Code: {resp.status_code}")
        print(resp.text[:500])
    except Exception as e:
        print(f"Failed: {e}")

def main():
    import paramiko
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610")
    
    stdin, stdout, stderr = ssh.exec_command("docker exec chatgpt2api cat /app/data/accounts.json")
    accounts = json.loads(stdout.read().decode('utf-8'))
    ssh.close()
    
    ag_acc = None
    for acc in accounts:
        if acc.get("type") == "antigravity" and acc.get("status") == "active":
            ag_acc = acc
            break
            
    if not ag_acc:
        print("No active antigravity account found!")
        return
        
    token = ag_acc["access_token"]
    print(f"Found Antigravity token (prefix): {token[:15]}...")
    
    # Test with the project ID returned by loadCodeAssist: "rising-silo-rmqqm"
    test_project(token, "rising-silo-rmqqm")

if __name__ == "__main__":
    main()
