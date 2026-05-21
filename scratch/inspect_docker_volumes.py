import subprocess
import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610", timeout=10)
        
        print("--- Docker volumes mapped to chatgpt2api ---")
        stdin, stdout, stderr = ssh.exec_command("docker inspect chatgpt2api --format '{{json .Mounts}}'")
        print(stdout.read().decode('utf-8'))
        
        print("\n--- Listing /opt/ ---")
        stdin, stdout, stderr = ssh.exec_command("ls -la /opt/")
        print(stdout.read().decode('utf-8'))
        
        print("\n--- Finding other potential chatgpt2api data directories ---")
        stdin, stdout, stderr = ssh.exec_command("find / -type d -name '*chatgpt2api*' -maxdepth 3 2>/dev/null")
        print(stdout.read().decode('utf-8'))
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
