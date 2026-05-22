import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610", timeout=10)
        
        script = """
import os, glob

# Find all JS files in web_dist
files = glob.glob('/app/web_dist/**/*.js', recursive=True)
patched = 0

for f in files:
    try:
        with open(f, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Look for the buggy logic. In minified JS it might be `if(!m.url)continue;` or `if(!e.url)continue;`
        # We can just look for `.url)continue`
        if ')continue' in content and 'url' in content:
            # A bit dangerous, let's be more specific
            # In page.tsx: `if (!m.url) continue;`
            import re
            # Matches: if(!a.url)continue;
            new_content, count = re.subn(r'if\(![a-zA-Z_]\.url\)continue;?', '', content)
            if count > 0:
                with open(f, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                patched += count
                print(f"Patched {count} occurrences in {f}")
    except Exception as e:
        pass

print(f"Total patched: {patched}")
"""
        with open("patch_js.py", "w", encoding="utf-8") as f:
            f.write(script)
            
        sftp = ssh.open_sftp()
        sftp.put("patch_js.py", "/tmp/patch_js.py")
        sftp.close()
        
        ssh.exec_command("docker cp /tmp/patch_js.py chatgpt2api:/app/patch_js.py")
        
        stdin, stdout, stderr = ssh.exec_command("docker exec chatgpt2api uv run python /app/patch_js.py")
        
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
