import paramiko

def main():
    hostname = "172.16.10.38"
    username = "root"
    password = "AnhNhi@0610"
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(hostname, username=username, password=password, timeout=15)
        
        # We will run python command in the container via simple double quotes
        cmd = "docker exec chatgpt2api python -c \"import json; f1=open('/app/config.json').read(); f2=open('/app/data/config.json').read(); print('f1 length:', len(f1)); print('f2 length:', len(f2)); json.loads(f1); json.loads(f2); print('SUCCESS: Both files are completely valid JSON!')\""
        stdin, stdout, stderr = ssh.exec_command(cmd)
        
        out = stdout.read().decode('utf-8', errors='ignore')
        err = stderr.read().decode('utf-8', errors='ignore')
        
        print("STDOUT:")
        print(out)
        print("STDERR:")
        print(err)
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
