
import sys
import json
sys.path.insert(0, '/app')

from services.mcp_client import call_mcp_tool, get_enabled_mcp_tools

print("--- Available MCP Tools ---")
tools = get_enabled_mcp_tools()
print(json.dumps(tools, ensure_ascii=False, indent=2))

print("\n--- Testing MCPSearch directly ---")
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
