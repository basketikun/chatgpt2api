"use client";

import { useEffect, useState } from "react";
import { LoaderCircle, Save, Cpu } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { request } from "@/lib/request";

export function GeminiCard() {
  const [geminiKey, setGeminiKey] = useState("");
  const [geminiModel, setGeminiModel] = useState("gemini-2.5-flash");
  const [geminiEnabled, setGeminiEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => { fetchConfig(); }, []);

  async function fetchConfig() {
    try {
      const data = await request.get("/api/settings");
      const cfg = (data.data as any)?.config || {};
      const p = (cfg.providers || {}).gemini_free || {};
      const keys = [p.api_key || "", ...(p.api_keys || [])].filter(Boolean);
      setGeminiKey([...new Set(keys)].join("\n"));
      setGeminiModel(p.model || "gemini-2.5-flash");
      setGeminiEnabled(p.enabled !== false);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }

  async function save() {
    setSaving(true);
    try {
      const keyList = geminiKey.split("\n").map(k => k.trim()).filter(Boolean);
      const cfg = await request.get("/api/settings");
      const config = (cfg.data as any)?.config || {};
      const providers = { ...(config.providers || {}) };
      providers.gemini_free = {
        enabled: geminiEnabled,
        api_key: keyList[0] || "",
        api_keys: keyList,
        model: geminiModel,
      };
      await request.post("/api/settings", { providers });
      toast.success("Đã lưu!");
    } catch (e: any) { toast.error(e?.message || "Lỗi lưu"); }
    finally { setSaving(false); }
  }

  if (loading) return <Card className="rounded-2xl card-3d card-tint-violet"><CardContent className="flex justify-center p-10"><LoaderCircle className="size-5 animate-spin text-stone-500" /></CardContent></Card>;

  return (
    <Card className="rounded-2xl card-3d card-tint-violet">
      <CardContent className="space-y-4 p-6">
        <div className="flex items-center gap-2"><Cpu className="size-5 text-stone-700" /><h3 className="text-sm font-semibold text-stone-900">Gemini AI Studio</h3></div>

        <label className="flex items-center gap-2 text-sm text-stone-700"><input type="checkbox" checked={geminiEnabled} onChange={(e) => setGeminiEnabled(e.target.checked)} className="size-4 accent-stone-400" /> Bật Gemini</label>

        <div className="space-y-2">
          <label className="text-sm text-stone-700">API Keys (mỗi dòng 1 key)</label>
          <Textarea value={geminiKey} onChange={(e) => setGeminiKey(e.target.value)}
            placeholder={"AIzaSyKey1...\nAIzaSyKey2..."}
            className="min-h-24 rounded-xl border-stone-200 bg-stone-100 text-stone-900 font-mono text-xs placeholder:text-stone-500" />
          <p className="text-xs text-stone-500">Nhiều key → tự động round-robin khi hết quota. Lấy tại aistudio.google.com/apikey</p>
        </div>

        <div className="flex items-center gap-3">
          <label className="text-sm text-stone-700">Model:</label>
          <select value={geminiModel} onChange={(e) => setGeminiModel(e.target.value)}
            className="rounded-lg border border-stone-200 bg-stone-100 px-2 py-1.5 text-sm text-stone-900">
            <option value="gemini-3-flash-preview">gemini-3-flash-preview (Preview - mới nhất)</option>
            <option value="gemini-2.5-flash">gemini-2.5-flash (Stable)</option>
            <option value="gemini-2.5-pro-preview-07-02">gemini-2.5-pro-preview-07-02 (Preview)</option>
            <option value="gemini-2.5-pro-preview-06-26">gemini-2.5-pro-preview-06-26 (Preview)</option>
            <option value="gemini-2.5-flash-lite-preview-06-26">gemini-2.5-flash-lite-preview-06-26 (Preview)</option>
            <option value="gemini-2.0-flash">gemini-2.0-flash (Stable)</option>
            <option value="gemini-2.0-flash-lite">gemini-2.0-flash-lite (Stable)</option>
          </select>
        </div>

        <div className="flex justify-end">
          <Button className="h-10 rounded-xl bg-stone-100 px-5 text-stone-900 hover:bg-white"
            onClick={() => void save()} disabled={saving}>
            {saving ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
            Lưu
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
