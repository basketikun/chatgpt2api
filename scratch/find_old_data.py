import subprocess
import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610", timeout=10)
        
        print("--- Docker volumes ---")
        stdin, stdout, stderr = ssh.exec_command("docker volume ls")
        print(stdout.read().decode('utf-8'))
        
        print("\n--- Finding config.json files on system ---")
        stdin, stdout, stderr = ssh.exec_command("find / -name config.json 2>/dev/null | grep -i chatgpt2api")
        print(stdout.read().decode('utf-8'))
        
        print("\n--- Finding accounts.json files on system ---")
        stdin, stdout, stderr = ssh.exec_command("find / -name accounts.json 2>/dev/null | grep -i chatgpt2api")
        print(stdout.read().decode('utf-8'))
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
