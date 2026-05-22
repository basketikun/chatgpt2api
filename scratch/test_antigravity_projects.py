import requests
import json
import random
import uuid

def generate_project_id() -> str:
    adjectives = ["useful", "bright", "swift", "calm", "bold"]
    nouns = ["fuze", "wave", "spark", "flow", "core"]
    return f"{random.choice(adjectives)}-{random.choice(nouns)}-{uuid.uuid4().hex[:5]}"

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
            "contents": [{"role": "user", "parts": [{"text": "Hello, write 1 word."}]}]
        }
    }
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=15)
        print(f"Status Code: {resp.status_code}")
        print(resp.text[:500])
    except Exception as e:
        print(f"Failed: {e}")

def main():
    # Read access token from remote container first or local store if available
    # Let's read the antigravity account token from /app/data/accounts.json inside the container
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
    
    # 1. Test loadCodeAssist API
    print("\nCalling loadCodeAssist API...")
    try:
        resp = requests.post(
            "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "google-api-nodejs-client/9.15.1",
            },
            json={"metadata": {"ideType": "IDE_UNSPECIFIED", "platform": "PLATFORM_UNSPECIFIED", "pluginType": "GEMINI"}},
            timeout=15,
        )
        print(f"loadCodeAssist Status: {resp.status_code}")
        print(resp.text)
    except Exception as e:
        print(f"loadCodeAssist failed: {e}")
        
    # 2. Test email as project (fails 403)
    test_project(token, ag_acc.get("email", ""))
    
    # 3. Test generated decoy project ID
    test_project(token, generate_project_id())

if __name__ == "__main__":
    main()
