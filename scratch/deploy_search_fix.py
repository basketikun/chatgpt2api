import paramiko
import os

def main():
    hostname = "172.16.10.38"
    username = "root"
    password = "AnhNhi@0610"
    
    local_file = r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\vn-mcp-hub\src\vn\search.py"
    remote_tmp = "/tmp/search.py"
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {hostname}...")
        ssh.connect(hostname, username=username, password=password, timeout=15)
        
        # Upload via SFTP
        sftp = ssh.open_sftp()
        print(f"Uploading {local_file} to {remote_tmp}...")
        sftp.put(local_file, remote_tmp)
        sftp.close()
        
        # Copy into docker container and restart
        commands = [
            "docker cp /tmp/search.py vn-mcp-hub:/app/src/vn/search.py",
            "docker restart vn-mcp-hub",
            "rm -f /tmp/search.py"
        ]
        
        for cmd in commands:
            print(f"Running remote command: {cmd}")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            out = stdout.read().decode('utf-8', errors='ignore')
            err = stderr.read().decode('utf-8', errors='ignore')
            if out.strip():
                print(f"STDOUT: {out}")
            if err.strip():
                print(f"STDERR: {err}")
                
        print("Successfully deployed search.py fix to remote container vn-mcp-hub!")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
