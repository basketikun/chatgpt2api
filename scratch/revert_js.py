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
            
        if 'useState("")' in content or '""' in content:
            # We don't know exactly where we replaced it, but we can look for the exact signature if we know it.
            # Actually, I replaced '"http://172.16.10.38:8005"' with '""'.
            # To revert, I can replace '""' back with '"http://172.16.10.38:8005"', but that's very dangerous.
            pass
    except Exception as e:
        pass
"""
        pass
        # A safer way to revert is just to restart the container, BUT the JS file was overwritten in the container's volume?
        # NO! The JS file is part of the docker image!
        # If I restart the container, does it revert? No, unless it's destroyed and recreated.
        # Let's recreate the container!
        commands = [
            "docker rm -f chatgpt2api",
            "docker run -d --name chatgpt2api -p 3030:3000 -v /opt/chatgpt2api-data:/app/data --restart always ghcr.io/tritue2011/chatgpt2api:latest"
        ]
        
        # Wait, I don't know the exact docker run command the user used!
        # Better to read the docker-compose.yml or docker run history!
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
