"use client";

import { useCallback, useEffect, useState } from "react";
import { request } from "@/lib/request";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { Plug, ExternalLink, CheckCircle2, AlertCircle } from "lucide-react";

type McpGroup = {
  name: string; icon: string; description: string;
  mcps: { id: string; name: string; url: string }[];
  installedCount: number; totalCount: number;
};

const GROUPS: McpGroup[] = [
  { name: "Tim kiem", icon: "🔍", description: "Search web, Wikipedia, paper, luat, phat nguoi, federated",
    mcps: [{id:"vn_search",name:"Tim kiem Web",url:""},{id:"wikipedia",name:"Wikipedia",url:""},{id:"arxiv",name:"arXiv Paper",url:""},{id:"federated_search",name:"Federated Search",url:""},{id:"vn_law",name:"Tra cuu Luat",url:""},{id:"vn_phat_nguoi",name:"Phat nguoi",url:""}], installedCount:0, totalCount:6 },
  { name: "Thoi tiet", icon: "🌤️", description: "Thoi tiet 4 nguon quoc te",
    mcps: [{id:"vn_weather",name:"Thoi tiet VN",url:""}], installedCount:0, totalCount:1 },
  { name: "Tin tuc", icon: "📰", description: "Tin VN + BBC + Google News",
    mcps: [{id:"vn_news",name:"Tin tuc VN",url:""}], installedCount:0, totalCount:1 },
  { name: "Tai chinh", icon: "💵", description: "Ty gia, vang, co phieu VN",
    mcps: [{id:"vn_currency",name:"Ty gia & Vang",url:""},{id:"vn_stock",name:"Co phieu VN",url:""}], installedCount:0, totalCount:2 },
  { name: "Knowledge Base", icon: "📚", description: "7 kho tri thuc RAG (dien nuoc, y te, giao duc, ngoai ngu, khoa hoc, tu nhien, xa hoi)",
    mcps: [{id:"kb_dien_nuoc",name:"Kho Dien Nuoc",url:""},{id:"kb_y_te",name:"Kho Y Te",url:""},{id:"kb_giao_duc",name:"Kho Giao Duc",url:""},{id:"kb_ngoai_ngu",name:"Kho Ngoai Ngu",url:""},{id:"kb_khoa_hoc",name:"Kho Khoa Hoc",url:""},{id:"kb_tu_nhien",name:"Kho Tu Nhien",url:""},{id:"kb_xa_hoi",name:"Kho Xa Hoi",url:""}], installedCount:0, totalCount:7 },
  { name: "VN Khac", icon: "🏛️", description: "Lich am",
    mcps: [{id:"vn_lunar",name:"Lich Am",url:""}], installedCount:0, totalCount:1 },
  { name: "Khac", icon: "📦", description: "YouTube Transcript, HA Helper",
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
      const installed: Record<string, any> = {};
      data.forEach((p: any) => { if (p.installed) installed[p.id] = p; });
      setGroups(prev => prev.map(g => {
        const count = g.mcps.filter(m => installed[m.id]).length;
        return { ...g, installedCount: count, mcps: g.mcps.map(m => installed[m.id]?.url ? { ...m, url: installed[m.id].url } : m) };
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
        const hubMcps = hubData.mcps || [];
        setGroups(GROUPS.map(g => ({ ...g, mcps: g.mcps.map(m => {
          const h = hubMcps.find((hm: any) => hm.id === m.id);
          return h ? { ...m, url: h.url } : m;
        }) })));
      }
    } catch (e) { /* ignore */ }
    setConnecting(false);
    loadStatus();
  };

  const installGroup = async (group: McpGroup) => {
    setSaving(group.name);
    const allInstalled = group.installedCount === group.totalCount;
    for (const m of group.mcps) {
      try {
        if (allInstalled) { await request.post(`/api/mcp/uninstall/${m.id}`); }
        else { await request.post("/api/mcp/install", { id: m.id, url_override: m.url }); }
      } catch (e) {}
    }
    setGroups(prev => prev.map(g => g.name === group.name ? { ...g, installedCount: allInstalled ? 0 : g.totalCount } : g));
    setSaving(null);
  };

  if (loading) return (
    <div className="space-y-4">
      <div className="skeleton h-8 w-48" />
      <div className="skeleton h-4 w-80" />
      <div className="grid gap-4 md:grid-cols-2">
        {[...Array(6)].map((_, i) => <div key={i} className="skeleton h-32 rounded-lg" />)}
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="animate-in">
        <h1 className="text-xl font-bold">MCP Servers</h1>
        <p className="text-sm text-[var(--muted-foreground)] mt-0.5">
          Connect vn-mcp-hub · Manage at{" "}
          <a href={`${hubUrl}/studio`} target="_blank" className="text-[var(--primary)] hover:underline font-medium inline-flex items-center gap-0.5">
            Studio <ExternalLink className="size-3" />
          </a>
        </p>
      </div>

      {/* Hub URL bar */}
      <div className="card animate-in">
        <div className="card-body flex gap-3 items-end">
          <div className="flex-1">
            <label className="text-xs font-semibold text-[var(--muted-foreground)] uppercase tracking-wider mb-1.5 block">Hub URL</label>
            <input value={hubUrl} onChange={(e) => setHubUrl(e.target.value)}
              placeholder="http://vn-mcp-hub:8005"
              className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
          </div>
          <button onClick={connectHub} disabled={connecting} className="btn btn-primary">{connecting ? "Connecting..." : "Connect Hub"}</button>
        </div>
      </div>

      {/* MCP Groups */}
      <div className="grid gap-4 md:grid-cols-2">
        {groups.map((g, idx) => {
          const allOn = g.installedCount === g.totalCount && g.totalCount > 0;
          const partial = g.installedCount > 0 && !allOn;
          const statusVariant = allOn ? "success" : partial ? "warning" : "muted";
          return (
            <div key={g.name} onClick={() => installGroup(g)}
              className="card cursor-pointer animate-in hover:border-[var(--primary)]/30"
              style={{ animationDelay: `${idx * 0.05}s`, borderLeft: allOn ? "3px solid var(--accent)" : partial ? "3px solid #f6c23e" : undefined }}>
              <div className="card-body">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2.5">
                    <span className="text-xl">{g.icon}</span>
                    <div>
                      <h3 className="font-semibold text-sm">{g.name}</h3>
                      <p className="text-xs text-[var(--muted-foreground)] mt-0.5 max-w-xs">{g.description}</p>
                    </div>
                  </div>
                  <span className={`badge badge-${statusVariant} shrink-0`}>
                    {saving === g.name ? "..." : `${g.installedCount}/${g.totalCount}`}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {g.mcps.map(m => (
                    <span key={m.id} className="text-xs px-2 py-1 rounded-md bg-[var(--secondary)] text-[var(--secondary-foreground)]"
                      style={{ opacity: m.url ? 1 : 0.45 }}>
                      {m.name}{!m.url ? ' —' : ''}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
