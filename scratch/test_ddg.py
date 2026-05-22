import paramiko
import sys

def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
        
    hostname = "172.16.10.38"
    username = "root"
    password = "AnhNhi@0610"
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {hostname}...")
        ssh.connect(hostname, username=username, password=password, timeout=15)
        
        python_cmd = (
            "from src.vn.search import ddg_search\n"
            "res = ddg_search('giá vàng hôm nay', 5)\n"
            "print('Results:', res)\n"
        )
        
        exec_cmd = "docker exec -i vn-mcp-hub python3"
        print(f"Running ddg_search in container vn-mcp-hub...")
        stdin, stdout, stderr = ssh.exec_command(exec_cmd)
        stdin.write(python_cmd)
        stdin.flush()
        stdin.channel.shutdown_write()
        
        out_content = stdout.read().decode('utf-8', errors='ignore')
        err_content = stderr.read().decode('utf-8', errors='ignore')
        
        print("\n--- STDOUT ---")
        print(out_content)
        if err_content.strip():
            print("--- STDERR ---")
            print(err_content)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
