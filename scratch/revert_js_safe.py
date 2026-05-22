import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610", timeout=10)
        
        commands = [
            "docker create --name temp_chatgpt2api ghcr.io/tritue2011/chatgpt2api:latest",
            "docker cp temp_chatgpt2api:/app/web_dist/_next/static/chunks/17pn6-a~kk32_.js /tmp/orig.js",
            "docker cp /tmp/orig.js chatgpt2api:/app/web_dist/_next/static/chunks/17pn6-a~kk32_.js",
            "docker rm -f temp_chatgpt2api"
        ]
        
        for cmd in commands:
            stdin, stdout, stderr = ssh.exec_command(cmd)
            out = stdout.read().decode('utf-8')
            err = stderr.read().decode('utf-8')
            if err:
                print(f"[{cmd}] STDERR: {err}")
            else:
                print(f"[{cmd}] STDOUT: {out}")
                
        print("Reverted JS file successfully!")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
