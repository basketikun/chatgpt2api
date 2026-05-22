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
        
        # We will write the python command cleanly to avoid any shell escaping issues
        python_cmd = (
            "from src.search.orchestrator import federated_search\n"
            "r = federated_search('giá vàng hôm nay', 5)\n"
            "print(f'{len(r)} results found:')\n"
            "for idx, x in enumerate(r[:10]):\n"
            "    source = x.get('source', '?')\n"
            "    title = x.get('title', '')\n"
            "    url = x.get('url', '')\n"
            "    print(f'[{idx+1}] Source: {source} | Title: {title} | URL: {url}')\n"
        )
        
        # Execute the python command inside the vn-mcp-hub docker container
        # Passing python command via stdin
        exec_cmd = "docker exec -i vn-mcp-hub python3"
        print(f"Running search in container vn-mcp-hub...")
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
