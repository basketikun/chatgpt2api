import paramiko
import os

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    local_file = r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\services\search_service.py"
    remote_path = "/tmp/search_service.py"
    container_path = "/app/services/search_service.py"
    
    try:
        ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610", timeout=10)
        
        # Upload file
        sftp = ssh.open_sftp()
        sftp.put(local_file, remote_path)
        sftp.close()
        print("Uploaded search_service.py to /tmp")
        
        # Copy to container and restart
        commands = [
            f"docker cp {remote_path} chatgpt2api:{container_path}",
            "docker restart chatgpt2api"
        ]
        
        for cmd in commands:
            print(f"Executing: {cmd}")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            out = stdout.read().decode('utf-8')
            err = stderr.read().decode('utf-8')
            if out: print(out)
            if err: print("Error:", err)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
