// @ts-nocheck — deprecated, use individual cards instead
"use client";

import { LoaderCircle, Save, Cpu, Sliders, Combine } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useSettingsStore } from "../store";

export function ProvidersCard() {
  const config = useSettingsStore((state) => state.config);
  const isLoadingConfig = useSettingsStore((state) => state.isLoadingConfig);
  const isSavingConfig = useSettingsStore((state) => state.isSavingConfig);
  const saveConfig = useSettingsStore((state) => state.saveConfig);

  const [geminiKeys, setGeminiKeys] = useState("");
  const [serperKeys, setSerperKeys] = useState("");
  const [comboText, setComboText] = useState("");
  const [initialized, setInitialized] = useState(false);

  // Sync from store on first load
  if (!initialized && config && Object.keys(config).length > 0) {
    const p = config.providers || {};
    const gemini = p.gemini_free || {};
    const serper = p.serper || {};
    const allGemini = [...new Set([gemini.api_key || "", ...(gemini.api_keys || [])])].filter(Boolean).join("\n");
    const allSerper = [...new Set([serper.api_key || "", ...(serper.api_keys || [])])].filter(Boolean).join("\n");
    const combos = config.combo_models || {};
    setGeminiKeys(allGemini);
    setSerperKeys(allSerper);
    setComboText(Object.entries(combos).map(([k, v]) => `${k}=${(v as string[]).join(",")}`).join("\n"));
    setInitialized(true);
  }

  function updateProviderConfig(name: string, keys: string) {
    const keyList = keys.split("\n").map(k => k.trim()).filter(Boolean);
    const p = { ...(config?.providers || {}) };
    p[name] = {
      ...(p[name] || {}),
      api_keys: keyList,
      api_key: keyList.length > 0 ? keyList[0] : "",
      enabled: p[name]?.enabled !== false,
    };
    setField("providers", p);
  }

  function handleSave() {
    // First sync the latest text values
    updateProviderConfig("gemini_free", geminiKeys);
    updateProviderConfig("serper", serperKeys);
    // Then save via store
    void saveConfig();
  }

  if (isLoadingConfig || !config) {
    return (
      <Card className="rounded-2xl card-3d card-tint-sky">
        <CardContent className="flex items-center justify-center p-10">
          <LoaderCircle className="size-5 animate-spin text-stone-500" />
        </CardContent>
      </Card>
    );
  }

  const providers = config.providers || {};
  const backends = config.backends || {};
  const rateLimit = config.rate_limit || {};
  const ninerouter = config.ninerouter || {};

  return (
    <Card className="rounded-2xl card-3d card-tint-sky">
      <CardContent className="space-y-6 p-6">

        {/* ── Providers ── */}
        <div>
          <div className="flex items-center gap-2 mb-4">
            <Cpu className="size-5 text-stone-700" />
            <h3 className="text-sm font-semibold text-stone-900">Nhà cung cấp AI</h3>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {Object.entries({
              opencode: { desc: "OpenCode (free, no auth)", type: "info" },
              gemini_free: { desc: "Gemini AI Studio (API key)", type: "textarea", state: geminiKeys, setState: setGeminiKeys, handler: "gemini" },
              openrouter: { desc: "OpenRouter (API key)", type: "input", key: "api_key" },
              sdwebui: { desc: "SD WebUI (local)", type: "input", key: "base_url", placeholder: "http://localhost:7860" },
              huggingface: { desc: "HuggingFace (API key)", type: "input", key: "api_key" },
              cloudflare_ai: { desc: "Cloudflare AI", type: "cloudflare" },
              serper: { desc: "Serper.dev Search (API key)", type: "textarea", state: serperKeys, setState: setSerperKeys, handler: "serper" },
              searxng: { desc: "SearXNG Search (base URL)", type: "input", key: "base_url", placeholder: "http://localhost:8080" },
              brave: { desc: "Brave Search (API key)", type: "input", key: "api_key" },
            } as Record<string, any>).map(([name, meta]) => {
              const p = providers[name] || {};
              return (
                <div key={name} className="rounded-xl border border-stone-200 bg-stone-100 p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-stone-700">{name}</span>
                    <label className="flex items-center gap-1 text-xs">
                      <input type="checkbox" checked={p.enabled !== false}
                        onChange={(e) => {
                          const newProviders = { ...providers };
                          newProviders[name] = { ...p, enabled: e.target.checked };
                          setField("providers", newProviders);
                        }}
                        className="size-3 accent-stone-400" />
                      Bật
                    </label>
                  </div>
                  <p className="text-[11px] text-stone-500">{meta.desc}</p>
                  {meta.type === "info" ? (
                    <p className="text-[10px] text-emerald-600">Miễn phí, không cần cấu hình gì thêm</p>
                  ) : meta.type === "cloudflare" ? (
                    <>
                      <Input value={p.account_id || ""}
                        onChange={(e) => {
                          const np = { ...providers };
                          np[name] = { ...p, account_id: e.target.value };
                          setField("providers", np);
                        }}
                        placeholder="Account ID" className="h-8 rounded-lg border-stone-200 text-xs" />
                      <Input value={p.api_token || ""}
                        onChange={(e) => {
                          const np = { ...providers };
                          np[name] = { ...p, api_token: e.target.value };
                          setField("providers", np);
                        }}
                        placeholder="API Token" className="h-8 rounded-lg border-stone-200 text-xs" />
                    </>
                  ) : meta.type === "textarea" ? (
                    <div className="space-y-1">
                      <textarea value={meta.state}
                        onChange={(e) => meta.setState(e.target.value)}
                        placeholder="Mỗi dòng 1 API key"
                        className="w-full h-16 rounded-lg border border-stone-200 text-xs p-2 resize-y" />
                      <div className="flex justify-between items-center">
                        <p className="text-[10px] text-stone-500">Nhiều key → tự chuyển khi hết quota</p>
                        <button type="button" onClick={() => meta.setState("")}
                          className="text-[10px] text-red-500 hover:text-red-700">Xóa</button>
                      </div>
                    </div>
                  ) : (
                    <Input value={p[meta.key] || ""}
                      onChange={(e) => {
                        const np = { ...providers };
                        np[name] = { ...p, [meta.key]: e.target.value };
                        setField("providers", np);
                      }}
                      placeholder={meta.placeholder || "API key"}
                      className="h-8 rounded-lg border-stone-200 text-xs" />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Backends ── */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Sliders className="size-5 text-stone-700" />
            <h3 className="text-sm font-semibold text-stone-900">Backend mặc định</h3>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <div className="space-y-1">
              <label className="text-xs text-stone-500">Default Chat Model</label>
              <Input value={backends.default_chat || "auto"}
                onChange={(e) => setField("backends", { ...backends, default_chat: e.target.value })}
                className="h-9 rounded-lg border-stone-200 text-sm" />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-stone-500">Default Image Size</label>
              <select value={backends.default_image || "1792x1024"}
                onChange={(e) => setField("backends", { ...backends, default_image: e.target.value })}
                className="w-full h-9 rounded-lg border-stone-200 text-sm bg-white">
                <option value="1024x1024">1024x1024 (1:1)</option>
                <option value="1792x1024">1792x1024 (16:9)</option>
                <option value="1024x1792">1024x1792 (9:16)</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs text-stone-500">9router URL</label>
              <Input value={ninerouter.base_url || "http://localhost:20128"}
                onChange={(e) => setField("ninerouter", { ...ninerouter, base_url: e.target.value })}
                className="h-9 rounded-lg border-stone-200 text-sm" />
            </div>
          </div>
        </div>

        {/* ── Rate Limit ── */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Sliders className="size-5 text-stone-700" />
            <h3 className="text-sm font-semibold text-stone-900">Rate Limit Backoff</h3>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            {[
              ["Base (ms)", "backoff_base_ms", 2000],
              ["Max (ms)", "backoff_max_ms", 300000],
              ["Max Levels", "max_levels", 15],
            ].map(([label, key, def]) => (
              <div key={key} className="space-y-1">
                <label className="text-xs text-stone-500">{label}</label>
                <Input value={(rateLimit as any)[key] || def}
                  onChange={(e) => setField("rate_limit", { ...rateLimit, [key]: parseInt(e.target.value) || def })}
                  className="h-9 rounded-lg border-stone-200 text-sm" />
              </div>
            ))}
          </div>
        </div>

        {/* ── Combo ── */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Combine className="size-5 text-stone-700" />
            <h3 className="text-sm font-semibold text-stone-900">Combo Models</h3>
          </div>
          <Textarea value={comboText}
            onChange={(e) => {
              setComboText(e.target.value);
              const combos: any = {};
              e.target.value.split("\n").filter(Boolean).forEach((line) => {
                const [name, models] = line.split("=");
                if (name && models) combos[name.trim()] = models.split(",").map((m: string) => m.trim()).filter(Boolean);
              });
              setField("combo_models", combos);
            }}
            placeholder="ha-agent=oc/auto,cx/auto,chatgpt/auto"
            className="min-h-24 rounded-xl border-stone-200 bg-white font-mono text-xs" />
          <p className="text-xs text-stone-500 mt-1">Mỗi dòng: tên=model1,model2. Thứ tự = thứ tự fallback.</p>
        </div>

        <div className="flex justify-end">
          <Button className="h-10 rounded-xl bg-stone-900 px-5 text-white hover:bg-stone-800"
            onClick={() => {
              // Sync textarea values before save
              updateProviderConfig("gemini_free", geminiKeys);
              updateProviderConfig("serper", serperKeys);
              void saveConfig();
            }}
            disabled={isSavingConfig}>
            {isSavingConfig ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
            Lưu tất cả
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
