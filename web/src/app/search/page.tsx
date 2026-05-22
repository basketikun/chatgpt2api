"use client";

import { useEffect, useState } from "react";
import { Search, CheckCircle2, Globe, Database, ArrowUp, ArrowDown, Cpu } from "lucide-react";
import { request } from "@/lib/request";
import { cn } from "@/lib/utils";

const SEARCH_BACKENDS = [
  { value: "gemini", label: "Gemini Google Search", desc: "Google Search qua Gemini API — cần API key AI Studio", icon: Search },
  { value: "serper", label: "Serper.dev", desc: "Google Search API nhanh — 2.500 req/tháng miễn phí", icon: Search },
  { value: "searxng", label: "SearXNG (tự cài)", desc: "Tự host, riêng tư, không giới hạn", icon: Database },
  { value: "brave", label: "Brave Search", desc: "Brave Search API — 2.000 req/tháng miễn phí", icon: Search },
];

type CustomProvider = {
  name: string;
  prefix: string;
};

export default function SearchPage() {
  const [config, setConfig] = useState<any>({});
  const [combo, setCombo] = useState<string[]>([]);
  const [geminiKey, setGeminiKey] = useState("");
  const [geminiModel, setGeminiModel] = useState("gemini-2.5-flash");
  const [customProviders, setCustomProviders] = useState<CustomProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    fetchConfig();
    fetchCustomProviders();
  }, []);

  async function fetchConfig() {
    try {
      const data = await request.get("/api/settings");
      const cfg = (data.data as any)?.config || {};
      const searchCfg = cfg.search || {};
      setConfig({ enabled: true, auto_detect: true, max_results: 3, ...searchCfg });
      setCombo(searchCfg.search_combo || ["gemini"]);
      const providers = cfg.providers || {};
      const geminiCfg = providers.gemini_free || {};
      setGeminiKey(geminiCfg.api_key || "");
      setGeminiModel(geminiCfg.model || "gemini-2.5-flash");
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function fetchCustomProviders() {
    try {
      const data = await request.get("/api/v1/custom-providers");
      const providers = (data.data as any)?.custom_providers || {};
      const list: CustomProvider[] = Object.entries(providers).map(([id, p]: any) => ({
        name: p.name || id,
        prefix: p.prefix || id,
      }));
      setCustomProviders(list);
    } catch (e) { console.error(e); }
  }

  function backendLabel(key: string): string {
    const builtin = SEARCH_BACKENDS.find(b => b.value === key);
    if (builtin) return builtin.label;
    if (key.startsWith("custom:")) {
      const cpId = key.slice(7);
      const cp = customProviders.find(p => p.prefix === cpId);
      return cp ? `${cp.name} (Custom API)` : key;
    }
    return key;
  }

  function backendDesc(key: string): string {
    if (key.startsWith("custom:")) return "Dùng model chat của custom provider để tìm kiếm";
    const builtin = SEARCH_BACKENDS.find(b => b.value === key);
    return builtin?.desc || "";
  }

  function toggleBackend(backend: string) {
    setCombo(prev => {
      if (prev.includes(backend)) return prev.filter(b => b !== backend);
      return [...prev, backend];
    });
  }

  function moveBackend(backend: string, direction: "up" | "down") {
    setCombo(prev => {
      const idx = prev.indexOf(backend);
      if (idx < 0) return prev;
      const next = [...prev];
      if (direction === "up" && idx > 0) {
        [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
      } else if (direction === "down" && idx < next.length - 1) {
        [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
      }
      return next;
    });
  }

  async function save() {
    setSaving(true);
    setMsg("");
    try {
      await request.post("/api/settings", {
        search: { ...config, search_combo: combo },
        providers: {
          ...config.providers || {},
          gemini_free: {
            enabled: true,
            api_key: geminiKey,
            model: geminiModel,
          },
        },
      });
      setMsg("Đã lưu!");
      setTimeout(() => setMsg(""), 2000);
    } catch (e: any) {
      setMsg("Lỗi: " + (e?.message || "unknown"));
    } finally {
      setSaving(false);
    }
  }

  // All available backends: builtin + custom providers
  const allBackends = [
    ...SEARCH_BACKENDS,
    ...customProviders.map(cp => ({
      value: `custom:${cp.prefix}`,
      label: `${cp.name} (Custom API)`,
      desc: `Dùng model của ${cp.name} để tìm kiếm — gửi prompt search đến chat endpoint`,
      icon: Cpu,
    })),
  ];

  if (loading) {
    return <div className="flex items-center justify-center py-20"><p className="text-stone-500">Đang tải...</p></div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1 border-b border-black/[0.04] pb-5">
        <h1 className="text-[24px] font-bold tracking-tight text-slate-900">Cấu hình tìm kiếm</h1>
        <p className="text-[14px] text-slate-500">
          Khi dùng model không có search built-in (cx/, oc/...), hệ thống sẽ tự tìm kiếm. Combo: thử lần lượt, backend trước lỗi → backend sau.
        </p>
      </div>

      {/* Enable */}
      <div className="rounded-[16px] p-5 card-3d card-tint-indigo">
        <label className="flex items-center gap-3 cursor-pointer">
          <input type="checkbox" checked={config.enabled !== false}
            onChange={(e) => setConfig({ ...config, enabled: e.target.checked })}
            className="size-4 accent-indigo-500" />
          <div>
            <span className="text-[14px] font-semibold text-slate-900">Bật tìm kiếm tự động</span>
            <p className="text-[13px] text-slate-500">Tự động phát hiện câu hỏi cần tìm kiếm và bổ sung kết quả</p>
          </div>
        </label>
      </div>

      {/* Gemini API Key */}
      <div className="rounded-[16px] p-5 card-3d card-tint-violet">
        <h3 className="text-[15px] font-bold text-slate-900 mb-3">Gemini API Key</h3>
        <input type="text" value={geminiKey}
          onChange={(e) => setGeminiKey(e.target.value)}
          placeholder="AIzaSy... (lấy tại aistudio.google.com/apikey)"
          className="w-full rounded-[10px] border border-slate-200 bg-slate-50 px-3 py-2.5 text-[13.5px] text-slate-900 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-300" />
        <div className="flex items-center gap-3 mt-3">
          <label className="text-[13px] text-slate-500 w-16">Model:</label>
          <select value={geminiModel} onChange={(e) => setGeminiModel(e.target.value)}
            className="rounded-[10px] border border-slate-200 bg-slate-50 px-2 py-1.5 text-[13px] text-slate-900 focus:border-indigo-400 focus:outline-none">
            <option value="gemini-3-flash-preview">gemini-3-flash-preview (Preview)</option>
            <option value="gemini-2.5-flash">gemini-2.5-flash (Stable)</option>
            <option value="gemini-2.0-flash">gemini-2.0-flash (Stable)</option>
          </select>
        </div>
      </div>

      {/* Search Combo */}
      <div className="rounded-[16px] p-5 card-main">
        <h3 className="text-[15px] font-bold text-slate-900 mb-3">
          Thứ tự tìm kiếm (Combo)
        </h3>
        <p className="text-xs text-stone-500 mb-4">
          Tích chọn backend và sắp xếp thứ tự ưu tiên. Backend đầu tiên được thử trước, nếu lỗi → thử backend tiếp theo. Có thể thêm custom provider làm search backend.
        </p>

        {/* Selected backends in priority order */}
        {combo.length > 0 && (
          <div className="space-y-1 mb-4">
            {combo.map((backend, idx) => {
              const info = allBackends.find(b => b.value === backend);
              if (!info) return null;
              const Icon = info.icon || Search;
              return (
                <div key={backend} className="flex items-center gap-2 rounded-lg border border-stone-200 bg-stone-50 px-3 py-2.5">
                  <span className={cn(
                    "text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center shrink-0",
                    idx === 0 ? "bg-emerald-500/20 text-emerald-600" : "bg-stone-200 text-stone-500",
                  )}>
                    {idx + 1}
                  </span>
                  <Icon className="size-4 text-stone-500" />
                  <div className="flex-1 min-w-0">
                    <span className="text-sm text-stone-800">{info.label}</span>
                    <p className="text-[10px] text-stone-400 truncate">{info.desc}</p>
                  </div>
                  <button onClick={() => moveBackend(backend, "up")} disabled={idx === 0}
                    className="p-0.5 text-stone-400 hover:text-stone-700 disabled:opacity-30">
                    <ArrowUp className="size-3.5" />
                  </button>
                  <button onClick={() => moveBackend(backend, "down")} disabled={idx === combo.length - 1}
                    className="p-0.5 text-stone-400 hover:text-stone-700 disabled:opacity-30">
                    <ArrowDown className="size-3.5" />
                  </button>
                  <button onClick={() => toggleBackend(backend)}
                    className="text-xs text-red-400 hover:text-red-600 ml-1">X</button>
                </div>
              );
            })}
          </div>
        )}

        {/* Available backends to add */}
        <div className="space-y-1">
          {allBackends.filter(b => !combo.includes(b.value)).map(b => {
            const Icon = b.icon || Search;
            return (
              <button key={b.value} type="button"
                onClick={() => toggleBackend(b.value)}
                className="flex w-full items-center gap-3 rounded-lg border border-stone-200 p-3 text-left hover:border-stone-300 hover:bg-stone-50 transition">
                <Icon className="size-4 text-stone-400" />
                <div className="flex-1">
                  <p className="text-sm text-stone-700">{b.label}</p>
                  <p className="text-xs text-stone-400">{b.desc}</p>
                </div>
                <span className="text-xs text-stone-400">+ Thêm</span>
              </button>
            );
          })}
        </div>

        {combo.length === 0 && (
          <p className="text-xs text-stone-400 italic">Chưa chọn backend nào — tìm kiếm sẽ bị tắt</p>
        )}
      </div>

      {/* ChatGPT note */}
      <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4">
        <div className="flex items-center gap-2">
          <Globe className="size-4 text-stone-500" />
          <span className="text-sm font-medium text-stone-700">ChatGPT & Custom API</span>
        </div>
        <p className="text-xs text-stone-500 mt-1">
          Model <code className="bg-stone-200 px-1 rounded">chatgpt/auto</code> tự tìm kiếm web nội bộ. Custom provider (như <code className="bg-stone-200 px-1 rounded">geminiapi</code>) gửi prompt search đến chat model — phù hợp với Gemini API có Google grounding.
        </p>
      </div>

      {/* Save */}
      <div className="flex justify-end gap-3">
        {msg && <span className={cn("text-sm", msg.startsWith("Lỗi") ? "text-red-500" : "text-emerald-600")}>{msg}</span>}
        <button type="button" onClick={save} disabled={saving}
          className="rounded-[12px] bg-slate-900 px-6 py-2.5 text-[14px] font-medium text-white hover:bg-slate-800 disabled:opacity-50">
          {saving ? "Đang lưu..." : "Lưu cài đặt"}
        </button>
      </div>
    </div>
  );
}
