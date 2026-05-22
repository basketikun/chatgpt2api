import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610", timeout=10)
        
        stdin, stdout, stderr = ssh.exec_command("docker logs --tail 200 chatgpt2api")
        logs = stdout.read().decode('utf-8', errors='replace')
        err_logs = stderr.read().decode('utf-8', errors='replace')
        
        all_logs = (logs + "\n" + err_logs).split('\n')
        
        with open(r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\scratch\remote_logs.txt", "w", encoding="utf-8") as f:
            for line in all_logs:
                if "search" in line.lower() or "gemini" in line.lower():
                    f.write(line + "\n")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
