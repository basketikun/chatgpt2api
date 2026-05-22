"use client";

import { useEffect, useState } from "react";
import { LoaderCircle, Save, Cpu } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { request } from "@/lib/request";

export function NvidiaNimCard() {
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => { fetchConfig(); }, []);

  async function fetchConfig() {
    try {
      const data = await request.get("/api/settings");
      const cfg = (data.data as any)?.config || {};
      const p = (cfg.providers || {}).nvidia_nim || {};
      const keys = [p.api_key || "", ...(p.api_keys || [])].filter(Boolean);
      setApiKey([...new Set(keys)].join("\n"));
      setEnabled(p.enabled !== false);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }

  async function save() {
    setSaving(true);
    try {
      const keyList = apiKey.split("\n").map(k => k.trim()).filter(Boolean);
      // Fetch current providers to merge with
      const cfg = await request.get("/api/settings");
      const config = (cfg.data as any)?.config || {};
      const providers = { ...(config.providers || {}) };
      providers.nvidia_nim = {
        enabled: enabled,
        api_key: keyList[0] || "",
        api_keys: keyList,
      };
      // Only send providers — avoid overwriting other settings
      await request.post("/api/settings", { providers });
      toast.success("Đã lưu NVIDIA NIM!");
    } catch (e: any) { toast.error(e?.message || "Lỗi lưu"); }
    finally { setSaving(false); }
  }

  if (loading) return <Card className="rounded-2xl card-3d card-tint-emerald"><CardContent className="flex justify-center p-10"><LoaderCircle className="size-5 animate-spin text-stone-500" /></CardContent></Card>;

  return (
    <Card className="rounded-2xl card-3d card-tint-emerald">
      <CardContent className="space-y-4 p-6">
        <div className="flex items-center gap-2">
          <span className="inline-flex size-5 items-center justify-center rounded text-xs font-bold" style={{backgroundColor: "#76B900", color: "#000"}}>N</span>
          <h3 className="text-sm font-semibold text-stone-900">NVIDIA NIM</h3>
          <span className="text-[10px] text-stone-500">build.nvidia.com</span>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} className="size-4 accent-stone-400" />
          Bật NVIDIA NIM
        </label>

        <div className="space-y-2">
          <label className="text-sm text-stone-700">API Keys (mỗi dòng 1 key)</label>
          <Textarea value={apiKey} onChange={(e) => setApiKey(e.target.value)}
            placeholder={"nvapi-xxx...\nnvapi-yyy..."}
            className="min-h-24 rounded-xl border-stone-200 bg-stone-100 font-mono text-xs" />
          <p className="text-xs text-stone-500">Nhiều key → tự động round-robin khi rate limit. Lấy tại build.nvidia.com</p>
        </div>

        <div className="p-3 rounded-lg bg-stone-100 text-xs text-stone-500 space-y-1">
          <p><strong>Chat:</strong> Dùng prefix <code className="bg-stone-200 px-1 rounded">nv/</code> — ví dụ: <code className="bg-stone-200 px-1 rounded">nv/openai/gpt-oss-120b</code></p>
          <p><strong>Tạo ảnh:</strong> Dùng prefix <code className="bg-stone-200 px-1 rounded">nv-image/</code> — ví dụ: <code className="bg-stone-200 px-1 rounded">nv-image/black-forest-labs/flux.2-klein-4b</code></p>
          <p><strong>Vision:</strong> Dùng model vision qua <code className="bg-stone-200 px-1 rounded">nv/google/gemma-4-31b-it</code></p>
        </div>

        <div className="flex justify-end">
          <Button className="h-10 rounded-xl bg-stone-900 px-5 text-white hover:bg-stone-800"
            onClick={() => void save()} disabled={saving}>
            {saving ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
            Lưu
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
