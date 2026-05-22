import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610", timeout=10)
        
        script = """
import os, glob

files = glob.glob('/app/web_dist/**/*.js', recursive=True)
patched = 0

for f in files:
    try:
        with open(f, 'r', encoding='utf-8') as file:
            content = file.read()
            
        if '172.16.10.38:8005' in content:
            new_content = content.replace('"http://172.16.10.38:8005"', '""')
            with open(f, 'w', encoding='utf-8') as file:
                file.write(new_content)
            patched += 1
            print(f"Patched {f}")
    except Exception as e:
        pass

print(f"Total patched: {patched}")
"""
        with open("patch_url.py", "w", encoding="utf-8") as f:
            f.write(script)
            
        sftp = ssh.open_sftp()
        sftp.put("patch_url.py", "/tmp/patch_url.py")
        sftp.close()
        
        ssh.exec_command("docker cp /tmp/patch_url.py chatgpt2api:/app/patch_url.py")
        
        stdin, stdout, stderr = ssh.exec_command("docker exec chatgpt2api uv run python /app/patch_url.py")
        
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
