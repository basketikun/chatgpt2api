
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
