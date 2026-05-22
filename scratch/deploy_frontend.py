import paramiko
import os
import shutil
import zipfile

def main():
    hostname = "172.16.10.38"
    username = "root"
    password = "AnhNhi@0610"
    
    local_out_dir = r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\web\out"
    local_zip_path = r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\scratch\frontend.zip"
    
    if not os.path.exists(local_out_dir):
        print(f"Error: Local out directory {local_out_dir} does not exist. Please run next build first.")
        return
        
    print(f"Zipping {local_out_dir} into {local_zip_path}...")
    with zipfile.ZipFile(local_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(local_out_dir):
            for file in files:
                filePath = os.path.join(root, file)
                relPath = os.path.relpath(filePath, local_out_dir)
                zipf.write(filePath, relPath)
                
    print(f"Zip created. Size: {os.path.getsize(local_zip_path)} bytes.")
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {hostname}...")
        ssh.connect(hostname, username=username, password=password, timeout=20)
        
        sftp = ssh.open_sftp()
        remote_zip = "/tmp/frontend.zip"
        print(f"Uploading zip to remote {remote_zip}...")
        sftp.put(local_zip_path, remote_zip)
        sftp.close()
        
        # Prepare remote extraction
        print("Cleaning up remote temp folders and extracting zip...")
        ssh.exec_command("rm -rf /tmp/web_dist && mkdir -p /tmp/web_dist")
        stdin, stdout, stderr = ssh.exec_command("unzip -q /tmp/frontend.zip -d /tmp/web_dist")
        stdout.read() # Wait for completion
        
        print("Copying extracted files into chatgpt2api container...")
        # Clear remote container /app/web_dist
        ssh.exec_command("docker exec chatgpt2api rm -rf /app/web_dist && docker exec chatgpt2api mkdir -p /app/web_dist")
        
        # Copy files using docker cp
        stdin, stdout, stderr = ssh.exec_command("docker cp /tmp/web_dist/. chatgpt2api:/app/web_dist/")
        err = stderr.read().decode('utf-8', errors='ignore')
        if err.strip():
            print(f"Error during docker cp: {err}")
            
        print("Cleaning up remote temp files...")
        ssh.exec_command("rm -f /tmp/frontend.zip")
        ssh.exec_command("rm -rf /tmp/web_dist")
        
        print("Restarting chatgpt2api container to apply frontend updates...")
        stdin, stdout, stderr = ssh.exec_command("docker restart chatgpt2api")
        stdout.read()
        
        print("Frontend deployment successful and live container restarted!")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()
        if os.path.exists(local_zip_path):
            os.remove(local_zip_path)

if __name__ == "__main__":
    main()
