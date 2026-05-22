import subprocess
import paramiko
import json

def fetch_file_from_container(ssh, container_name, file_path):
    stdin, stdout, stderr = ssh.exec_command(f"docker exec {container_name} cat {file_path}")
    content = stdout.read().decode('utf-8')
    err = stderr.read().decode('utf-8')
    if err and not content:
        # Try finding the file in /opt/ if container doesn't exist
        stdin, stdout, stderr = ssh.exec_command(f"cat /opt/chatgpt2api-data/{file_path.split('/')[-1]}")
        content = stdout.read().decode('utf-8')
    return content

def main():
    ssh_src = paramiko.SSHClient()
    ssh_src.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    ssh_dest = paramiko.SSHClient()
    ssh_dest.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print("Connecting to SOURCE (172.16.10.200)...")
        ssh_src.connect("172.16.10.200", username="root", password="AnhNhi@0610", timeout=10)
        
        print("Fetching config.json...")
        config_data = fetch_file_from_container(ssh_src, "chatgpt2api", "/app/data/config.json")
        
        print("Fetching accounts.json...")
        accounts_data = fetch_file_from_container(ssh_src, "chatgpt2api", "/app/data/accounts.json")
        
        if not config_data or not accounts_data:
            print("Could not find the files on the source server!")
            return
            
        print(f"Got config.json ({len(config_data)} bytes) and accounts.json ({len(accounts_data)} bytes).")
        
        print("\nConnecting to DESTINATION (172.16.10.38)...")
        ssh_dest.connect("172.16.10.38", username="root", password="AnhNhi@0610", timeout=10)
        
        print("Writing config.json...")
        sftp = ssh_dest.open_sftp()
        with sftp.file("/opt/chatgpt2api-data/config.json", "w") as f:
            f.write(config_data)
            
        print("Writing accounts.json...")
        with sftp.file("/opt/chatgpt2api-data/accounts.json", "w") as f:
            f.write(accounts_data)
        sftp.close()
        
        print("Restarting chatgpt2api on DESTINATION...")
        ssh_dest.exec_command("docker restart chatgpt2api")
        print("Migration complete!")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh_src.close()
        ssh_dest.close()

if __name__ == "__main__":
    main()
