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
      const installed: Record<string, any> = {};
      data.forEach((p: any) => { if (p.installed) installed[p.id] = p; });
      setGroups(prev => prev.map(g => {
        const count = g.mcps.filter(m => installed[m.id]).length;
        return { 
          ...g, 
          installedCount: count,
          mcps: g.mcps.map(m => installed[m.id]?.url ? { ...m, url: installed[m.id].url } : m)
        };
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

  if (loading) return (
    <div className="p-8 space-y-4">
      <div className="skeleton h-8 w-48" />
      <div className="skeleton h-4 w-96" />
      <div className="grid gap-4 md:grid-cols-2">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="skeleton h-36 rounded-xl" />
        ))}
      </div>
    </div>
  );

  return (
    <div className="space-y-8 p-6">
      {/* Header with gradient accent */}
      <div className="animate-fade-slide-up">
        <h1 className="text-3xl font-bold tracking-tight">
          <span className="gradient-text">MCP Servers</span>
        </h1>
        <p className="text-[var(--muted-foreground)] text-sm mt-2 max-w-xl">
          Kết nối vn-mcp-hub. Bật/tắt nhóm MCP. Chi tiết từng MCP quản lý tại{" "}
          <a href={`${hubUrl}/studio`} target="_blank" className="text-[var(--primary)] underline decoration-[var(--primary)]/30 hover:decoration-[var(--primary)] transition-all">
            Studio
          </a>.
        </p>
      </div>

      {/* Hub connection bar — glass card */}
      <div className="glass-card rounded-2xl p-4 flex gap-3 items-end animate-fade-slide-up">
        <div className="flex-1">
          <label className="text-xs font-medium text-[var(--muted-foreground)] mb-1.5 block">
            Hub URL
          </label>
          <input
            value={hubUrl}
            onChange={(e) => setHubUrl(e.target.value)}
            placeholder="http://vn-mcp-hub:8005"
            className="w-full rounded-xl border border-[var(--border)] bg-[var(--background)] px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--ring)] transition-shadow"
          />
        </div>
        <button
          onClick={connectHub}
          disabled={connecting}
          className="btn-primary h-10"
        >
          {connecting ? (
            <span className="flex items-center gap-2">
              <span className="size-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Kết nối...
            </span>
          ) : "Kết nối Hub"}
        </button>
      </div>

      {/* MCP Groups Grid */}
      <div className="grid gap-4 md:grid-cols-2">
        {groups.map((g, idx) => {
          const allOn = g.installedCount === g.totalCount && g.totalCount > 0;
          const partial = g.installedCount > 0 && !allOn;
          return (
            <div
              key={g.name}
              onClick={() => installGroup(g)}
              className="card-elevated p-5 cursor-pointer group animate-fade-slide-up"
              style={{
                animationDelay: `${idx * 60}ms`,
                borderColor: allOn ? '#22c55e' : partial ? '#f59e0b' : undefined,
              }}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <span className="text-2xl group-hover:scale-110 transition-transform duration-300">
                    {g.icon}
                  </span>
                  <div>
                    <h3 className="font-semibold text-[var(--foreground)]">{g.name}</h3>
                    <p className="text-xs text-[var(--muted-foreground)] mt-0.5">{g.description}</p>
                  </div>
                </div>
                {/* Status badge */}
                <span className={`shrink-0 px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                  allOn ? 'bg-green-500/10 text-green-600 dark:text-green-400 border border-green-500/30' :
                  partial ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/30' :
                  'bg-[var(--muted)] text-[var(--muted-foreground)] border border-[var(--border)]'
                }`}>
                  {saving === g.name ? '...' : `${g.installedCount}/${g.totalCount}`}
                </span>
              </div>
              {/* MCP chips */}
              <div className="flex flex-wrap gap-1.5">
                {g.mcps.map(m => (
                  <span
                    key={m.id}
                    className="text-xs px-2.5 py-1 rounded-lg transition-all duration-200"
                    style={{
                      background: m.url ? 'var(--secondary)' : 'var(--muted)',
                      color: m.url ? 'var(--secondary-foreground)' : 'var(--muted-foreground)',
                      opacity: m.url ? 1 : 0.5,
                    }}
                  >
                    {m.name}{!m.url ? ' (chưa kết nối)' : ''}
                  </span>
                ))}
              </div>
              {/* Hover indicator */}
              <div className="mt-3 pt-3 border-t border-[var(--border)] flex items-center justify-between text-xs text-[var(--muted-foreground)]">
                <span>
                  {allOn ? '✅ Đã cài tất cả' : partial ? '⚠️ Cài một phần' : 'Nhấn để cài tất cả'}
                </span>
                <span className="opacity-0 group-hover:opacity-100 transition-opacity text-[var(--primary)]">
                  {allOn ? 'Gỡ tất cả →' : 'Cài tất cả →'}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
