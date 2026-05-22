import paramiko
import os

def main():
    hostname = "172.16.10.38"
    username = "root"
    password = "AnhNhi@0610"
    
    local_path = r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\vn-mcp-hub\src\vn\currency.py"
    container_dest = "vn-mcp-hub:/app/src/vn/currency.py"
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {hostname}...")
        ssh.connect(hostname, username=username, password=password, timeout=15)
        
        sftp = ssh.open_sftp()
        remote_tmp = "/tmp/currency.py"
        print(f"Uploading {local_path} to {remote_tmp}...")
        sftp.put(local_path, remote_tmp)
        sftp.close()
        
        print(f"Copying {remote_tmp} into container {container_dest}...")
        stdin, stdout, stderr = ssh.exec_command(f"docker cp {remote_tmp} {container_dest}")
        err = stderr.read().decode('utf-8', errors='ignore')
        if err.strip():
            print(f"STDERR copy: {err}")
            
        print(f"Removing {remote_tmp} on server...")
        ssh.exec_command(f"rm -f {remote_tmp}")
        
        print("Restarting vn-mcp-hub container to apply updates...")
        stdin, stdout, stderr = ssh.exec_command("docker restart vn-mcp-hub")
        out = stdout.read().decode('utf-8', errors='ignore')
        print(f"Restart status: {out.strip()}")
        print("Deployment of vn-mcp-hub currency gold prices scraper successful!")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
