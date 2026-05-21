"use client";

import { useCallback, useEffect, useState } from "react";
import { request } from "@/lib/request";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type McpGroup = {
  name: string; icon: string; description: string;
  mcps: { id: string; name: string; url: string }[];
  installedCount: number; totalCount: number;
};

const GROUPS: McpGroup[] = [
  { name: "Tìm kiếm", icon: "🔍", description: "Search web, Wikipedia, paper, luật, phạt nguội, federated",
    mcps: [{id:"vn_search",name:"Tìm kiếm Web",url:""},{id:"wikipedia",name:"Wikipedia",url:""},{id:"arxiv",name:"arXiv Paper",url:""},{id:"federated_search",name:"Federated Search",url:""},{id:"vn_law",name:"Tra cứu Luật",url:""},{id:"vn_phat_nguoi",name:"Phạt nguội",url:""}], installedCount:0, totalCount:6 },
  { name: "Thời tiết", icon: "🌤️", description: "Thời tiết 4 nguồn quốc tế",
    mcps: [{id:"vn_weather",name:"Thời tiết VN",url:""}], installedCount:0, totalCount:1 },
  { name: "Tin tức", icon: "📰", description: "Tin VN + BBC + Google News",
    mcps: [{id:"vn_news",name:"Tin tức VN",url:""}], installedCount:0, totalCount:1 },
  { name: "Tài chính", icon: "💵", description: "Tỷ giá, vàng, cổ phiếu VN",
    mcps: [{id:"vn_currency",name:"Tỷ giá & Vàng",url:""},{id:"vn_stock",name:"Cổ phiếu VN",url:""}], installedCount:0, totalCount:2 },
  { name: "Knowledge Base", icon: "📚", description: "7 kho tri thức RAG (điện nước, y tế, giáo dục, ngoại ngữ, khoa học, tự nhiên, xã hội)",
    mcps: [{id:"kb_dien_nuoc",name:"Kho Điện Nước",url:""},{id:"kb_y_te",name:"Kho Y Tế",url:""},{id:"kb_giao_duc",name:"Kho Giáo Dục",url:""},{id:"kb_ngoai_ngu",name:"Kho Ngoại Ngữ",url:""},{id:"kb_khoa_hoc",name:"Kho Khoa Học",url:""},{id:"kb_tu_nhien",name:"Kho Tự Nhiên",url:""},{id:"kb_xa_hoi",name:"Kho Xã Hội",url:""}], installedCount:0, totalCount:7 },
  { name: "VN Khác", icon: "🏛️", description: "Lịch âm",
    mcps: [{id:"vn_lunar",name:"Lịch Âm",url:""}], installedCount:0, totalCount:1 },
  { name: "Khác", icon: "📦", description: "YouTube Transcript, HA Helper",
    mcps: [{id:"youtube",name:"YouTube Transcript",url:""},{id:"ha_helper",name:"HA Helper",url:""}], installedCount:0, totalCount:2 },
];

export default function McpPage() {
  const { isCheckingAuth } = useAuthGuard(["admin"]);
  const [groups, setGroups] = useState<McpGroup[]>(GROUPS);
  const [hubUrl, setHubUrl] = useState("");

  const [connecting, setConnecting] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadStatus = useCallback(async () => {
    try {
      const presets = await request.get("/api/mcp/presets");
      const data = presets.data?.presets || presets.presets || [];
      const installed: Record<string, boolean> = {};
      data.forEach((p: any) => { if (p.installed) installed[p.id] = true; });
      setGroups(prev => prev.map(g => {
        const count = g.mcps.filter(m => installed[m.id]).length;
        return { ...g, installedCount: count };
      }));
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => { 
    const saved = localStorage.getItem("mcp_hub_url") || "http://vn-mcp-hub:8005";
    setHubUrl(saved);
    loadStatus(); 
  }, []);

  const connectHub = async () => {
    setConnecting(true);
    localStorage.setItem("mcp_hub_url", hubUrl);
    try {
      const hub = await request.post("/api/mcp/discover", { hub_url: hubUrl });
      const hubData = hub.data || hub;
      if (hubData.ok) {
        // Update groups with real URLs from hub
        const hubMcps = hubData.mcps || [];
        setGroups(GROUPS.map(g => ({
          ...g,
          mcps: g.mcps.map(m => {
            const h = hubMcps.find((hm: any) => hm.id === m.id);
            return h ? { ...m, url: h.url } : m;
          }),
        })));
      }
    } catch (e) { alert("Không kết nối được Hub"); }
    setConnecting(false);
    // Remove loadStatus() call here to prevent overwriting URL state immediately after connecting,
    // or just let it run since loadStatus now uses prev state.
    loadStatus();
  };

  const installGroup = async (group: McpGroup) => {
    setSaving(group.name);
    const allInstalled = group.installedCount === group.totalCount;
    let delta = 0;
    for (const m of group.mcps) {
      try {
        if (allInstalled) {
          await request.post(`/api/mcp/uninstall/${m.id}`);
          delta--;
        } else {
          await request.post("/api/mcp/install", { id: m.id, url_override: m.url });
          delta++;
        }
      } catch (e) {}
    }
    // Update just the count, don't reset state
    setGroups(prev => prev.map(g => g.name === group.name
      ? { ...g, installedCount: allInstalled ? 0 : g.totalCount }
      : g));
    setSaving(null);
  };

  if (loading) return <div className="p-6 text-muted-foreground">Đang tải...</div>;

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold">MCP Servers</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Kết nối vn-mcp-hub. Bật/tắt nhóm MCP. Chi tiết từng MCP quản lý tại <a href={`${hubUrl}/studio`} target="_blank" className="text-primary underline">Studio</a>.
        </p>
      </div>

      <div className="flex gap-2 items-end">
        <div className="flex-1">
          <Input value={hubUrl} onChange={(e) => setHubUrl(e.target.value)} placeholder="http://vn-mcp-hub:8005" />
        </div>
        <Button onClick={connectHub} disabled={connecting}>{connecting ? "..." : "Kết nối Hub"}</Button>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {groups.map(g => {
          const allOn = g.installedCount === g.totalCount && g.totalCount > 0;
          const partial = g.installedCount > 0 && !allOn;
          return (
            <div key={g.name}
              className="p-4 border-2 rounded-lg cursor-pointer hover:border-primary/50 transition-colors"
              style={{borderColor: allOn ? '#22c55e' : partial ? '#f59e0b' : undefined}}
              onClick={() => installGroup(g)}>
              <div className="flex items-center justify-between mb-1">
                <span className="font-medium text-lg">{g.icon} {g.name}</span>
                {saving === g.name ? <span className="text-xs text-muted-foreground">Đang lưu...</span> :
                 <Badge variant="outline" className={allOn ? "border-green-500 text-green-500" : partial ? "border-orange-500 text-orange-500" : ""}>
                   {g.installedCount}/{g.totalCount}
                 </Badge>}
              </div>
              <p className="text-sm text-muted-foreground mb-2">{g.description}</p>
              <div className="flex flex-wrap gap-1">
                {g.mcps.map(m => (
                  <span key={m.id} className="text-xs px-2 py-0.5 rounded bg-secondary text-secondary-foreground"
                    style={{opacity: m.url ? 1 : 0.4}}>
                    {m.name}{!m.url ? ' (chưa kết nối)' : ''}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
