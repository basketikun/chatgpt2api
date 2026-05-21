import paramiko
import os

def main():
    hostname = "172.16.10.38"
    username = "root"
    password = "AnhNhi@0610"
    
    files_to_deploy = [
        (r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\services\oauth_service.py", "chatgpt2api:/app/services/oauth_service.py"),
        (r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\api\system.py", "chatgpt2api:/app/api/system.py")
    ]
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {hostname}...")
        ssh.connect(hostname, username=username, password=password, timeout=15)
        
        sftp = ssh.open_sftp()
        for local_path, container_dest in files_to_deploy:
            remote_tmp = f"/tmp/{os.path.basename(local_path)}"
            print(f"Uploading {local_path} to {remote_tmp}...")
            sftp.put(local_path, remote_tmp)
            
            print(f"Copying {remote_tmp} into container {container_dest}...")
            stdin, stdout, stderr = ssh.exec_command(f"docker cp {remote_tmp} {container_dest}")
            err = stderr.read().decode('utf-8', errors='ignore')
            if err.strip():
                print(f"STDERR copy: {err}")
                
            print(f"Removing {remote_tmp} on server...")
            ssh.exec_command(f"rm -f {remote_tmp}")
            
        sftp.close()
        
        print("Restarting chatgpt2api container to apply updates...")
        stdin, stdout, stderr = ssh.exec_command("docker restart chatgpt2api")
        out = stdout.read().decode('utf-8', errors='ignore')
        print(f"Restart status: {out.strip()}")
        print("Deployment of OAuth fix successful!")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
