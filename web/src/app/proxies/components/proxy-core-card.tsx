"use client";

import { useState } from "react";
import { ChevronDown, Copy, Cpu, LoaderCircle, RefreshCw, RotateCcw, Save } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import type { ProxyCoreStatus, ProxyCoreUpdate } from "@/lib/api";
import { cn } from "@/lib/utils";

const COMPOSE_COMMAND = "docker compose --profile proxy-core up -d";
const CORE_DEFAULTS = { api_url: "http://proxy-core:9090", listen_host: "proxy-core", port_start: 20000 };
const PORT_MIN = 1024;
const PORT_MAX = 64000;

type Draft = Partial<{ enabled: boolean; api_url: string; secret: string; listen_host: string; port_start: string }>;

type ProxyCoreCardProps = {
  core: ProxyCoreStatus | null;
  isSaving: boolean;
  onSave: (updates: ProxyCoreUpdate) => Promise<boolean>;
};

function CoreStatusBadge({ core }: { core: ProxyCoreStatus | null }) {
  if (!core) {
    return null;
  }
  if (!core.settings.enabled) {
    return <Badge variant="secondary">未启用</Badge>;
  }
  return core.status.ok ? (
    <Badge variant="success">连接正常{core.status.version ? ` · ${core.status.version}` : ""}</Badge>
  ) : (
    <Badge variant="danger">无法连接</Badge>
  );
}

