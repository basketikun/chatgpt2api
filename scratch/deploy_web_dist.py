import os
import tarfile
import paramiko

def make_tarfile(output_filename, source_dir):
    """Create a tar.gz file where the root folder inside is named 'web_dist'."""
    print(f"Archiving {source_dir} into {output_filename}...")
    with tarfile.open(output_filename, "w:gz") as tar:
        # We walk through all files and add them with arcname starting with 'web_dist/'
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                local_path = os.path.join(root, file)
                # Calculate relative path from source_dir
                rel_path = os.path.relpath(local_path, source_dir)
                # Target path in archive should be under 'web_dist/'
                archive_name = os.path.join("web_dist", rel_path).replace("\\", "/")
                tar.add(local_path, arcname=archive_name)
    print("Archiving complete!")

def main():
    source_dir = r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\web\out"
    tar_path = r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\scratch\web_dist.tar.gz"
    
    make_tarfile(tar_path, source_dir)
    
    hostname = "172.16.10.38"
    username = "root"
    password = "AnhNhi@0610"
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {hostname}...")
        ssh.connect(hostname, username=username, password=password, timeout=15)
        
        sftp = ssh.open_sftp()
        remote_tmp = "/tmp/web_dist.tar.gz"
        print(f"Uploading {tar_path} to remote {remote_tmp}...")
        sftp.put(tar_path, remote_tmp)
        sftp.close()
        
        print("Copying archive into container...")
        stdin, stdout, stderr = ssh.exec_command(f"docker cp {remote_tmp} chatgpt2api:/tmp/web_dist.tar.gz")
        err = stderr.read().decode('utf-8', errors='ignore')
        if err.strip():
            print(f"STDERR copy: {err}")
            
        print("Extracting archive inside container...")
        # First clear old web_dist files to avoid stales, then extract
        cmds = [
            "docker exec chatgpt2api rm -rf /app/web_dist",
            "docker exec chatgpt2api tar -xzf /tmp/web_dist.tar.gz -C /app",
            "docker exec chatgpt2api rm -f /tmp/web_dist.tar.gz",
            f"rm -f {remote_tmp}"
        ]
        for cmd in cmds:
            print(f"Running: {cmd}")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            out_err = stderr.read().decode('utf-8', errors='ignore')
            if out_err.strip():
                print(f"STDERR: {out_err.strip()}")
                
        print("Restarting chatgpt2api container to apply frontend updates...")
        ssh.exec_command("docker restart chatgpt2api")
        print("Deployment of Next.js frontend successful!")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()
        # Clean up local tar file
        if os.path.exists(tar_path):
            os.remove(tar_path)

if __name__ == "__main__":
    main()
