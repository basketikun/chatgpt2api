import requests
import json

def main():
    import paramiko
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610")
    
    stdin, stdout, stderr = ssh.exec_command("docker exec chatgpt2api cat /app/data/accounts.json")
    accounts = json.loads(stdout.read().decode('utf-8'))
    ssh.close()
    
    print("--- ACTIVE ACCOUNTS AND ACCESS TOKENS PREFIXES ---")
    for acc in accounts:
        email = acc.get("email")
        status = acc.get("status")
        acc_type = acc.get("type")
        token = acc.get("access_token") or ""
        
        prefix = token[:20] if token else "None"
        starts_with_eyj = token.startswith("eyJ")
        print(f"Email: {email} | Status: {status} | Type: {acc_type} | Prefix: {prefix} | eyJ: {starts_with_eyj}")

if __name__ == "__main__":
    main()
