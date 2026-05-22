import json

def detect_token_audience(access_token: str) -> str:
    if not access_token or not access_token.startswith("eyJ"):
        return "unknown"
    try:
        import base64, json
        parts = access_token.split(".")
        if len(parts) >= 2:
            padded = parts[1] + "=" * (-len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded))
            aud = payload.get("aud", "")
            if isinstance(aud, list):
                aud = aud[0] if aud else ""
            aud_str = str(aud).lower()
            if "api.openai.com" in aud_str:
                return "api.openai.com"
            if "chatgpt.com" in aud_str:
                return "chatgpt.com"
            return f"other_aud: {aud_str}"
    except Exception as e:
        return f"err: {e}"
    return "unknown"

def main():
    import paramiko
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610")
    
    stdin, stdout, stderr = ssh.exec_command("docker exec chatgpt2api cat /app/data/accounts.json")
    accounts = json.loads(stdout.read().decode('utf-8'))
    ssh.close()
    
    for acc in accounts:
        email = acc.get("email")
        status = acc.get("status")
        acc_type = acc.get("type")
        token = acc.get("access_token") or ""
        
        aud = detect_token_audience(token)
        print(f"Email: {email} | Status: {status} | Type: {acc_type} | Audience: {aud}")

if __name__ == "__main__":
    main()
