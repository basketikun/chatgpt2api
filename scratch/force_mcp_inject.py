import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610", timeout=10)
        
        script = """
import sys
sys.path.insert(0, '/app')
from services.config import config
from services.mcp_presets import PRESETS

installed = config.data.get("mcp_servers") or {}
if isinstance(installed, list):
    installed = {item.get("id", str(i)): item for i, item in enumerate(installed) if isinstance(item, dict)}

# Lọc ra các preset liên quan đến vn_ và kb_
for p in PRESETS:
    if p.id.startswith("vn_") or p.id.startswith("kb_") or p.id in ["youtube", "wikipedia", "ha_helper"]:
        installed[p.id] = {
            "name": p.name,
            "url": f"http://vn-mcp-hub:8005/{p.id}/mcp" if p.id != "wikipedia" and p.id != "youtube" and p.id != "ha_helper" else f"http://vn-mcp-hub:8005/{p.id}/mcp",
            "enabled": True,
            "requires_api_key": p.requires_api_key,
            "api_key": None
        }

config.data["mcp_servers"] = installed
config._save()
print("Force injected MCP configurations!")
"""
        with open("force_mcp.py", "w", encoding="utf-8") as f:
            f.write(script)
            
        sftp = ssh.open_sftp()
        sftp.put("force_mcp.py", "/tmp/force_mcp.py")
        sftp.close()
        
        ssh.exec_command("docker cp /tmp/force_mcp.py chatgpt2api:/app/force_mcp.py")
        
        stdin, stdout, stderr = ssh.exec_command("docker exec chatgpt2api uv run python /app/force_mcp.py")
        
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
