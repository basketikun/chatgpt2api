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
        
        cmd = "docker exec chatgpt2api cat /app/data/accounts.json"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        
        content = stdout.read().decode('utf-8', errors='ignore')
        data = json.loads(content)
        
        print(f"Total accounts in pool: {len(data)}")
        for idx, acc in enumerate(data, start=1):
            email = acc.get("email", "Unknown")
            status = acc.get("status", "Unknown")
            plan = acc.get("plan", "Unknown")
            acc_type = acc.get("type", "Unknown")
            print(f"{idx}. Email: {email} | Status: {status} | Plan: {plan} | Type: {acc_type}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
