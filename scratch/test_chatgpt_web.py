import json
import requests

def test_chatgpt_web(access_token: str):
    print("\nTesting chatgpt.com backend-api/conversation...")
    url = "https://chatgpt.com/backend-api/conversation"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/event-stream",
    }
    body = {
        "action": "next",
        "messages": [
            {
                "id": "aaaabbbb-cccc-dddd-eeee-ffff00001111",
                "author": {"role": "user"},
                "content": {"content_type": "text", "parts": ["Hi, answer in exactly 1 word: YES"]},
                "metadata": {}
            }
        ],
        "parent_message_id": "00000000-0000-0000-0000-000000000000",
        "model": "auto",
        "timezone_offset_min": -420,
        "history_and_training_disabled": True,
        "conversation_mode": {"kind": "primary_assistant"}
    }
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=20, stream=True)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            count = 0
            for line in resp.iter_lines():
                if line:
                    line_str = line.decode('utf-8', errors='ignore')
                    if line_str.startswith("data:"):
                        count += 1
                        if count < 5:
                            print(line_str[:200])
                        elif count == 5:
                            print("...")
            print("Stream completed successfully.")
        else:
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
    
    # 1. Test with a type: free token (tritue0610@gmail.com)
    free_token = None
    for acc in accounts:
        if acc.get("email") == "tritue0610@gmail.com" and acc.get("status") == "active":
            free_token = acc["access_token"]
            break
    if free_token:
        print("Testing with tritue0610@gmail.com (type: free)...")
        test_chatgpt_web(free_token)
    else:
        print("tritue0610@gmail.com not active or not found.")

    # 2. Test with a type: codex token
    codex_token = None
    for acc in accounts:
        if acc.get("type") == "codex" and acc.get("status") == "active":
            codex_token = acc["access_token"]
            break
    if codex_token:
        print("\nTesting with a codex token...")
        test_chatgpt_web(codex_token)

if __name__ == "__main__":
    main()
