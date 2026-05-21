import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    local_file = r"d:\Chatgpt\chatgpt2api\chatgpt2api-1\api\mcp.py"
    remote_path = "/tmp/mcp.py"
    container_path = "/app/api/mcp.py"
    
    try:
        ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610", timeout=10)
        
        sftp = ssh.open_sftp()
        sftp.put(local_file, remote_path)
        sftp.close()
        
        commands = [
            f"docker cp {remote_path} chatgpt2api:{container_path}",
            "docker restart chatgpt2api"
        ]
        
        for cmd in commands:
            ssh.exec_command(cmd)
            
        print("Synced api/mcp.py and restarted container.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
