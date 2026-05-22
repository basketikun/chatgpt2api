import paramiko
import json

def main():
    hostname = "172.16.10.38"
    username = "root"
    password = "AnhNhi@0610"
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(hostname, username=username, password=password, timeout=15)
        
        cmd = "docker exec chatgpt2api cat /app/data/config.json"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        
        content = stdout.read().decode('utf-8', errors='ignore')
        data = json.loads(content)
        
        print("combo_models:")
        print(json.dumps(data.get("combo_models"), indent=2))
        
        print("\nsearch:")
        print(json.dumps(data.get("search"), indent=2))
        
        print("\nproviders:")
        print(json.dumps(data.get("providers"), indent=2))
        
        print("\ncustom_providers:")
        print(json.dumps(data.get("custom_providers"), indent=2))
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
