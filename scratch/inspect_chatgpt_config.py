import json

def main():
    import paramiko
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610")
    
    stdin, stdout, stderr = ssh.exec_command("docker exec chatgpt2api cat /app/data/config.json")
    cfg = json.loads(stdout.read().decode('utf-8'))
    ssh.close()
    
    prov = cfg.get("providers") or {}
    print(json.dumps(prov.get("chatgpt"), indent=2))
    print("OpenAI API Key in config:", cfg.get("openai_api_key"))

if __name__ == "__main__":
    main()
