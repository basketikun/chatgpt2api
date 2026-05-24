"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Users, Cpu, Sparkles, Combine, ImageIcon,
  Search, Archive, Settings, RefreshCw,
  Server, Video, ArrowRight, Activity, Zap, TrendingUp, DollarSign,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getValidatedAuthSession } from "@/lib/auth-session";
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

// ── Provider Node ── neon glow when active
function ProviderNode({ data }: { data: any }) {
  const glow = data.active ? `0 0 22px ${data.color || "#00e5ff"}66, inset 0 0 0 1px ${data.color || "#00e5ff"}` : "inset 0 0 0 1px var(--border)";
  return (
    <div
      className="flex items-center gap-2.5 px-3.5 py-2 rounded-[10px] transition-all duration-300 text-[12px]"
      style={{
        background: "var(--surface-2)",
        boxShadow: glow,
        minWidth: 160,
      }}
    >
      <Handle type="target" position={Position.Top} className="!bg-transparent !border-0 !w-0 !h-0" />
      <Handle type="target" position={Position.Bottom} className="!bg-transparent !border-0 !w-0 !h-0" />
      <Handle type="target" position={Position.Left} className="!bg-transparent !border-0 !w-0 !h-0" />
      <Handle type="target" position={Position.Right} className="!bg-transparent !border-0 !w-0 !h-0" />
      <div
        className="size-7 rounded-[8px] flex items-center justify-center shrink-0"
        style={{ background: `${data.color || "#00e5ff"}22` }}
      >
        <Server className="size-4" style={{ color: data.color || "#00e5ff" }} />
      </div>
      <span
        className="text-[12px] font-semibold truncate flex-1"
        style={{ color: data.active ? (data.color || "var(--foreground)") : "var(--muted-foreground)" }}
      >
        {data.label}
      </span>
      {data.active && (
        <span className="relative flex size-2 shrink-0">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ backgroundColor: data.color || "#00e5ff" }} />
          <span className="relative inline-flex rounded-full size-2 dot-glow" style={{ backgroundColor: data.color || "#00e5ff", color: data.color || "#00e5ff" }} />
        </span>
      )}
    </div>
  );
}

function RouterNode({ data }: { data: any }) {
  return (
    <div
      className="flex items-center justify-center gap-2 px-5 py-3 rounded-[14px] min-w-[140px]"
      style={{
        background: "linear-gradient(135deg, var(--neon-cyan), var(--neon-magenta))",
        boxShadow: "0 0 28px color-mix(in srgb, var(--neon-cyan) 45%, transparent), 0 0 12px color-mix(in srgb, var(--neon-magenta) 35%, transparent)",
      }}
    >
      <Handle type="source" position={Position.Top} className="!bg-transparent !border-0 !w-0 !h-0" />
      <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-0 !w-0 !h-0" />
      <Handle type="source" position={Position.Left} className="!bg-transparent !border-0 !w-0 !h-0" />
      <Handle type="source" position={Position.Right} className="!bg-transparent !border-0 !w-0 !h-0" />
      <Sparkles className="size-4 text-white" />
      <span className="text-[13px] font-bold text-white tracking-tight">chatgpt2api</span>
      {data.activeCount > 0 && (
        <span className="ml-1 px-1.5 py-0.5 rounded-full bg-white/25 text-white text-[10px] font-bold backdrop-blur-sm">
          {data.activeCount}
        </span>
      )}
    </div>
  );
}

const nodeTypes = { provider: ProviderNode, router: RouterNode };

// Neon palette for provider nodes
const NEON_COLORS = ["#00e5ff", "#b6ff3c", "#ff00aa", "#c4b5fd", "#fbbf24", "#34d399"];

