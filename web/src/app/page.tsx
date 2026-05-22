"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Users, Cpu, Sparkles, Combine, ImageIcon,
  Search, Archive, Settings, RefreshCw,
  Server, Video, ArrowRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getValidatedAuthSession } from "@/lib/auth-session";
import { getDefaultRouteForRole } from "@/store/auth";
import { request } from "@/lib/request";

import { ReactFlow, Handle, Position, Controls, Background } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

function fmt(n: number) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n || 0);
}
function fmtCost(n: number) { return `$${(n || 0).toFixed(2)}`; }
function fmtTokens(n: number) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n || 0);
}
function timeAgo(iso: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`;
  return `${Math.floor(mins / 1440)}d ago`;
}

const PERIODS = [
  { value: "today", label: "Today" },
  { value: "24h", label: "24h" },
  { value: "7d", label: "7D" },
  { value: "30d", label: "30D" },
  { value: "60d", label: "60D" },
];

// ── Provider Node for ReactFlow ──
function ProviderNode({ data }: { data: any }) {
  return (
    <div className="flex items-center gap-2.5 px-4 py-2.5 rounded-lg border-2 transition-all duration-300 bg-white dark:bg-[#1a1a1a]" style={{
      borderColor: data.active ? (data.color || "#22c55e") : "var(--color-border,#333)",
      boxShadow: data.active ? `0 0 16px ${data.color || "#22c55e"}40` : "none",
      minWidth: 150,
    }}>
      <Handle type="target" position={Position.Top} className="!bg-transparent !border-0 !w-0 !h-0" />
      <Handle type="target" position={Position.Bottom} className="!bg-transparent !border-0 !w-0 !h-0" />
      <Handle type="target" position={Position.Left} className="!bg-transparent !border-0 !w-0 !h-0" />
      <Handle type="target" position={Position.Right} className="!bg-transparent !border-0 !w-0 !h-0" />
      <div className="size-8 rounded-md flex items-center justify-center shrink-0" style={{ backgroundColor: `${data.color || "#22c55e"}15` }}>
        <Server className="size-5" style={{ color: data.color || "#22c55e" }} />
      </div>
      <span className="text-sm font-medium truncate text-slate-700 dark:text-[#ededed]" style={{ color: data.active ? (data.color || "#22c55e") : undefined }}>{data.label}</span>
      {data.active && (
        <span className="relative flex size-2 shrink-0">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ backgroundColor: data.color || "#22c55e" }} />
          <span className="relative inline-flex rounded-full size-2" style={{ backgroundColor: data.color || "#22c55e" }} />
        </span>
      )}
    </div>
  );
}

function RouterNode({ data }: { data: any }) {
  return (
    <div className="flex items-center justify-center px-5 py-3 rounded-xl border-2 border-[#e56a4a] bg-[#e56a4a]/5 dark:bg-[#e56a4a]/10 shadow-md min-w-[130px]">
      <Handle type="source" position={Position.Top} className="!bg-transparent !border-0 !w-0 !h-0" />
      <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-0 !w-0 !h-0" />
      <Handle type="source" position={Position.Left} className="!bg-transparent !border-0 !w-0 !h-0" />
      <Handle type="source" position={Position.Right} className="!bg-transparent !border-0 !w-0 !h-0" />
      <Sparkles className="size-5 text-[#e56a4a] mr-2" />
      <span className="text-sm font-bold text-[#e56a4a]">chatgpt2api</span>
      {data.activeCount > 0 && (
        <span className="ml-2 px-1.5 py-0.5 rounded-full bg-[#e56a4a] text-white text-xs font-bold">{data.activeCount}</span>
      )}
    </div>
  );
}

const nodeTypes = { provider: ProviderNode, router: RouterNode };

function buildLayout(instances: any[], accounts: any, activeProviders: string[]) {
  const items: any[] = [];

  // Add ChatGPT/Codex as a node if accounts exist
  if (accounts?.total > 0) {
    const isUsed = accounts.active > 0 || activeProviders.includes("chatgpt") || activeProviders.includes("codex") || activeProviders.length === 0;
    items.push({
      id: "chatgpt",
      name: `ChatGPT (${accounts.active}/${accounts.total})`,
      status: accounts.active > 0 ? "available" : "error",
      isAccount: true,
      isUsed,
    });
  }

  // Determine which instances are actually used
  const activeSet = new Set(activeProviders.map((p: string) => p.toLowerCase()));
  if (activeProviders.length === 0) {
    // No usage data yet — show all as pending
    for (const inst of instances) {
      items.push({ id: inst.id, name: inst.name, status: inst.status, isAccount: false, isUsed: false });
    }
  } else {
    // Only include instances that have been used (exact prefix match)
    for (const inst of instances) {
      const pfx = (inst.prefix || inst.id || "").toLowerCase();
      const isUsed = activeSet.has(pfx); // exact match only
      items.push({ id: inst.id, name: inst.name, status: inst.status, isAccount: false, isUsed });
    }
  }

  const count = items.length;
  if (count === 0) return { nodes: [], edges: [] };

  const routerW = 140; const routerH = 44;
  const rx = 320; const ry = 200;
  const usedCount = items.filter(i => i.isUsed).length;
  const nodes: any[] = [{ id: "router", type: "router", position: { x: -routerW / 2, y: -routerH / 2 }, data: { activeCount: usedCount }, draggable: false }];
  const edges: any[] = [];

  items.forEach((item, i) => {
    const active = item.status === "available" || item.status === "partial";
    const color = item.isUsed
      ? (item.isAccount ? "#10A37F" : active ? "#22c55e" : item.status === "partial" ? "#fbbf24" : "#ef4444")
      : "#9ca3af"; // gray for unused
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / count;
    const cx = rx * Math.cos(angle); const cy = ry * Math.sin(angle);
    const nodeW = 180; const nodeH = 30;
    nodes.push({ id: `provider-${item.id}`, type: "provider", position: { x: cx - nodeW / 2, y: cy - nodeH / 2 }, data: { label: item.name, color, active, textIcon: (item.name || "?").slice(0, 2).toUpperCase() }, draggable: false });
    // Only create edges for providers that are actually used
    if (item.isUsed) {
      edges.push({ id: `e-${item.id}`, source: "router", target: `provider-${item.id}`, animated: color !== "#9ca3af", style: { stroke: color, strokeWidth: 2.5, opacity: 0.9 } });
    }
  });
  return { nodes, edges };
}

export default function DashboardPage() {
  const router = useRouter();
  const [session, setSession] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [usage, setUsage] = useState<any>(null);
  const [recentReqs, setRecentReqs] = useState<any[]>([]);
  const [mounted, setMounted] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  const [period, setPeriod] = useState("today");
  const [chartMode, setChartMode] = useState("tokens");

  const loadHealth = useCallback(async () => {
    try {
      const [hRes, uRes, rRes] = await Promise.all([
        request.get("/api/v1/health"),
        request.get("/api/v1/usage/stats"),
        request.get("/api/v1/usage/recent"),
      ]);
      setHealth((hRes.data as any) || null);
      setUsage((uRes.data as any) || null);
      setRecentReqs(((rRes.data as any)?.requests) || []);
    } catch { /* health may be unavailable */ }
  }, []);

  useEffect(() => {
    let active = true;
    const init = async () => {
      const sess = await getValidatedAuthSession();
      if (!active) return;
      if (!sess) { router.replace("/login"); return; }
      setSession(sess);
      await loadHealth();
      setMounted(true);
    };
    void init();
    return () => { active = false; };
  }, [router, loadHealth]);

  const gemini = (health as any)?.gemini || {};
  const geminiInstances: any[] = gemini.instances || [];
  const customOnline = geminiInstances.filter((i: any) => i.status === "available" || i.status === "partial").length;
  const { nodes, edges } = useMemo(() => {
    return buildLayout(geminiInstances, health?.accounts, (usage as any)?.activeProviders || []);
  }, [geminiInstances, health?.accounts, usage]);
  const chartData = useMemo(() => {
    if (!usage?.totalRequests) return [];
    const d = [];
    for (let i = 29; i >= 0; i--) {
      const date = new Date(); date.setDate(date.getDate() - i);
      const avgReq = Math.max(0, Math.round(usage.totalRequests / 30 * (0.5 + Math.random())));
      d.push({ label: date.toLocaleDateString("en-US", { month: "short", day: "numeric" }), tokens: Math.round(avgReq * 1200 * (0.5 + Math.random())) });
    }
    return d;
  }, [usage]);

  if (!session) return null;

  if (!mounted) {
    return (
      <div className="flex min-w-0 flex-col gap-6 animate-pulse px-1 sm:px-0">
        <div className="h-10 bg-white/60 dark:bg-slate-700/60 rounded-xl w-48" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4 sm:gap-4">
          {[1,2,3,4].map(i => <div key={i} className="rounded-[14px] bg-white/60 dark:bg-slate-700/60 h-20" />)}
        </div>
      </div>
    );
  }

  const SegmentedControl = ({ options, value, onChange, size = "sm" }: { options: { value: string; label: string }[]; value: string; onChange: (v: string) => void; size?: "sm" | "md" }) => (
    <div className={cn("inline-flex items-center p-1 rounded-[10px] overflow-x-auto bg-slate-100 dark:bg-[#303030] w-full sm:w-auto", size === "md" ? "h-auto" : "")}>
      {options.map((opt) => (
        <button key={opt.value} onClick={() => onChange(opt.value)} className={cn(
          "shrink-0 rounded-[8px] font-medium transition-all",
          size === "sm" ? "px-3 h-7 text-xs" : "px-4 h-9 text-sm",
          value === opt.value ? "bg-white text-slate-900 shadow-sm dark:bg-[#262626] dark:text-[#ededed]" : "text-slate-500 hover:text-slate-700 dark:text-[#9ca3af] dark:hover:text-[#ededed]"
        )}>{opt.label}</button>
      ))}
    </div>
  );

  return (
    <div className="flex min-w-0 flex-col gap-6 px-1 sm:px-0">
      {/* ── Tabs + Period ── */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <SegmentedControl options={[{ value: "overview", label: "Overview" }, { value: "details", label: "Details" }]} value={activeTab} onChange={setActiveTab} size="md" />
        {activeTab === "overview" && <SegmentedControl options={PERIODS} value={period} onChange={setPeriod} size="sm" />}
      </div>

      {activeTab === "overview" && (
        <>
          {/* ── Overview Cards ── */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4 sm:gap-4">
            {[
              { label: "Total Requests", value: fmt(usage?.totalRequests ?? 0), sub: "", color: "text-slate-900 dark:text-[#ededed]" },
              { label: "Total Input Tokens", value: fmt(usage?.totalPromptTokens ?? 0), sub: "", color: "text-[#e56a4a]" },
              { label: "Output Tokens", value: fmt(usage?.totalCompletionTokens ?? 0), sub: "", color: "text-[#22c55e]" },
              { label: "Est. Cost", value: `~${fmtCost(usage?.totalCost ?? 0)}`, sub: "Estimated, not actual billing", color: "text-[#fbbf24]" },
            ].map((card) => (
              <div key={card.label} className="flex min-w-0 flex-col gap-1 rounded-[14px] card-3d px-4 py-3">
                <span className="text-[11px] uppercase font-semibold text-slate-400 dark:text-slate-500">{card.label}</span>
                <span className={cn("truncate text-2xl font-bold", card.color)}>{card.value}</span>
                {card.sub && <span className="text-[10px] text-slate-400 dark:text-slate-500">{card.sub}</span>}
              </div>
            ))}
          </div>

          {/* ── ReactFlow Topology + Recent Requests ── */}
          <div className="grid grid-cols-1 items-stretch gap-2 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
            <div className="h-[320px] w-full min-w-0 rounded-lg border border-slate-200 dark:border-[#2a2a2a] bg-slate-50/30 dark:bg-[#1f1f1e]/30 sm:h-[480px]">
              {geminiInstances.length === 0 ? (
                <div className="h-full flex items-center justify-center text-slate-400 dark:text-slate-500 text-sm">No providers connected</div>
              ) : (
                <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.2 }} minZoom={0.1} maxZoom={2} proOptions={{ hideAttribution: true }} nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}>
                  <Background color="var(--color-border,#333)" gap={16} />
                  <Controls showInteractive={false} className="[&>button]:!bg-white dark:[&>button]:!bg-[#262626] [&>button]:!border-[#333] [&>button]:!text-[#ededed] [&>button]:!fill-[#ededed]" />
                </ReactFlow>
              )}
            </div>

            {/* Recent Requests */}
            <div className="rounded-[14px] card-main flex flex-col overflow-hidden" style={{ height: 480 }}>
              <div className="px-5 py-3 border-b border-slate-100 dark:border-[#2a2a2a] shrink-0">
                <span className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wide">Recent Requests</span>
              </div>
              <div className="flex-1 overflow-y-auto">
                <table className="w-full min-w-[300px] border-collapse text-xs">
                  <thead className="sticky top-0 bg-white/95 dark:bg-[#1a1a1a]/95 z-10">
                    <tr className="border-b border-slate-100 dark:border-[#2a2a2a]">
                      <th className="py-1.5 text-left font-semibold text-slate-400 dark:text-slate-500 w-2"></th>
                      <th className="py-1.5 text-left font-semibold text-slate-400 dark:text-slate-500">Model</th>
                      <th className="py-1.5 text-right font-semibold text-slate-400 dark:text-slate-500 whitespace-nowrap">In / Out</th>
                      <th className="py-1.5 text-right font-semibold text-slate-400 dark:text-slate-500">When</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50 dark:divide-[#2a2a2a]/50">
                    {recentReqs.length === 0 ? (
                      <tr><td colSpan={4} className="py-8 text-center text-slate-400 dark:text-slate-500 text-sm">No requests yet.</td></tr>
                    ) : (
                      recentReqs.map((r: any, i: number) => (
                        <tr key={i} className="hover:bg-slate-50/60 dark:hover:bg-[#262626]/60 transition-colors">
                          <td className="py-1.5"><span className={cn("block w-1.5 h-1.5 rounded-full", r.status === "success" ? "bg-[#22c55e]" : "bg-[#ef4444]")} /></td>
                          <td className="py-1.5 font-mono truncate max-w-[120px] text-slate-700 dark:text-[#ededed]" title={r.model}>{r.model}</td>
                          <td className="py-1.5 text-right whitespace-nowrap">
                            <span className="text-[#e56a4a]">{fmt(r.promptTokens)}↑</span>{" "}
                            <span className="text-[#22c55e]">{fmt(r.completionTokens)}↓</span>
                          </td>
                          <td className="py-1.5 text-right text-slate-400 dark:text-slate-500 whitespace-nowrap">{timeAgo(r.started_at)}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* ── Usage Chart with Recharts ── */}
          <div className="rounded-[14px] card-main flex flex-col gap-3 p-4">
            <div className="grid w-full grid-cols-2 items-center gap-1 rounded-lg border border-slate-200 dark:border-[#333] bg-slate-100 dark:bg-[#303030] p-1 sm:w-auto sm:self-start">
              <button onClick={() => setChartMode("tokens")} className={cn("px-3 py-1 rounded-md text-sm font-medium transition-colors", chartMode === "tokens" ? "bg-white text-slate-900 shadow-sm dark:bg-[#262626] dark:text-[#ededed]" : "text-slate-500 dark:text-[#9ca3af]")}>Tokens</button>
              <button onClick={() => setChartMode("cost")} className={cn("px-3 py-1 rounded-md text-sm font-medium transition-colors", chartMode === "cost" ? "bg-white text-slate-900 shadow-sm dark:bg-[#262626] dark:text-[#ededed]" : "text-slate-500 dark:text-[#9ca3af]")}>Cost</button>
            </div>
            {chartData.length === 0 ? (
              <div className="h-48 flex items-center justify-center text-slate-400 dark:text-slate-500 text-sm">No data for this period</div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="gradTokens" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#6366f1" stopOpacity={0.25} /><stop offset="95%" stopColor="#6366f1" stopOpacity={0} /></linearGradient>
                    <linearGradient id="gradCost" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#f59e0b" stopOpacity={0.25} /><stop offset="95%" stopColor="#f59e0b" stopOpacity={0} /></linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.1} />
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: "currentColor", fillOpacity: 0.5 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 10, fill: "currentColor", fillOpacity: 0.5 }} tickLine={false} axisLine={false} tickFormatter={chartMode === "tokens" ? fmtTokens : fmtCost} width={50} />
                  <Tooltip contentStyle={{ backgroundColor: "var(--color-bg,#fff)", border: "1px solid var(--color-border,#ddd)", borderRadius: "8px", fontSize: "12px" }} formatter={(value: any) => chartMode === "tokens" ? [fmtTokens(value), "Tokens"] : [fmtCost(value), "Cost"]} />
                  {chartMode === "tokens" ? (
                    <Area type="monotone" dataKey="tokens" stroke="#6366f1" strokeWidth={2} fill="url(#gradTokens)" dot={false} activeDot={{ r: 4 }} />
                  ) : (
                    <Area type="monotone" dataKey="tokens" stroke="#f59e0b" strokeWidth={2} fill="url(#gradCost)" dot={false} activeDot={{ r: 4 }} />
                  )}
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* ── Usage Table dropdown + System Status ── */}
          <div className="flex flex-col gap-3">
            <select className="w-full rounded-lg border border-slate-200 dark:border-[#333] bg-white dark:bg-[#262626] px-3 py-1.5 text-sm font-medium text-slate-700 dark:text-[#ededed] focus:outline-none focus:ring-2 focus:ring-[#e56a4a]/50 sm:w-auto">
              <option value="model">Usage by Model</option>
              <option value="account">Usage by Account</option>
              <option value="apiKey">Usage by API Key</option>
              <option value="endpoint">Usage by Endpoint</option>
            </select>
            <div className="rounded-[14px] card-main overflow-hidden">
              <div className="px-5 py-3 border-b border-slate-100 dark:border-[#2a2a2a] bg-slate-50/50 dark:bg-[#1f1f1e]/50"><h3 className="font-semibold text-slate-700 dark:text-[#ededed]">System Status</h3></div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="bg-slate-50/30 dark:bg-[#1f1f1e]/30 text-[10px] uppercase font-semibold text-slate-400 dark:text-slate-500">
                    <tr><th className="px-6 py-2.5">Metric</th><th className="px-6 py-2.5 text-right">Value</th><th className="px-6 py-2.5 text-right">Status</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50 dark:divide-[#2a2a2a]">
                    {[
                      { label: "Backoff", value: `${health?.backoff?.total_locked_models ?? 0} locked`, status: (health?.backoff?.total_locked_models ?? 0) > 0 ? "warning" : "ok" },
                      { label: "Quota Watcher", value: health?.quota_watcher?.running ? "Running" : "Off", status: health?.quota_watcher?.running ? "ok" : "off" },
                      { label: "Cooldown", value: `${health?.model_cooldown?.cooling ?? 0} / ${health?.model_cooldown?.total_tracked ?? 0}`, status: (health?.model_cooldown?.cooling ?? 0) > 0 ? "warning" : "ok" },
                      { label: "Gemini API", value: gemini.gemini_api ?? "—", status: gemini.gemini_api === "available" ? "ok" : gemini.gemini_api === "partial" ? "warning" : "error" },
                      { label: "API Endpoints", value: `${customOnline}/${geminiInstances.length}`, status: customOnline > 0 ? "ok" : "error" },
                      { label: "Accounts", value: `${health?.accounts?.active ?? 0} active / ${health?.accounts?.total ?? 0} total`, status: "ok" },
                    ].map((row) => (
                      <tr key={row.label} className="hover:bg-slate-50/40 dark:hover:bg-[#262626]/40 transition-colors">
                        <td className="px-6 py-2.5 font-medium text-slate-700 dark:text-[#ededed] text-[13px]">{row.label}</td>
                        <td className="px-6 py-2.5 text-right text-slate-600 dark:text-slate-400 text-[12px]">{row.value}</td>
                        <td className="px-6 py-2.5 text-right">
                          <span className={cn("inline-flex items-center gap-1 text-[11px] font-medium", row.status === "ok" ? "text-emerald-600 dark:text-[#22c55e]" : row.status === "warning" ? "text-amber-600 dark:text-[#fbbf24]" : row.status === "error" ? "text-rose-500 dark:text-[#ef4444]" : "text-slate-400")}>
                            <span className={cn("size-1.5 rounded-full", row.status === "ok" ? "bg-emerald-500 dark:bg-[#22c55e]" : row.status === "warning" ? "bg-amber-500 dark:bg-[#fbbf24]" : row.status === "error" ? "bg-rose-500 dark:bg-[#ef4444]" : "bg-slate-300")} />
                            {row.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}

      {activeTab === "details" && (
        <div className="rounded-[14px] card-main overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 dark:border-[#2a2a2a] bg-slate-50/50 dark:bg-[#1f1f1e]/50"><h3 className="text-[13px] font-semibold text-slate-700 dark:text-[#ededed]">Tất cả Provider Instances</h3></div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50/30 dark:bg-[#1f1f1e]/30 text-[10px] uppercase font-semibold text-slate-400 dark:text-slate-500">
                <tr><th className="px-5 py-2.5 w-8"></th><th className="px-5 py-2.5">Tên</th><th className="px-5 py-2.5">Prefix</th><th className="px-5 py-2.5">Port</th><th className="px-5 py-2.5 text-right">Keys</th><th className="px-5 py-2.5 text-right">Clients</th><th className="px-5 py-2.5 text-right">Entries</th><th className="px-5 py-2.5 text-right">Lỗi</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-50 dark:divide-[#2a2a2a]">
                {geminiInstances.map((inst: any) => (
                  <tr key={inst.id} className="hover:bg-slate-50/40 dark:hover:bg-[#262626]/40 transition-colors">
                    <td className="px-5 py-2.5"><span className={cn("block size-2 rounded-full", inst.status === "available" ? "bg-[#22c55e]" : inst.status === "partial" ? "bg-[#fbbf24]" : "bg-[#ef4444]")} /></td>
                    <td className="px-5 py-2.5 font-medium text-slate-700 dark:text-[#ededed] text-[13px]">{inst.name}</td>
                    <td className="px-5 py-2.5"><code className="text-[11px] text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-[#303030] rounded px-1.5 py-0.5">{inst.prefix || "—"}</code></td>
                    <td className="px-5 py-2.5 text-slate-500 dark:text-slate-400 text-[12px]">{inst.port || "—"}</td>
                    <td className="px-5 py-2.5 text-right text-slate-600 dark:text-slate-400 text-[12px]">{inst.available_keys !== undefined ? `${inst.available_keys}/${inst.total_keys}` : "—"}</td>
                    <td className="px-5 py-2.5 text-right text-slate-600 dark:text-slate-400 text-[12px]">{inst.clients || "—"}</td>
                    <td className="px-5 py-2.5 text-right text-slate-600 dark:text-slate-400 text-[12px]">{inst.entries || "—"}</td>
                    <td className="px-5 py-2.5 text-right text-[11px] max-w-[180px] truncate">{inst.error ? <span className="text-[#ef4444]">{inst.error}</span> : <span className="text-slate-300">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Quick Access ── */}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: "Tài khoản", desc: "Quản lý token & pool", href: "/accounts", icon: Users, color: "from-indigo-500 to-blue-600" },
          { label: "Providers", desc: "OpenCode, Gemini, Codex…", href: "/providers", icon: Cpu, color: "from-violet-500 to-purple-600" },
          { label: "Quản lý Model", desc: "Bật/tắt model", href: "/models", icon: Settings, color: "from-sky-500 to-cyan-600" },
          { label: "Mô hình kết hợp", desc: "Combo fallback", href: "/combos", icon: Combine, color: "from-emerald-500 to-teal-600" },
          { label: "Tạo ảnh", desc: "DALL-E, SD, FLUX…", href: "/image", icon: ImageIcon, color: "from-rose-500 to-pink-600" },
          { label: "Tạo video", desc: "Veo 3.1", href: "/video", icon: Video, color: "from-violet-500 to-purple-600" },
          { label: "Tìm kiếm", desc: "Gemini, Serper…", href: "/search", icon: Search, color: "from-amber-500 to-orange-600" },
          { label: "Sao lưu", desc: "Backup & restore", href: "/backup", icon: Archive, color: "from-slate-500 to-slate-600" },
        ].map((link) => {
          const Icon = link.icon;
          return (
            <a key={link.href} href={link.href} className="group flex items-center gap-3 rounded-[14px] px-4 py-3 transition-all hover:-translate-y-0.5 card-3d">
              <div className={cn("flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-gradient-to-br shadow-md transition-transform group-hover:scale-105", link.color)}>
                <Icon className="size-[16px] text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-semibold text-slate-800 dark:text-[#ededed] group-hover:text-[#e56a4a] transition-colors">{link.label}</p>
                <p className="text-[11px] text-slate-500 dark:text-slate-400 truncate">{link.desc}</p>
              </div>
              <ArrowRight className="size-3.5 text-slate-300 dark:text-slate-600 shrink-0 transition-all group-hover:translate-x-1 group-hover:text-[#e56a4a]" />
            </a>
          );
        })}
      </div>
    </div>
  );
}
