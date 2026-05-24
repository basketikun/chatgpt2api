"use client";

import { useEffect, useState } from "react";
import { LoaderCircle, MessageSquare, Save } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { request } from "@/lib/request";

export function ChatGPTWebCard() {
  const [profile, setProfile] = useState("chatgpt-default");
  const [timeout, setTimeoutVal] = useState(120);
  const [savingCfg, setSavingCfg] = useState(false);

  useEffect(() => {
    void fetchCfg();
  }, []);

  async function fetchCfg() {
    try {
      const data = await request.get("/api/settings");
      const cfg = (data.data as any)?.config?.providers || {};
      const cgw = cfg.chatgpt_web || {};
      setProfile(cgw.profile || "chatgpt-default");
      setTimeoutVal(Number(cgw.timeout) || 120);
    } catch (e) {
      console.error(e);
    }
  }

  async function saveProviderCfg() {
    setSavingCfg(true);
    try {
      const cur = await request.get("/api/settings");
      const config = (cur.data as any)?.config ||{};
      config.providers = config.providers || {};
      config.providers.chatgpt_web = {
        ...(config.providers.chatgpt_web || {}),
        profile: profile.trim() || "chatgpt-default",
        timeout: Math.max(30, Math.min(600, timeout)),
      };
      await request.put("/api/settings", { config });
      toast.success("Đã lưu config ChatGPT Web");
    } catch (e: any) {
      toast.error(`Save fail: ${e?.message || e}`);
    } finally {
      setSavingCfg(false);
    }
  }

  return (
    <Card className="rounded-3xl border-emerald-100/80 bg-emerald-50/30">
      <CardContent className="space-y-4 p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <MessageSquare className="size-4 text-emerald-600" />
              <h3 className="text-sm font-semibold text-emerald-900">ChatGPT Web (chatgpt.com)</h3>
            </div>
            <p className="text-xs text-emerald-700/70 mt-0.5">
              DOM scrape chatgpt.com qua profile đã login (dùng card "ChatGPT via Google OAuth" để
              setup profile). Endpoint OpenAI-compat:{" "}
              <code className="font-mono text-[10px]">model=cgw/chat</code>,{" "}
              <code className="font-mono text-[10px]">cgw/image</code>,{" "}
              <code className="font-mono text-[10px]">cgw/vision</code>.
            </p>
          </div>
        </div>

        <div className="space-y-2 rounded-xl border border-emerald-200 bg-white/80 p-3">
          <p className="text-xs font-bold text-emerald-800">Cấu hình provider</p>
          <p className="text-[10px] text-emerald-700/70 leading-relaxed">
            Profile = tên user-data-dir trong captcha-solver (cùng tên với card OAuth ở trên).
            Nếu để mặc định <code className="font-mono">chatgpt-default</code> thì đặt tên profile
            tương ứng khi onboard.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <label className="text-[11px] text-stone-500">Profile (captcha-solver user-data-dir)</label>
              <Input
                value={profile}
                onChange={(e) => setProfile(e.target.value)}
                placeholder="chatgpt-default"
                className="mt-1 h-8 rounded-lg border-emerald-200 text-xs font-mono"
              />
            </div>
            <div>
              <label className="text-[11px] text-stone-500">Timeout (giây)</label>
              <Input
                type="number" min={30} max={600}
                value={timeout}
                onChange={(e) => setTimeoutVal(Number(e.target.value))}
                className="mt-1 h-8 rounded-lg border-emerald-200 text-xs font-mono"
              />
            </div>
          </div>
          <div className="flex items-center justify-between pt-1">
            <p className="text-[10px] text-stone-500">
              Vision tự nhận diện qua multimodal block <code className="font-mono">image_url</code>{" "}
              trong <code className="font-mono">/v1/chat/completions</code>.
            </p>
            <Button
              className="h-8 rounded-lg bg-emerald-600 px-3 text-xs text-white hover:bg-emerald-700"
              onClick={saveProviderCfg} disabled={savingCfg}
            >
              {savingCfg ? <LoaderCircle className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
              {" "}Lưu config
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
