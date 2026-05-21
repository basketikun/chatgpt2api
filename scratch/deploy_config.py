import paramiko
import os

def main():
    hostname = "172.16.10.38"
    username = "root"
    password = "AnhNhi@0610"
    
    local_path = r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\config.json"
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {hostname}...")
        ssh.connect(hostname, username=username, password=password, timeout=15)
        
        sftp = ssh.open_sftp()
        remote_tmp = "/tmp/config.json"
        print(f"Uploading {local_path} to {remote_tmp}...")
        sftp.put(local_path, remote_tmp)
        sftp.close()
        
        # Copy to BOTH root config and data config inside container
        container_dests = [
            "chatgpt2api:/app/config.json",
            "chatgpt2api:/app/data/config.json"
        ]
        
        for dest in container_dests:
            print(f"Copying {remote_tmp} into container {dest}...")
            stdin, stdout, stderr = ssh.exec_command(f"docker cp {remote_tmp} {dest}")
            err = stderr.read().decode('utf-8', errors='ignore')
            if err.strip():
                print(f"STDERR copy: {err}")
            
        print(f"Removing {remote_tmp} on server...")
        ssh.exec_command(f"rm -f {remote_tmp}")
        
        print("Restarting chatgpt2api container to apply updates...")
        stdin, stdout, stderr = ssh.exec_command("docker restart chatgpt2api")
        out = stdout.read().decode('utf-8', errors='ignore')
        print(f"Restart status: {out.strip()}")
        print("Deployment of config.json to all persistent locations successful!")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
