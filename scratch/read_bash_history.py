import subprocess
import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610", timeout=10)
        
        print("--- .bash_history ---")
        stdin, stdout, stderr = ssh.exec_command("cat ~/.bash_history | grep -i docker")
        print(stdout.read().decode('utf-8'))
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