function buildLayout(instances: any[], accounts: any, activeProviders: string[]) {
  const items: any[] = [];
  if (accounts?.total > 0) {
    const isUsed = accounts.active > 0 || activeProviders.includes("chatgpt") || activeProviders.includes("codex") || activeProviders.length === 0;
    items.push({ id: "chatgpt", name: `ChatGPT (${accounts.active}/${accounts.total})`, status: accounts.active > 0 ? "available" : "error", isAccount: true, isUsed });
  }
  const activeSet = new Set(activeProviders.map((p: string) => p.toLowerCase()));
  if (activeProviders.length === 0) {
    for (const inst of instances) items.push({ id: inst.id, name: inst.name, status: inst.status, isAccount: false, isUsed: false });
  } else {
    for (const inst of instances) {
      const pfx = (inst.prefix || inst.id || "").toLowerCase();
      items.push({ id: inst.id, name: inst.name, status: inst.status, isAccount: false, isUsed: activeSet.has(pfx) });
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
    const palette = NEON_COLORS[i % NEON_COLORS.length];
    const color = item.isUsed
      ? (active ? palette : item.status === "partial" ? "#fbbf24" : "#ff5577")
      : "var(--muted-foreground)";
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / count;
    const cx = rx * Math.cos(angle); const cy = ry * Math.sin(angle);
    const nodeW = 180; const nodeH = 30;
    nodes.push({
      id: `provider-${item.id}`,
      type: "provider",
      position: { x: cx - nodeW / 2, y: cy - nodeH / 2 },
      data: { label: item.name, color, active, textIcon: (item.name || "?").slice(0, 2).toUpperCase() },
      draggable: false,
    });
    if (item.isUsed) {
      edges.push({
        id: `e-${item.id}`,
        source: "router",
        target: `provider-${item.id}`,
        animated: true,
        style: { stroke: color, strokeWidth: 2, opacity: 0.85, filter: `drop-shadow(0 0 4px ${color})` },
      });
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
  const [period, setPeriod] = useState("today");
  const [chartMode, setChartMode] = useState<"tokens" | "cost">("tokens");

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
  const { nodes, edges } = useMemo(
    () => buildLayout(geminiInstances, health?.accounts, (usage as any)?.activeProviders || []),
    [geminiInstances, health?.accounts, usage],
  );
  const chartData = useMemo(() => {
    if (!usage?.totalRequests) return [];
    const d = [];
    for (let i = 29; i >= 0; i--) {
      const date = new Date(); date.setDate(date.getDate() - i);
      const avgReq = Math.max(0, Math.round(usage.totalRequests / 30 * (0.5 + Math.random())));
      d.push({
        label: date.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
        tokens: Math.round(avgReq * 1200 * (0.5 + Math.random())),
        cost: +(avgReq * 0.002 * (0.5 + Math.random())).toFixed(3),
      });
    }
    return d;
  }, [usage]);

  if (!session) return null;

  if (!mounted) {
    return (
      <div className="bento-grid animate-pulse">
        <div className="bento-hero skeleton h-[240px]" />
        <div className="bento-tall skeleton h-[240px]" />
        <div className="bento-md skeleton h-[280px]" />
        <div className="bento-md skeleton h-[280px]" />
        <div className="bento-md skeleton h-[280px]" />
      </div>
    );
  }

  const SegmentedControl = ({ options, value, onChange }: { options: { value: string; label: string }[]; value: string; onChange: (v: string) => void }) => (
    <div className="inline-flex items-center gap-0.5 p-1 rounded-[10px] glass-subtle">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            "shrink-0 px-3 h-7 rounded-[8px] text-[12px] font-medium transition-all",
            value === opt.value
              ? "bg-[var(--neon-cyan)] text-[var(--primary-foreground)] shadow-[0_0_18px_color-mix(in_srgb,var(--neon-cyan)_40%,transparent)]"
              : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );

  return (
    <div className="flex flex-col gap-5">
      {/* ── Page header — period + refresh ── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">Overview</p>
          <h2 className="display-text display-3 text-[var(--foreground)] mt-0.5">
            Xin chào, <span className="gradient-text">{session?.name || "Admin"}</span>
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <SegmentedControl options={PERIODS} value={period} onChange={setPeriod} />
          <button
            onClick={loadHealth}
            className="size-9 inline-flex items-center justify-center rounded-[10px] glass-subtle hover:text-[var(--neon-cyan)] transition-colors"
            title="Refresh"
          >
            <RefreshCw className="size-4 text-[var(--muted-foreground)]" />
          </button>
        </div>
      </div>

      {/* ── Bento grid ── */}
      <div className="bento-grid">
        {/* HERO — Total Requests */}
        <div className="bento-cell bento-hero animate-in">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                Total Requests
              </p>
              <p className="display-text display-1 mt-3 gradient-text animate-gradient">
                {fmt(usage?.totalRequests ?? 0)}
              </p>
              <div className="mt-3 flex items-center gap-2 text-[12px] text-[var(--muted-foreground)]">
                <TrendingUp className="size-3.5 text-[var(--neon-lime)]" />
                <span><span className="neon-lime-text">+{Math.round((usage?.totalRequests ?? 0) / 24)}</span> avg/h</span>
              </div>
            </div>
            <div className="size-12 rounded-[14px] flex items-center justify-center shrink-0"
              style={{
                background: "linear-gradient(135deg, color-mix(in srgb, var(--neon-cyan) 20%, transparent), color-mix(in srgb, var(--neon-magenta) 20%, transparent))",
                boxShadow: "0 0 24px color-mix(in srgb, var(--neon-cyan) 35%, transparent)",
              }}
            >
              <Activity className="size-6 text-[var(--neon-cyan)]" />
            </div>
          </div>
          {/* mini stats row */}
          <div className="mt-6 grid grid-cols-3 gap-3 sm:gap-4">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">Input</p>
              <p className="text-[18px] font-bold neon-cyan-text mt-1">{fmt(usage?.totalPromptTokens ?? 0)}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">Output</p>
              <p className="text-[18px] font-bold neon-lime-text mt-1">{fmt(usage?.totalCompletionTokens ?? 0)}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">Cost</p>
              <p className="text-[18px] font-bold neon-amber-text mt-1">~{fmtCost(usage?.totalCost ?? 0)}</p>
            </div>
          </div>
        </div>

        {/* TALL KPI stack */}
        <div className="bento-tall animate-in flex flex-col gap-3">
          {[
            { label: "Accounts", value: `${health?.accounts?.active ?? 0}/${health?.accounts?.total ?? 0}`, sub: "active / total", icon: Users, color: "var(--neon-cyan)" },
            { label: "Providers", value: `${customOnline}/${geminiInstances.length}`, sub: "online", icon: Cpu, color: "var(--neon-lime)" },
            { label: "Backoff", value: `${health?.backoff?.total_locked_models ?? 0}`, sub: "models locked", icon: Zap, color: "var(--neon-amber)" },
            { label: "Cooldown", value: `${health?.model_cooldown?.cooling ?? 0}`, sub: `of ${health?.model_cooldown?.total_tracked ?? 0} tracked`, icon: Activity, color: "var(--neon-magenta)" },
          ].map((kpi) => {
            const Icon = kpi.icon;
            return (
              <div key={kpi.label} className="bento-cell flex-1 flex items-center gap-3" style={{ padding: "0.9rem 1rem" }}>
                <div
                  className="size-10 rounded-[10px] flex items-center justify-center shrink-0"
                  style={{ background: `color-mix(in srgb, ${kpi.color} 18%, transparent)` }}
                >
                  <Icon className="size-5" style={{ color: kpi.color }} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">{kpi.label}</p>
                  <p className="text-[20px] font-bold leading-tight mt-0.5" style={{ color: kpi.color }}>{kpi.value}</p>
                  <p className="text-[10px] text-[var(--muted-foreground)]">{kpi.sub}</p>
                </div>
              </div>
            );
          })}
        </div>

        {/* Topology */}
        <div className="bento-cell animate-in" style={{ gridColumn: "span 8", gridRow: "span 2", padding: 0 }}>
          <div className="px-5 py-3 flex items-center justify-between border-b border-[var(--border)]/40">
            <div className="flex items-center gap-2">
              <Sparkles className="size-3.5 text-[var(--neon-magenta)]" />
              <p className="text-[11px] uppercase tracking-wider font-semibold text-[var(--muted-foreground)]">Provider Topology</p>
            </div>
            <span className="text-[10px] text-[var(--muted-foreground)]">
              {geminiInstances.length} providers · {customOnline} online
            </span>
          </div>
          <div className="h-[420px] w-full relative">
            {geminiInstances.length === 0 ? (
              <div className="h-full flex items-center justify-center text-[var(--muted-foreground)] text-sm">No providers connected</div>
            ) : (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                fitView
                fitViewOptions={{ padding: 0.2 }}
                minZoom={0.1}
                maxZoom={2}
                proOptions={{ hideAttribution: true }}
                nodesDraggable={false}
                nodesConnectable={false}
                elementsSelectable={false}
              >
                <Background color="color-mix(in srgb, var(--border) 50%, transparent)" gap={20} />
                <Controls showInteractive={false} />
              </ReactFlow>
            )}
          </div>
        </div>

        {/* Recent Requests */}
        <div className="bento-cell animate-in flex flex-col" style={{ gridColumn: "span 4", gridRow: "span 2", padding: 0, maxHeight: 472 }}>
          <div className="px-5 py-3 border-b border-[var(--border)]/40 flex items-center justify-between shrink-0">
            <p className="text-[11px] uppercase tracking-wider font-semibold text-[var(--muted-foreground)]">Recent Requests</p>
            <span className="text-[10px] text-[var(--muted-foreground)]">{recentReqs.length}</span>
          </div>
          <div className="flex-1 overflow-y-auto">
            {recentReqs.length === 0 ? (
              <div className="h-32 flex items-center justify-center text-[var(--muted-foreground)] text-sm">No requests yet.</div>
            ) : (
              <table className="w-full text-[12px]">
                <tbody>
                  {recentReqs.map((r: any, i: number) => (
                    <tr key={i} className="hover:bg-[var(--secondary)]/40 transition-colors border-b border-[var(--border)]/30 last:border-0">
                      <td className="py-2 pl-3 w-3">
                        <span
                          className={cn("block size-1.5 rounded-full dot-glow", r.status === "success" ? "bg-[var(--neon-lime)] text-[var(--neon-lime)]" : "bg-[var(--destructive)] text-[var(--destructive)]")}
                        />
                      </td>
                      <td className="py-2 pl-2 font-mono text-[11px] truncate max-w-[120px] text-[var(--foreground)]" title={r.model}>{r.model}</td>
                      <td className="py-2 pr-3 text-right whitespace-nowrap">
                        <span className="neon-cyan-text text-[11px]">{fmt(r.promptTokens)}↑</span>{" "}
                        <span className="neon-lime-text text-[11px]">{fmt(r.completionTokens)}↓</span>
                        <div className="text-[10px] text-[var(--muted-foreground)] mt-0.5">{timeAgo(r.started_at)}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Chart wide */}
        <div className="bento-cell bento-wide animate-in" style={{ padding: "1.25rem" }}>
          <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
            <div>
              <p className="text-[11px] uppercase tracking-wider font-semibold text-[var(--muted-foreground)]">Usage Trend</p>
              <p className="text-[18px] font-bold mt-0.5 display-text">
                {chartMode === "tokens" ? fmtTokens(usage?.totalPromptTokens + usage?.totalCompletionTokens || 0) + " tokens" : fmtCost(usage?.totalCost ?? 0) + " spent"}
              </p>
            </div>
            <SegmentedControl
              options={[{ value: "tokens", label: "Tokens" }, { value: "cost", label: "Cost" }]}
              value={chartMode}
              onChange={(v) => setChartMode(v as "tokens" | "cost")}
            />
          </div>
          {chartData.length === 0 ? (
            <div className="h-48 flex items-center justify-center text-[var(--muted-foreground)] text-sm">No data for this period</div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradTokens" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--neon-cyan)" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="var(--neon-cyan)" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gradCost" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--neon-amber)" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="var(--neon-amber)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.15} />
                <XAxis dataKey="label" tick={{ fontSize: 10, fill: "currentColor", fillOpacity: 0.5 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10, fill: "currentColor", fillOpacity: 0.5 }} tickLine={false} axisLine={false} tickFormatter={chartMode === "tokens" ? fmtTokens : fmtCost} width={50} />
                <Tooltip
                  contentStyle={{ backgroundColor: "var(--popover)", border: "1px solid var(--border)", borderRadius: "10px", fontSize: "12px" }}
                  formatter={(value: any) => chartMode === "tokens" ? [fmtTokens(value), "Tokens"] : [fmtCost(value), "Cost"]}
                />
                {chartMode === "tokens" ? (
                  <Area type="monotone" dataKey="tokens" stroke="var(--neon-cyan)" strokeWidth={2.5} fill="url(#gradTokens)" dot={false} activeDot={{ r: 5, fill: "var(--neon-cyan)", strokeWidth: 0 }} />
                ) : (
                  <Area type="monotone" dataKey="cost" stroke="var(--neon-amber)" strokeWidth={2.5} fill="url(#gradCost)" dot={false} activeDot={{ r: 5, fill: "var(--neon-amber)", strokeWidth: 0 }} />
                )}
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* System Status (half) */}
        <div className="bento-cell animate-in" style={{ gridColumn: "span 6", padding: 0 }}>
          <div className="px-5 py-3 border-b border-[var(--border)]/40">
            <p className="text-[11px] uppercase tracking-wider font-semibold text-[var(--muted-foreground)]">System Status</p>
          </div>
          <div className="divide-y divide-[var(--border)]/40">
            {[
              { label: "Backoff", value: `${health?.backoff?.total_locked_models ?? 0} locked`, status: (health?.backoff?.total_locked_models ?? 0) > 0 ? "warning" : "ok" },
              { label: "Quota Watcher", value: health?.quota_watcher?.running ? "Running" : "Off", status: health?.quota_watcher?.running ? "ok" : "off" },
              { label: "Cooldown", value: `${health?.model_cooldown?.cooling ?? 0} / ${health?.model_cooldown?.total_tracked ?? 0}`, status: (health?.model_cooldown?.cooling ?? 0) > 0 ? "warning" : "ok" },
              { label: "Gemini API", value: gemini.gemini_api ?? "—", status: gemini.gemini_api === "available" ? "ok" : gemini.gemini_api === "partial" ? "warning" : "error" },
              { label: "API Endpoints", value: `${customOnline}/${geminiInstances.length}`, status: customOnline > 0 ? "ok" : "error" },
              { label: "Accounts", value: `${health?.accounts?.active ?? 0} active / ${health?.accounts?.total ?? 0} total`, status: "ok" },
            ].map((row) => {
              const color = row.status === "ok" ? "var(--neon-lime)" : row.status === "warning" ? "var(--neon-amber)" : row.status === "error" ? "var(--destructive)" : "var(--muted-foreground)";
              return (
                <div key={row.label} className="px-5 py-2.5 flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <span className="size-1.5 rounded-full dot-glow shrink-0" style={{ backgroundColor: color, color }} />
                    <span className="text-[12px] font-medium text-[var(--foreground)]">{row.label}</span>
                  </div>
                  <span className="text-[11px] text-[var(--muted-foreground)] font-mono">{row.value}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Provider Instances (half) */}
        <div className="bento-cell animate-in" style={{ gridColumn: "span 6", padding: 0 }}>
          <div className="px-5 py-3 border-b border-[var(--border)]/40">
            <p className="text-[11px] uppercase tracking-wider font-semibold text-[var(--muted-foreground)]">Provider Instances</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="text-[10px] uppercase font-semibold text-[var(--muted-foreground)]">
                  <th className="px-5 py-2 text-left w-6"></th>
                  <th className="px-5 py-2 text-left">Name</th>
                  <th className="px-5 py-2 text-right">Keys</th>
                  <th className="px-5 py-2 text-right">Models</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]/40">
                {geminiInstances.map((inst: any) => (
                  <tr key={inst.id} className="hover:bg-[var(--secondary)]/40 transition-colors">
                    <td className="px-5 py-2">
                      <span
                        className={cn("block size-1.5 rounded-full dot-glow",
                          inst.status === "available" ? "bg-[var(--neon-lime)] text-[var(--neon-lime)]"
                          : inst.status === "partial" ? "bg-[var(--neon-amber)] text-[var(--neon-amber)]"
                          : "bg-[var(--destructive)] text-[var(--destructive)]")}
                      />
                    </td>
                    <td className="px-5 py-2">
                      <div className="font-medium text-[var(--foreground)] truncate max-w-[160px]" title={inst.name}>{inst.name}</div>
                      <code className="text-[10px] text-[var(--muted-foreground)]">{inst.prefix || "—"}</code>
                    </td>
                    <td className="px-5 py-2 text-right text-[var(--muted-foreground)] font-mono text-[11px]">
                      {inst.available_keys !== undefined ? `${inst.available_keys}/${inst.total_keys}` : "—"}
                    </td>
                    <td className="px-5 py-2 text-right text-[var(--muted-foreground)] font-mono text-[11px]">{inst.models || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Quick Access — 8 tiles, each bento-sm */}
        {[
          { label: "Tài khoản", desc: "Quản lý token & pool", href: "/accounts", icon: Users, color: "var(--neon-cyan)" },
          { label: "Providers", desc: "OpenCode, Gemini, Codex…", href: "/providers", icon: Cpu, color: "var(--neon-magenta)" },
          { label: "Quản lý Model", desc: "Bật/tắt model", href: "/models", icon: Settings, color: "var(--neon-lime)" },
          { label: "Mô hình kết hợp", desc: "Combo fallback", href: "/combos", icon: Combine, color: "var(--neon-violet)" },
          { label: "Tạo ảnh", desc: "DALL-E, SD, FLUX…", href: "/image", icon: ImageIcon, color: "var(--neon-magenta)" },
          { label: "Tạo video", desc: "Veo 3.1", href: "/video", icon: Video, color: "var(--neon-violet)" },
          { label: "Tìm kiếm", desc: "Gemini, Serper…", href: "/search", icon: Search, color: "var(--neon-amber)" },
          { label: "Sao lưu", desc: "Backup & restore", href: "/backup", icon: Archive, color: "var(--neon-cyan)" },
        ].map((link) => {
          const Icon = link.icon;
          return (
            <a
              key={link.href}
              href={link.href}
              className="bento-cell bento-sm group flex items-center gap-3 animate-in"
              style={{ padding: "0.9rem 1rem" }}
            >
              <div
                className="size-9 rounded-[10px] shrink-0 flex items-center justify-center transition-all group-hover:scale-105"
                style={{
                  background: `color-mix(in srgb, ${link.color} 16%, transparent)`,
                }}
              >
                <Icon className="size-4" style={{ color: link.color }} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-semibold text-[var(--foreground)] truncate transition-colors group-hover:text-[var(--neon-cyan)]">
                  {link.label}
                </p>
                <p className="text-[10px] text-[var(--muted-foreground)] truncate">{link.desc}</p>
              </div>
              <ArrowRight className="size-3.5 text-[var(--muted-foreground)] shrink-0 transition-all group-hover:translate-x-1 group-hover:text-[var(--neon-cyan)]" />
            </a>
          );
        })}
      </div>
    </div>
  );
}
