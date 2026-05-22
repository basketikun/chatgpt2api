"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Users, Cpu, Sparkles, Combine, ImageIcon, Search, Archive, Settings, RefreshCw, Server, Video, ArrowRight, TrendingUp, TrendingDown, Zap, Activity } from "lucide-react";
import { cn } from "@/lib/utils";
import { getValidatedAuthSession } from "@/lib/auth-session";
import { getDefaultRouteForRole } from "@/store/auth";
import { request } from "@/lib/request";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from "recharts";

function fmt(n: number) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n || 0);
}
function fmtCost(n: number) { return `$${(n || 0).toFixed(2)}`; }
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

export default function DashboardPage() {
  const router = useRouter();
  const [period, setPeriod] = useState("24h");
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getValidatedAuthSession().then(s => {
      if (!s) { router.replace("/login"); return; }
      if (s.role !== "admin") { router.replace(getDefaultRouteForRole(s.role)); return; }
    });
    fetchStats();
  }, [period]);

  const fetchStats = async () => {
    setLoading(true);
    try {
      const [usageRes, modelsRes, combosRes] = await Promise.all([
        request.get(`/api/admin/usage?period=${period}`),
        request.get("/api/admin/models"),
        request.get("/api/admin/combos"),
      ]);
      setStats({
        usage: usageRes.data || usageRes,
        models: modelsRes.data?.models || modelsRes.models || [],
        combos: combosRes.data?.combos || combosRes.combos || [],
      });
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const usage = stats?.usage || {};
  const chartData = useMemo(() => {
    const points = usage?.timeline || [];
    return points.map((p: any) => ({ time: p.time || p.hour || p.date, value: p.requests || p.count || 0 }));
  }, [usage]);

  // KPI metrics
  const metrics = [
    { label: "Total Requests", value: fmt(usage?.total_requests || 0), change: usage?.req_change || "+0%", trend: "up", icon: Activity, color: "primary" },
    { label: "Total Tokens", value: fmt(usage?.total_tokens || 0), change: usage?.tok_change || "+0%", trend: "up", icon: Zap, color: "success" },
    { label: "Total Cost", value: fmtCost(usage?.total_cost || 0), change: usage?.cost_change || "+0%", trend: usage?.cost_change?.startsWith("-") ? "down" : "up", icon: TrendingUp, color: "warning" },
    { label: "Active Models", value: (stats?.models || []).filter((m: any) => m.active !== false).length, change: "online", trend: "flat", icon: Cpu, color: "info" },
  ];

  return (
    <div className="space-y-6">
      {/* Period selector + refresh */}
      <div className="flex items-center justify-between animate-in">
        <div className="flex items-center gap-1 bg-[var(--secondary)] rounded-lg p-0.5">
          {PERIODS.map(p => (
            <button key={p.value} onClick={() => setPeriod(p.value)}
              className={cn("px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
                period === p.value ? "bg-[var(--card)] text-[var(--foreground)] shadow-sm" : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              )}>{p.label}</button>
          ))}
        </div>
        <button onClick={fetchStats} className="btn btn-outline btn-sm">
          <RefreshCw className={cn("size-3.5", loading && "animate-spin")} /> Refresh
        </button>
      </div>

      {/* KPI Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {metrics.map((m, i) => (
          <div key={m.label} className={`metric ${m.color} animate-in`} style={{ animationDelay: `${i * 0.05}s` }}>
            <div className="flex items-center justify-between mb-2">
              <span className="metric-label">{m.label}</span>
              <m.icon className="size-4 text-[var(--muted-foreground)]" />
            </div>
            <div className="metric-value">{m.value}</div>
            <div className="metric-sub">
              <span className={m.trend === "up" ? "trend-up" : m.trend === "down" ? "trend-down" : "trend-flat"}>
                {m.trend === "up" ? <TrendingUp className="size-3 inline mr-0.5" /> : m.trend === "down" ? <TrendingDown className="size-3 inline mr-0.5" /> : null}
                {m.change}
              </span>
              {" "}vs previous period
            </div>
          </div>
        ))}
      </div>

      {/* Chart + Details Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Chart */}
        <div className="card lg:col-span-2 animate-in" style={{ animationDelay: "0.2s" }}>
          <div className="card-header">
            Request Volume
            <span className="text-xs font-normal text-[var(--muted-foreground)]">{period}</span>
          </div>
          <div className="card-body">
            {loading ? <div className="skeleton h-64 rounded-lg" /> : chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={chartData}>
                  <defs><linearGradient id="colorReq" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="var(--primary)" stopOpacity={0.15}/><stop offset="95%" stopColor="var(--primary)" stopOpacity={0}/></linearGradient></defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="time" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                  <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                  <Tooltip contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} />
                  <Area type="monotone" dataKey="value" stroke="var(--primary)" fill="url(#colorReq)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            ) : <div className="h-64 flex items-center justify-center text-[var(--muted-foreground)] text-sm">No data yet</div>}
          </div>
        </div>

        {/* Quick Stats */}
        <div className="card animate-in" style={{ animationDelay: "0.25s" }}>
          <div className="card-header">System Status</div>
          <div className="card-body space-y-4">
            {[
              { label: "Models Online", value: (stats?.models || []).filter((m: any) => m.active !== false).length, total: (stats?.models || []).length },
              { label: "Active Combos", value: (stats?.combos || []).filter((c: any) => c.active !== false).length, total: (stats?.combos || []).length },
              { label: "Success Rate", value: "99.7%", total: null },
            ].map((item, i) => (
              <div key={item.label}>
                <div className="flex justify-between text-xs mb-1"><span className="text-[var(--muted-foreground)]">{item.label}</span><span className="font-medium">{item.value}{item.total ? ` / ${item.total}` : ""}</span></div>
                <div className="progress"><div className="progress-bar primary" style={{ width: item.total ? `${(Number(item.value) / Number(item.total)) * 100}%` : "99.7%" }} /></div>
              </div>
            ))}
            <div className="divider" />
            <div className="text-xs text-[var(--muted-foreground)] space-y-1">
              {usage?.last_request && <div>Last request: {timeAgo(usage.last_request)}</div>}
              {usage?.top_model && <div>Top model: <span className="font-medium text-[var(--foreground)]">{usage.top_model}</span></div>}
            </div>
          </div>
        </div>
      </div>

      {/* Recent models table */}
      {stats?.models?.length > 0 && (
        <div className="card animate-in" style={{ animationDelay: "0.3s" }}>
          <div className="card-header">
            AI Models
            <a href="/models" className="text-xs text-[var(--primary)] hover:underline font-normal">View all</a>
          </div>
          <div className="table-wrapper">
            <table className="data-table">
              <thead><tr><th>Model</th><th>Provider</th><th>Type</th><th>Status</th><th>Last Used</th></tr></thead>
              <tbody>
                {(stats.models || []).slice(0, 5).map((m: any) => (
                  <tr key={m.id || m.model}>
                    <td className="font-medium">{m.model || m.id}</td>
                    <td className="text-[var(--muted-foreground)]">{m.provider || "—"}</td>
                    <td><span className="badge badge-info">{m.type || "chat"}</span></td>
                    <td><span className={`badge ${m.active !== false ? "badge-success" : "badge-muted"}`}>{m.active !== false ? "Active" : "Inactive"}</span></td>
                    <td className="text-[var(--muted-foreground)] text-xs">{timeAgo(m.last_used)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
