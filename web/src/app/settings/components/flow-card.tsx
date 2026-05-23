"use client";

import { useEffect, useState } from "react";
import { LoaderCircle, Plus, Save, Trash2, ExternalLink, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { request } from "@/lib/request";

type FlowAccount = {
  profile: string;
  project_id: string;
  label?: string;
};

type FlowConfig = {
  enabled: boolean;
  captcha_solver_url: string;
  captcha_solver_api_key: string;
  accounts: FlowAccount[];
};

const EMPTY_ACCOUNT: FlowAccount = { profile: "google-fx", project_id: "", label: "Main" };

export function FlowCard() {
  const [cfg, setCfg] = useState<FlowConfig>({
    enabled: true,
    captcha_solver_url: "http://172.16.10.38:8010",
    captcha_solver_api_key: "AnhNhi@0610",
    accounts: [],
  });
  const [draft, setDraft] = useState<FlowAccount>({ ...EMPTY_ACCOUNT });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => { fetchCfg(); }, []);

  async function fetchCfg() {
    setLoading(true);
    try {
      const data = await request.get("/api/settings");
      const flow = ((data.data as any)?.config?.providers || {}).flow || {};
      setCfg({
        enabled: flow.enabled !== false,
        captcha_solver_url: flow.captcha_solver_url || "http://172.16.10.38:8010",
        captcha_solver_api_key: flow.captcha_solver_api_key || "",
        accounts: Array.isArray(flow.accounts) ? flow.accounts : [],
      });
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }

  async function save(next: FlowConfig) {
    setSaving(true);
    try {
      await request.post("/api/settings", {
        config: { providers: { flow: next } },
      });
      toast.success("Đã lưu cấu hình Flow");
      setCfg(next);
    } catch (e: any) {
      toast.error(e?.message || "Lỗi lưu");
    } finally { setSaving(false); }
  }

  function addAccount() {
    if (!draft.profile.trim() || !draft.project_id.trim()) {
      toast.error("Profile + project_id là bắt buộc");
      return;
    }
    const next = { ...cfg, accounts: [...cfg.accounts, { ...draft, label: draft.label?.trim() || draft.profile }] };
    void save(next);
    setDraft({ ...EMPTY_ACCOUNT });
  }

  function removeAccount(idx: number) {
    const next = { ...cfg, accounts: cfg.accounts.filter((_, i) => i !== idx) };
    void save(next);
  }

  function openNoVNC() {
    if (!cfg.captcha_solver_url) {
      toast.error("Cần điền captcha_solver_url trước");
      return;
    }
    const novncUrl = cfg.captcha_solver_url.replace(":8010", ":6080") + "/vnc.html?autoconnect=1";
    window.open(novncUrl, "_blank");
  }

  async function triggerManualLogin() {
    if (!draft.profile.trim()) {
      toast.error("Cần điền profile trước");
      return;
    }
    try {
      await fetch(`${cfg.captcha_solver_url}/v1/session/manual-login`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${cfg.captcha_solver_api_key}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          profile: draft.profile.trim(),
          url: "https://labs.google/fx/vi/tools/flow",
        }),
      });
      toast.success("Đã mở browser session — mở noVNC để login Google");
      openNoVNC();
    } catch (e: any) {
      toast.error(`Lỗi gọi manual-login: ${e?.message}`);
    }
  }

  return (
    <Card className="rounded-3xl border-emerald-100/80 bg-emerald-50/30">
      <CardContent className="space-y-4 p-5">
        {/* Header + global enable */}
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Sparkles className="size-4 text-emerald-600" />
              <h3 className="text-sm font-semibold text-emerald-900">Google Labs Flow</h3>
            </div>
            <p className="text-xs text-emerald-700/70 mt-0.5">
              Sinh ảnh qua labs.google/fx (Nano Banana Pro / 2 / Imagen 4) — chạy qua captcha-solver browser pool
            </p>
          </div>
          <label className="flex items-center gap-2 text-xs text-stone-600">
            <input
              type="checkbox"
              checked={cfg.enabled}
              onChange={(e) => void save({ ...cfg, enabled: e.target.checked })}
              className="size-4 rounded"
            />
            Enabled
          </label>
        </div>

        {/* Captcha-solver connection */}
        <div className="grid gap-3 sm:grid-cols-2 rounded-xl border border-emerald-200/60 bg-white/60 p-3">
          <div>
            <label className="text-xs text-emerald-800">Captcha-solver URL</label>
            <Input
              value={cfg.captcha_solver_url}
              onChange={(e) => setCfg({ ...cfg, captcha_solver_url: e.target.value })}
              onBlur={() => void save(cfg)}
              placeholder="http://172.16.10.38:8010"
              className="mt-1 h-9 rounded-lg border-emerald-200 text-sm font-mono"
            />
          </div>
          <div>
            <label className="text-xs text-emerald-800">Captcha-solver API Key</label>
            <Input
              type="password"
              value={cfg.captcha_solver_api_key}
              onChange={(e) => setCfg({ ...cfg, captcha_solver_api_key: e.target.value })}
              onBlur={() => void save(cfg)}
              placeholder="bearer key"
              className="mt-1 h-9 rounded-lg border-emerald-200 text-sm font-mono"
            />
          </div>
        </div>

        {/* Existing accounts list */}
        {cfg.accounts.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs font-semibold uppercase tracking-wider text-emerald-700/80">
              Tài khoản hiện có ({cfg.accounts.length}) — #1 luôn được dùng trước
            </p>
            {cfg.accounts.map((a, i) => (
              <div key={`${a.profile}:${a.project_id}`} className="flex items-center gap-2 rounded-lg border border-emerald-200/60 bg-white/60 px-3 py-2">
                <span className={`shrink-0 inline-flex items-center justify-center min-w-[28px] h-5 px-1.5 rounded-md text-[11px] font-mono font-bold tabular-nums ${
                  i === 0 ? "bg-emerald-100 text-emerald-700 ring-1 ring-emerald-300" : "bg-slate-100 text-slate-500"
                }`}>
                  #{i + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-stone-800">{a.label || a.profile}</div>
                  <div className="flex items-center gap-2 text-[11px] text-stone-500 font-mono">
                    <span>profile: {a.profile}</span>
                    <span>·</span>
                    <span className="truncate">project: {a.project_id}</span>
                  </div>
                </div>
                <Button
                  className="h-7 w-7 rounded-md bg-rose-50 text-rose-500 hover:bg-rose-100 p-0"
                  onClick={() => removeAccount(i)}
                  disabled={saving}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}

        {/* Add new account */}
        <div className="space-y-2 rounded-xl border border-dashed border-emerald-300 bg-white/40 p-3">
          <p className="text-xs font-semibold text-emerald-800">+ Thêm tài khoản mới</p>
          <div className="grid gap-2 sm:grid-cols-3">
            <div>
              <label className="text-[11px] text-stone-500">Label (chọn hoặc gõ)</label>
              <Input
                value={draft.label || ""}
                onChange={(e) => setDraft({ ...draft, label: e.target.value })}
                placeholder="VD: Main / Work / Backup"
                className="mt-1 h-8 rounded-lg border-stone-200 text-xs"
                list="flow-label-presets"
                autoComplete="off"
              />
              {/* Native HTML5 datalist — gõ thoải mái, dropdown gợi ý 6 preset
                  phổ biến + bất kỳ label nào đã dùng trước đó để khỏi đặt
                  trùng. */}
              <datalist id="flow-label-presets">
                <option value="Main" />
                <option value="Backup" />
                <option value="Work" />
                <option value="Personal" />
                <option value="Family" />
                <option value="Team" />
                {cfg.accounts
                  .map((a) => a.label || "")
                  .filter((v, i, arr) => v && arr.indexOf(v) === i)
                  .map((v) => (
                    <option key={`used-${v}`} value={v} />
                  ))}
              </datalist>
            </div>
            <div>
              <label className="text-[11px] text-stone-500">Profile (browser context)</label>
              <Input
                value={draft.profile}
                onChange={(e) => setDraft({ ...draft, profile: e.target.value })}
                placeholder="google-fx"
                className="mt-1 h-8 rounded-lg border-stone-200 text-xs font-mono"
              />
            </div>
            <div>
              <label className="text-[11px] text-stone-500">Project ID (Flow URL)</label>
              <Input
                value={draft.project_id}
                onChange={(e) => setDraft({ ...draft, project_id: e.target.value })}
                placeholder="54468d77-02ff-4a06-..."
                className="mt-1 h-8 rounded-lg border-stone-200 text-xs font-mono"
              />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button
              className="h-8 rounded-lg bg-emerald-600 px-3 text-xs text-white hover:bg-emerald-700"
              onClick={addAccount}
              disabled={saving}
            >
              {saving ? <LoaderCircle className="size-3.5 animate-spin" /> : <Plus className="size-3.5" />}
              Thêm vào pool
            </Button>
            <Button
              className="h-8 rounded-lg border border-emerald-200 bg-white px-3 text-xs text-emerald-700 hover:bg-emerald-50"
              onClick={triggerManualLogin}
            >
              <ExternalLink className="size-3.5" /> Mở noVNC + bắt đầu login Google
            </Button>
          </div>
          <p className="text-[10px] text-stone-500 leading-relaxed">
            <b>Cách lấy project_id:</b> sau khi login Google trong noVNC, truy cập{" "}
            <code className="text-emerald-700">labs.google/fx/vi/tools/flow</code> → tạo project mới → copy UUID từ URL{" "}
            <code className="text-emerald-700">.../project/&lt;UUID&gt;</code>.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