/** 可选的 mihomo 内核：只有 ss / vmess / trojan 等节点需要；默认折叠，启用后连接异常时自动展开 */
export function ProxyCoreCard({ core, isSaving, onSave }: ProxyCoreCardProps) {
  const [open, setOpen] = useState<boolean | null>(null);
  // 只有改过的字段才放进草稿；轮询刷新不会覆盖正在编辑的输入
  const [draft, setDraft] = useState<Draft>({});

  const settings = core?.settings ?? null;
  const status = core?.status ?? null;
  const isOpen = open ?? Boolean(settings?.enabled && status && !status.ok);

  const enabled = draft.enabled ?? settings?.enabled ?? false;
  const valueOf = (key: "api_url" | "listen_host" | "port_start") => draft[key] ?? (settings ? String(settings[key]) : "");
  const isDirty =
    settings !== null &&
    ((draft.enabled !== undefined && draft.enabled !== settings.enabled) ||
      Boolean(draft.secret?.trim()) ||
      (["api_url", "listen_host", "port_start"] as const).some((key) => key in draft && draft[key] !== String(settings[key])));

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(COMPOSE_COMMAND);
      toast.success("已复制到剪贴板");
    } catch {
      toast.error("复制失败，请手动复制");
    }
  };

  const handleSave = async () => {
    if (!settings) {
      return;
    }
    const updates: ProxyCoreUpdate = {};
    if (draft.enabled !== undefined && draft.enabled !== settings.enabled) {
      updates.enabled = draft.enabled;
    }
    if (draft.api_url !== undefined) {
      const apiUrl = draft.api_url.trim().replace(/\/+$/, "");
      if (!/^https?:\/\/\S+$/i.test(apiUrl)) {
        toast.error("控制接口需要是 http(s) 地址，例如 " + CORE_DEFAULTS.api_url);
        return;
      }
      if (apiUrl !== settings.api_url) updates.api_url = apiUrl;
    }
    if (draft.listen_host !== undefined) {
      const host = draft.listen_host.trim();
      if (!host || /[\s/]/.test(host)) {
        toast.error("监听主机需要是主机名或 IP，例如 " + CORE_DEFAULTS.listen_host);
        return;
      }
      if (host !== settings.listen_host) updates.listen_host = host;
    }
    if (draft.port_start !== undefined) {
      const raw = draft.port_start.trim();
      const port = Number(raw);
      if (!raw || !Number.isInteger(port) || port < PORT_MIN || port > PORT_MAX) {
        toast.error(`起始端口需要是 ${PORT_MIN}–${PORT_MAX} 之间的整数`);
        return;
      }
      if (port !== settings.port_start) updates.port_start = port;
    }
    // 密钥只写不读：只有输入了内容才提交
    if (draft.secret?.trim()) {
      updates.secret = draft.secret.trim();
    }
    if (Object.keys(updates).length === 0) {
      setDraft({});
      return;
    }
    const ok = await onSave(updates);
    if (ok) {
      setDraft({});
    }
  };

  const lastApply = status?.last_apply;

  return (
    <Card className="min-w-0 overflow-hidden">
      <button
        type="button"
        className="flex w-full items-start justify-between gap-4 p-5 text-left outline-none transition-colors hover:bg-accent/40 focus-visible:ring-4 focus-visible:ring-ring/30 focus-visible:ring-inset"
        aria-expanded={isOpen}
        aria-controls="proxy-core-settings"
        onClick={() => setOpen(!isOpen)}
      >
        <span className="flex min-w-0 items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-violet/15 text-violet">
            <Cpu className="size-4" />
          </span>
          <span className="min-w-0 space-y-1">
            <span className="flex flex-wrap items-center gap-2 text-[15px] leading-snug font-semibold tracking-tight text-foreground">
              mihomo 内核
              <Badge variant="outline" className="text-muted-foreground">
                可选
              </Badge>
              <CoreStatusBadge core={core} />
            </span>
            <span className="block text-[13px] leading-5 text-muted-foreground">
              只有导入 ss / vmess / vless / trojan / hysteria2 / tuic 等节点才需要；HTTP / SOCKS5 节点直接导入，不用它。
            </span>
          </span>
        </span>
        <ChevronDown className={cn("mt-2 size-4 shrink-0 text-muted-foreground transition-transform", isOpen && "rotate-180")} />
      </button>

      {isOpen ? (
        <CardContent id="proxy-core-settings" className="space-y-4 border-t border-border">
          <div className="space-y-2 text-[13px] leading-6 text-muted-foreground">
            <p>
              内核是单独的 compose profile，默认不启动。启用后每个导入的节点映射到内核的一个固定本地端口，代理池里的地址是
              <code className="mx-1 rounded bg-field px-1 font-mono text-xs text-foreground/80">
                http://{valueOf("listen_host") || CORE_DEFAULTS.listen_host}:&lt;端口&gt;
              </code>
              ，节点参数随订阅变化时地址不变，账号绑定不受影响。先在部署目录执行：
            </p>
            <div className="flex items-center gap-2 rounded-xl border border-border bg-field/60 py-1.5 pr-1.5 pl-3.5">
              <code className="min-w-0 flex-1 overflow-x-auto font-mono text-xs whitespace-nowrap text-foreground/90">{COMPOSE_COMMAND}</code>
              <Button variant="ghost" size="icon-sm" className="size-7 rounded-md text-muted-foreground" aria-label="复制命令" title="复制命令" onClick={() => void handleCopy()}>
                <Copy className="size-3.5" />
              </Button>
            </div>
          </div>

          {settings?.enabled && status ? (
            <div
              className={cn(
                "flex items-start justify-between gap-3 rounded-xl px-3.5 py-2 text-xs leading-5",
                status.ok && lastApply?.ok !== false ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive",
              )}
            >
              <div className="min-w-0 space-y-1 break-all">
                <div>{status.ok ? `连接正常${status.version ? ` · mihomo ${status.version}` : ""}` : `无法连接：${status.error || "未知错误"}`}</div>
                {lastApply?.ok === false ? (
                  <div>最近一次应用配置失败：{lastApply.error || "未知错误"}</div>
                ) : lastApply?.ok ? (
                  <div className="text-muted-foreground">
                    最近一次应用配置成功{lastApply.nodes != null ? ` · ${lastApply.nodes} 个节点` : ""}
                  </div>
                ) : null}
              </div>
              {/* 内核刚启动或之前没连上：把当前节点配置重新推一次 */}
              <Button
                variant="outline"
                size="sm"
                className="h-7 shrink-0 rounded-lg px-2.5 text-xs"
                title="把当前已导入的内核节点重新写入并热加载"
                onClick={() => void onSave({})}
                disabled={isSaving}
              >
                {isSaving ? <LoaderCircle className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
                重新应用
              </Button>
            </div>
          ) : null}

          <div className="flex items-center justify-between gap-4 rounded-xl border border-border bg-field/50 px-3.5 py-2.5">
            <div className="min-w-0 space-y-0.5">
              <div className="text-[13px] font-medium text-foreground/80">启用内核</div>
              <div className="text-xs leading-5 text-muted-foreground">
                启用后才能导入需内核的节点；关闭后经内核的代理会自动禁用，账号临时借用其他代理，重新启用时自动恢复。
              </div>
            </div>
            <Switch
              checked={enabled}
              onCheckedChange={(next) => setDraft((current) => ({ ...current, enabled: next }))}
              disabled={!settings || isSaving}
              aria-label="启用 mihomo 内核"
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field className="gap-1.5">
              <FieldLabel htmlFor="proxy-core-api-url">控制接口</FieldLabel>
              <Input
                id="proxy-core-api-url"
                value={valueOf("api_url")}
                onChange={(event) => setDraft((current) => ({ ...current, api_url: event.target.value }))}
                placeholder={CORE_DEFAULTS.api_url}
                spellCheck={false}
                autoComplete="off"
                disabled={!settings || isSaving}
                className="h-9 font-mono text-xs"
              />
            </Field>
            <Field className="gap-1.5">
              <FieldLabel htmlFor="proxy-core-secret">控制接口密钥</FieldLabel>
              <Input
                id="proxy-core-secret"
                type="password"
                value={draft.secret ?? ""}
                onChange={(event) => setDraft((current) => ({ ...current, secret: event.target.value }))}
                placeholder={settings?.has_secret ? "已设置，留空保持不变" : "可选"}
                autoComplete="new-password"
                disabled={!settings || isSaving}
                className="h-9 font-mono text-xs"
              />
            </Field>
            <Field className="gap-1.5">
              <FieldLabel htmlFor="proxy-core-listen-host">监听主机</FieldLabel>
              <Input
                id="proxy-core-listen-host"
                value={valueOf("listen_host")}
                onChange={(event) => setDraft((current) => ({ ...current, listen_host: event.target.value }))}
                placeholder={CORE_DEFAULTS.listen_host}
                spellCheck={false}
                autoComplete="off"
                disabled={!settings || isSaving}
                className="h-9 font-mono text-xs"
              />
            </Field>
            <Field className="gap-1.5">
              <FieldLabel htmlFor="proxy-core-port-start">起始端口</FieldLabel>
              <Input
                id="proxy-core-port-start"
                type="number"
                inputMode="numeric"
                min={PORT_MIN}
                max={PORT_MAX}
                step={1}
                value={valueOf("port_start")}
                onChange={(event) => setDraft((current) => ({ ...current, port_start: event.target.value }))}
                placeholder={String(CORE_DEFAULTS.port_start)}
                disabled={!settings || isSaving}
                className="h-9 font-mono text-[13px] tabular-nums"
              />
            </Field>
          </div>
          <p className="text-xs leading-5 text-muted-foreground">
            监听主机是本服务访问内核端口用的地址（compose 里的服务名）；端口从起始端口依次分配，已分配的节点端口保持不变。
          </p>

          <div className="flex justify-end gap-1.5">
            {isDirty ? (
              <Button variant="ghost" size="sm" onClick={() => setDraft({})} disabled={isSaving}>
                <RotateCcw className="size-3.5" />
                还原
              </Button>
            ) : null}
            <Button size="sm" onClick={() => void handleSave()} disabled={!settings || !isDirty || isSaving}>
              {isSaving ? <LoaderCircle className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
              保存
            </Button>
          </div>
        </CardContent>
      ) : null}
    </Card>
  );
}
