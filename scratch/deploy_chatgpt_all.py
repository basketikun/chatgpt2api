import os
import tarfile
import paramiko

def main():
    hostname = "172.16.10.38"
    username = "root"
    password = "AnhNhi@0610"
    
    local_out_dir = r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\web\out"
    local_tar_path = r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\web_out.tar"
    remote_tar_path = "/tmp/web_out.tar"
    
    print("Creating tar archive of web/out...")
    with tarfile.open(local_tar_path, "w") as tar:
        tar.add(local_out_dir, arcname=".")
    print(f"Archive created at {local_tar_path}")
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {hostname} via SSH...")
        ssh.connect(hostname, username=username, password=password, timeout=10)
        
        sftp = ssh.open_sftp()
        print(f"Uploading {local_tar_path} -> {remote_tar_path}...")
        sftp.put(local_tar_path, remote_tar_path)
        sftp.close()
        
        print("Extracting archive inside chatgpt2api docker container...")
        # Clear existing web_dist contents to avoid leftovers
        ssh.exec_command("docker exec chatgpt2api rm -rf /app/web_dist/*")
        
        # Ensure /app/web_dist exists
        ssh.exec_command("docker exec chatgpt2api mkdir -p /app/web_dist")
        
        # Extract tar into container
        stdin, stdout, stderr = ssh.exec_command(f"docker cp {remote_tar_path} chatgpt2api:/app/web_dist/")
        err = stderr.read().decode('utf-8', errors='ignore')
        if err:
            print(f"Error copying tar into container: {err}")
            return
            
        print("Extracting tar in container...")
        stdin, stdout, stderr = ssh.exec_command("docker exec chatgpt2api tar -xf /app/web_dist/web_out.tar -C /app/web_dist/")
        err = stderr.read().decode('utf-8', errors='ignore')
        if err:
            print(f"Error extracting tar in container: {err}")
            return
            
        # Remove tar file from container and host
        ssh.exec_command("docker exec chatgpt2api rm -f /app/web_dist/web_out.tar")
        ssh.exec_command(f"rm -f {remote_tar_path}")
        
        print("Copying python code changes...")
        # Deploy the python code changes we made:
        py_files = [
            (r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\services\account_service.py", "chatgpt2api:/app/services/account_service.py"),
            (r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\services\oauth_service.py", "chatgpt2api:/app/services/oauth_service.py"),
            (r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\api\system.py", "chatgpt2api:/app/api/system.py"),
        ]
        
        sftp = ssh.open_sftp()
        for local_file, container_dest in py_files:
            tmp_remote = f"/tmp/{os.path.basename(local_file)}"
            print(f"Uploading {local_file} -> {tmp_remote}...")
            sftp.put(local_file, tmp_remote)
            print(f"Copying {tmp_remote} -> {container_dest}...")
            ssh.exec_command(f"docker cp {tmp_remote} {container_dest}")
        sftp.close()
        
        print("Restarting chatgpt2api container to apply updates...")
        stdin, stdout, stderr = ssh.exec_command("docker restart chatgpt2api")
        out = stdout.read().decode('utf-8', errors='ignore')
        print(f"Restart status: {out.strip()}")
        print("Deployment successful!")
        
    except Exception as e:
        print(f"Error during deployment: {e}")
    finally:
        ssh.close()
        # Clean up local tar file
        if os.path.exists(local_tar_path):
            os.remove(local_tar_path)

if __name__ == "__main__":
    main()
