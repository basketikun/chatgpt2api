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
        
        # Read the file /app/data/config.json content
        cmd = "docker exec chatgpt2api cat /app/data/config.json"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        
        content = stdout.read().decode('utf-8', errors='ignore')
        err = stderr.read().decode('utf-8', errors='ignore')
        
        if err.strip():
            print(f"Error reading file: {err}")
            return
            
        data = json.loads(content)
        print("--- /app/data/config.json inside container ---")
        print("\nCombo Models:")
        print(json.dumps(data.get("combo_models"), indent=2, ensure_ascii=False))
        
        print("\nGlobal System Prompt:")
        print(data.get("global_system_prompt"))
        
        print("\nSearch Configuration:")
        print(json.dumps(data.get("search"), indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
