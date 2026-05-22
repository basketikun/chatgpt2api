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
        if acc.get("status") == "active":
            token = acc.get("access_token", "")
            acc_type_raw = str(acc.get("type") or "")
            acc_type = acc_type_raw.split(",")
            aud = detect_token_audience(token)
            
            is_openai_api = False
            if token.startswith("sk-"):
                is_openai_api = True
            else:
                if ("standard" in acc_type or "openai" in acc_type) or (
                    aud == "api.openai.com"
                    and "codex" not in acc_type
                    and "free" not in acc_type
                    and "antigravity" not in acc_type
                ):
                    is_openai_api = True
            
            print(f"Email: {acc.get('email')} | Type: {acc_type_raw} | Aud: {aud} | is_openai_api: {is_openai_api}")

if __name__ == "__main__":
    main()
