import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610", timeout=10)
        
        script = """
import sys
import json
sys.path.insert(0, '/app')

from services.mcp_client import call_mcp_tool, get_enabled_mcp_tools

print("--- Available MCP Tools ---")
tools = get_enabled_mcp_tools()
print(json.dumps(tools, ensure_ascii=False, indent=2))

print("\\n--- Testing MCPSearch directly ---")
results = []
for tool in ["search_web", "search_all", "search", "get_news", "get_current_weather"]:
    try:
        print(f"Trying tool {tool}...")
        text = call_mcp_tool(tool, {"query": "giá vàng hôm nay", "limit": 3})
        print(f"Tool {tool} succeeded, length={len(str(text))}")
        if text and len(text) > 10:
            results.append({"title": tool, "snippet": text[:150], "url": ""})
    except Exception as e:
        print(f"Tool {tool} failed: {e}")

print("Results:", json.dumps(results, ensure_ascii=False, indent=2))
"""
        with open("test_mcp.py", "w", encoding="utf-8") as f:
            f.write(script)
            
        sftp = ssh.open_sftp()
        sftp.put("test_mcp.py", "/tmp/test_mcp.py")
        sftp.close()
        
        ssh.exec_command("docker cp /tmp/test_mcp.py chatgpt2api:/app/test_mcp.py")
        
        print("Executing script inside container...")
        stdin, stdout, stderr = ssh.exec_command("docker exec chatgpt2api uv run python /app/test_mcp.py")
        
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        
        print("STDOUT:")
        print(out)
        if err:
            print("STDERR:")
            print(err)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    main()
