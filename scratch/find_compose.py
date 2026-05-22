import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610", timeout=10)
        
        stdin, stdout, stderr = ssh.exec_command('find /opt -name "docker-compose.yml" 2>/dev/null')
        files = stdout.read().decode('utf-8').splitlines()
        
        for f in files:
            stdin, stdout, stderr = ssh.exec_command(f'grep -H "chatgpt2api" "{f}"')
            out = stdout.read().decode('utf-8')
            if out:
                print(f"Found in {f}:\n{out}")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
