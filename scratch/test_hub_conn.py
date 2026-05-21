import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610", timeout=10)
        
        script = """
import urllib.request
try:
    print("Trying 172.16.10.38:8005...")
    r = urllib.request.urlopen("http://172.16.10.38:8005/", timeout=5)
    print("Success! " + r.read().decode('utf-8')[:50])
except Exception as e:
    print("Failed: " + str(e))

try:
    print("Trying vn-mcp-hub:8005...")
    r = urllib.request.urlopen("http://vn-mcp-hub:8005/", timeout=5)
    print("Success! " + r.read().decode('utf-8')[:50])
except Exception as e:
    print("Failed: " + str(e))
"""
        with open("test_hub.py", "w", encoding="utf-8") as f:
            f.write(script)
            
        sftp = ssh.open_sftp()
        sftp.put("test_hub.py", "/tmp/test_hub.py")
        sftp.close()
        
        ssh.exec_command("docker cp /tmp/test_hub.py chatgpt2api:/app/test_hub.py")
        
        stdin, stdout, stderr = ssh.exec_command("docker exec chatgpt2api uv run python /app/test_hub.py")
        
        out = stdout.read().decode('utf-8')
        err = stderr.read().decode('utf-8')
        
        print("STDOUT:\n" + out)
        if err:
            print("STDERR:\n" + err)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
