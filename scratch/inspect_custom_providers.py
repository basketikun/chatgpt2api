import json

def main():
    import paramiko
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610")
    
    stdin, stdout, stderr = ssh.exec_command("docker exec chatgpt2api cat /app/data/config.json")
    cfg = json.loads(stdout.read().decode('utf-8'))
    ssh.close()
    
    print(json.dumps(cfg.get("custom_providers"), indent=2))

if __name__ == "__main__":
    main()
