"use client";

import { useEffect, useRef, useState } from "react";
import { LoaderCircle, Sparkles, ExternalLink, X, Save } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { request } from "@/lib/request";

type OnboardState = {
  profile: string;
  state: "none" | "starting" | "running" | "need_tap" | "need_code" | "success" | "failed";
  message: string;
  elapsed_sec?: number;
  error?: string | null;
};

type CSCfg = { url: string; apiKey: string };

export function GeminiWebCard() {
  const [cs, setCs] = useState<CSCfg>({
    url: "http://172.16.10.38:8010",
    apiKey: "AnhNhi@0610",
  });
  const [profile, setProfile] = useState("gemini-web-default");
  const [timeout, setTimeoutVal] = useState(120);
  const [draft, setDraft] = useState({ email: "", password: "" });
  const [running, setRunning] = useState(false);
  const [session, setSession] = useState<OnboardState | null>(null);
  const [savingCfg, setSavingCfg] = useState(false);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    void fetchCfg();
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, []);

  async function fetchCfg() {
    try {
      const data = await request.get("/api/settings");
      const cfg = (data.data as any)?.config?.providers || {};
      const flow = cfg.flow || {};
      const gemw = cfg.gemini_web || {};
      setCs({
        url: flow.captcha_solver_url || "http://172.16.10.38:8010",
        apiKey: flow.captcha_solver_api_key || "AnhNhi@0610",
      });
      setProfile(gemw.profile || "gemini-web-default");
      setTimeoutVal(Number(gemw.timeout) || 120);
    } catch (e) {
      console.error(e);
    }
  }

  async function saveProviderCfg() {
    setSavingCfg(true);
    try {
      const cur = await request.get("/api/settings");
      const config = (cur.data as any)?.config || {};
      config.providers = config.providers || {};
      config.providers.gemini_web = {
        ...(config.providers.gemini_web || {}),
        profile: profile.trim() || "gemini-web-default",
        timeout: Math.max(30, Math.min(600, timeout)),
      };
      await request.put("/api/settings", { config });
      toast.success("Đã lưu config Gemini Web");
    } catch (e: any) {
      toast.error(`Save fail: ${e?.message || e}`);
    } finally {
      setSavingCfg(false);
    }
  }

  function stopPolling() {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function pollStatus() {
    try {
      const res = await fetch(
        `${cs.url}/v1/gemini-web/${encodeURIComponent(profile)}/onboard-status`,
        { headers: { Authorization: `Bearer ${cs.apiKey}` } },
      );
      if (!res.ok) return;
      const data: OnboardState = await res.json();
      setSession(data);
      if (data.state === "success" || data.state === "failed") {
        stopPolling();
        setRunning(false);
        if (data.state === "success") toast.success(`Gemini Web profile sẵn sàng ✓`);
        else toast.error(`Onboard fail: ${data.error || data.message}`);
      }
    } catch {
      /* ignore */
    }
  }

  async function onboard() {
    if (!draft.email.trim() || !draft.password) {
      toast.error("Cần email + mật khẩu Google");
      return;
    }
    stopPolling();
    setRunning(true);
    setSession(null);
    try {
      const res = await fetch(`${cs.url}/v1/gemini-web/onboard`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${cs.apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          profile, email: draft.email.trim(), password: draft.password,
        }),
      });
      if (!res.ok) throw new Error(`onboard HTTP ${res.status}`);
      const initial = await res.json();
      setSession(initial);
      const noVncUrl = cs.url.replace(":8010", ":6080") + "/vnc.html?autoconnect=1";
      window.open(noVncUrl, "_blank", "noopener,width=1024,height=720");
      pollRef.current = window.setInterval(() => void pollStatus(), 1500);
    } catch (e: any) {
      toast.error(`Onboard error: ${e?.message}`);
      setRunning(false);
    }
  }

  function openNoVNC() {
    window.open(cs.url.replace(":8010", ":6080") + "/vnc.html?autoconnect=1", "_blank");
  }

  function cancelSession() {
    stopPolling();
    setSession(null);
    setRunning(false);
  }

  return (
    <Card className="rounded-3xl border-violet-100/80 bg-violet-50/30">
      <CardContent className="space-y-4 p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Sparkles className="size-4 text-violet-600" />
              <h3 className="text-sm font-semibold text-violet-900">Gemini Web (gemini.google.com)</h3>
            </div>
            <p className="text-xs text-violet-700/70 mt-0.5">
              DOM scrape gemini.google.com (chat / image / vision). Bypass VN geo-block của Gemini API.
              Endpoint OpenAI-compat: <code className="font-mono text-[10px]">model=gmw/chat</code>,{" "}
              <code className="font-mono text-[10px]">gmw/image</code>,{" "}
              <code className="font-mono text-[10px]">gmw/vision</code>.
            </p>
          </div>
        </div>

        <div className="space-y-2 rounded-xl border border-violet-200 bg-white/80 p-3">
          <p className="text-xs font-bold text-violet-800">Cấu hình provider</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <label className="text-[11px] text-stone-500">Profile (captcha-solver user-data-dir)</label>
              <Input
                value={profile} onChange={(e) => setProfile(e.target.value)}
                placeholder="gemini-web-default"
                className="mt-1 h-8 rounded-lg border-violet-200 text-xs font-mono"
              />
            </div>
            <div>
              <label className="text-[11px] text-stone-500">Timeout (giây)</label>
              <Input
                type="number" min={30} max={600}
                value={timeout}
                onChange={(e) => setTimeoutVal(Number(e.target.value))}
                className="mt-1 h-8 rounded-lg border-violet-200 text-xs font-mono"
              />
            </div>
          </div>
          <Button
            className="h-8 rounded-lg bg-violet-600 px-3 text-xs text-white hover:bg-violet-700"
            onClick={saveProviderCfg} disabled={savingCfg}
          >
            {savingCfg ? <LoaderCircle className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
            {" "}Lưu config
          </Button>
        </div>

        <div className="space-y-2 rounded-xl border-2 border-violet-300 bg-gradient-to-br from-violet-50/60 to-fuchsia-50/60 p-3">
          <p className="text-xs font-bold text-violet-800">1-click onboard (Google OAuth)</p>
          <p className="text-[10px] text-violet-700/70 leading-relaxed">
            Nếu profile đã login Google (qua Flow/ChatGPT onboard), short-circuit success ngay.
            Nếu chưa, mở Playwright + login chuẩn — theo dõi qua noVNC khi cần thao tác manual.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <label className="text-[11px] text-stone-500">Email Google</label>
              <Input
                value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })}
                placeholder="you@gmail.com"
                className="mt-1 h-8 rounded-lg border-violet-200 text-xs font-mono"
                autoComplete="off" disabled={running}
              />
            </div>
            <div>
              <label className="text-[11px] text-stone-500">Mật khẩu Google</label>
              <Input
                type="password" value={draft.password}
                onChange={(e) => setDraft({ ...draft, password: e.target.value })}
                placeholder="••••••••"
                className="mt-1 h-8 rounded-lg border-violet-200 text-xs font-mono"
                autoComplete="off" disabled={running}
              />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button
              className="h-9 rounded-lg bg-gradient-to-r from-violet-600 to-fuchsia-600 px-3 text-xs font-bold text-white hover:from-violet-700 hover:to-fuchsia-700 shadow-lg shadow-violet-200"
              onClick={onboard} disabled={running}
            >
              {running ? <><LoaderCircle className="size-3.5 animate-spin" /> Đang chạy…</>
                : <><Sparkles className="size-3.5" /> Onboard</>}
            </Button>
            <Button
              className="h-9 rounded-lg border border-violet-200 bg-white px-3 text-xs text-violet-700 hover:bg-violet-50"
              onClick={openNoVNC}
            >
              <ExternalLink className="size-3.5" /> Mở noVNC
            </Button>
            {session && session.state !== "none" && (
              <Button
                className="h-9 rounded-lg border border-stone-200 bg-white px-3 text-xs text-stone-600 hover:bg-stone-50"
                onClick={cancelSession}
              >
                <X className="size-3.5" /> Đóng
              </Button>
            )}
          </div>

          {session && session.state !== "none" && (
            <div className={`mt-2 rounded-lg border p-2 text-xs space-y-1 ${
              session.state === "success" ? "border-emerald-300 bg-emerald-50/70"
              : session.state === "failed" ? "border-rose-300 bg-rose-50/70"
              : "border-violet-200 bg-white/80"
            }`}>
              <div className="flex items-center gap-2">
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${
                  session.state === "success" ? "bg-emerald-100 text-emerald-700"
                  : session.state === "failed" ? "bg-rose-100 text-rose-700"
                  : "bg-violet-100 text-violet-700"
                }`}>
                  {(session.state === "running" || session.state === "starting") && (
                    <LoaderCircle className="size-3 animate-spin" />
                  )}
                  {session.state}
                </span>
                <span className="text-stone-600">{session.message}</span>
                {typeof session.elapsed_sec === "number" && (
                  <span className="ml-auto text-[10px] text-stone-400 font-mono">{session.elapsed_sec}s</span>
                )}
              </div>
              {session.state === "failed" && session.error && (
                <p className="text-rose-700 text-[11px]">{session.error}</p>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
