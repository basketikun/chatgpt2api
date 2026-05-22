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
        
        # Read /app/data/config.json content
        cmd = "docker exec chatgpt2api cat /app/data/config.json"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        
        content = stdout.read().decode('utf-8', errors='ignore')
        data = json.loads(content)
        
        print("Keys of config.json:")
        for k in data.keys():
            print(f"- {k}: {type(data[k])}")
            
        print("\nhome_assistant field:")
        print(data.get("home_assistant"))
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
