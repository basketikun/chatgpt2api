"use client";

import { AlertTriangle, Cookie, LoaderCircle, PlugZap, Save, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  testProxy,
  testProxyClearance,
  type ClearanceTestResult,
  type ProxyRuntimeClearanceMode,
  type ProxyRuntimeEgressMode,
  type ProxyTestResult,
} from "@/lib/api";

import { useSettingsStore } from "../store";

export function ProxyRuntimeCard() {
  const [isTestingProxy, setIsTestingProxy] = useState(false);
  const [isTestingClearance, setIsTestingClearance] = useState(false);
  const [proxyResult, setProxyResult] = useState<ProxyTestResult | null>(null);
  const [clearanceResult, setClearanceResult] = useState<ClearanceTestResult | null>(null);
  const [targetUrl, setTargetUrl] = useState("https://chatgpt.com");
  const config = useSettingsStore((state) => state.config);
  const isLoadingConfig = useSettingsStore((state) => state.isLoadingConfig);
  const isSavingConfig = useSettingsStore((state) => state.isSavingConfig);
  const saveConfig = useSettingsStore((state) => state.saveConfig);
  const setProxyRuntimeField = useSettingsStore((state) => state.setProxyRuntimeField);
  const setProxyRuntimeClearanceField = useSettingsStore((state) => state.setProxyRuntimeClearanceField);
  const setProxyRuntimeStatusCodesText = useSettingsStore((state) => state.setProxyRuntimeStatusCodesText);

  if (isLoadingConfig || !config?.proxy_runtime) {
    return (
      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="flex items-center justify-center p-10">
          <LoaderCircle className="size-5 animate-spin text-stone-400" />
        </CardContent>
      </Card>
    );
  }

  const runtime = config.proxy_runtime;
  const clearance = runtime.clearance;
  const runtimeEnabled = Boolean(runtime.enabled);
  const clearanceMode = clearance.mode;
  const hasStoredClearance = Boolean(clearance.has_cf_cookies || clearance.has_cf_clearance);

  const handleTestRuntimeProxy = async () => {
    setIsTestingProxy(true);
    setProxyResult(null);
    try {
      const saved = await saveConfig();
      if (!saved) {
        return;
      }
      const data = await testProxy();
      setProxyResult(data.result);
      if (data.result.ok) {
        toast.success(`清障代理可用（${data.result.latency_ms} ms，HTTP ${data.result.status}）`);
      } else {
        toast.error(`清障代理不可用：${data.result.error ?? "未知错误"}`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "测试清障代理失败");
    } finally {
      setIsTestingProxy(false);
    }
  };

  const handleTestClearance = async () => {
    setIsTestingClearance(true);
    setClearanceResult(null);
    try {
      const saved = await saveConfig();
      if (!saved) {
        return;
      }
      const data = await testProxyClearance(targetUrl.trim() || "https://chatgpt.com");
      setClearanceResult(data.result);
      if (data.result.ok) {
        toast.success(`Clearance 获取成功（${data.result.latency_ms} ms）`);
      } else {
        toast.error(`Clearance 获取失败：${data.result.error ?? data.result.status}`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "测试 Clearance 失败");
    } finally {
      setIsTestingClearance(false);
    }
  };

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-5 p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-base font-semibold text-stone-900">
              <PlugZap className="size-5 text-stone-500" />
              FlareSolverr 清障
            </div>
            <p className="mt-1 text-xs leading-6 text-stone-500">
              默认关闭。用于上游请求遇到 Cloudflare 拦截后获取 clearance，可配合 WARP / Privoxy 代理链路重试。
            </p>
          </div>
          <span className={`rounded-full px-3 py-1 text-xs ${runtimeEnabled ? "bg-emerald-50 text-emerald-700" : "bg-stone-100 text-stone-500"}`}>
            {runtimeEnabled ? "已启用" : "未启用"}
          </span>
        </div>

        <div className="rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-xs leading-6 text-stone-600">
          代理优先级：账号代理 &gt; FlareSolverr 代理链路 &gt; 显式代理 &gt; 全局代理。Cookie / cf_clearance 不会在接口响应中明文返回。
        </div>

        <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-6 text-amber-800">
          <AlertTriangle className="mt-1 size-4 shrink-0" />
          <span>使用 FlareSolverr 模式前，请先通过 Docker 启动 flaresolverr、privoxy、warp-proxy 等相关容器；容器内 URL 通常填写 http://flaresolverr:8191。</span>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700 md:col-span-2">
            <Checkbox
              checked={runtimeEnabled}
              onCheckedChange={(checked) => setProxyRuntimeField("enabled", Boolean(checked))}
            />
            启用 FlareSolverr 清障
          </label>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">出站模式</label>
            <Select
              value={runtime.egress_mode}
              onValueChange={(value) => setProxyRuntimeField("egress_mode", value as ProxyRuntimeEgressMode)}
              disabled={!runtimeEnabled}
            >
              <SelectTrigger className="h-10 rounded-xl border-stone-200 bg-white shadow-none">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="direct">直连</SelectItem>
                <SelectItem value="single_proxy">单代理/WARP</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-stone-500">WARP compose 默认使用 single_proxy。</p>
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">清障代理 URL</label>
            <Input
              value={runtime.proxy_url}
              onChange={(event) => setProxyRuntimeField("proxy_url", event.target.value)}
              placeholder="http://privoxy:8118"
              className="h-10 rounded-xl border-stone-200 bg-white"
              disabled={!runtimeEnabled || runtime.egress_mode !== "single_proxy"}
            />
            <p className="text-xs leading-5 text-stone-500">
              支持 http/https/socks5/socks5h，socks5 会转为 socks5h。带认证格式：协议://账号:密码@主机:端口，也可直接粘贴 主机:端口:账号:密码。
            </p>
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">资源代理 URL</label>
            <Input
              value={runtime.resource_proxy_url}
              onChange={(event) => setProxyRuntimeField("resource_proxy_url", event.target.value)}
              placeholder="留空则复用清障代理"
              className="h-10 rounded-xl border-stone-200 bg-white"
              disabled={!runtimeEnabled || runtime.egress_mode !== "single_proxy"}
            />
          </div>

          <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700">
            <Checkbox
              checked={Boolean(runtime.resource_proxy_enabled)}
              onCheckedChange={(checked) => setProxyRuntimeField("resource_proxy_enabled", Boolean(checked))}
              disabled={!runtimeEnabled || runtime.egress_mode !== "single_proxy"}
            />
            远程图片使用运行时代理
          </label>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">重置会话状态码</label>
            <Input
              value={runtime.reset_session_status_codes.join(",")}
              onChange={(event) => setProxyRuntimeStatusCodesText(event.target.value)}
              placeholder="403"
              className="h-10 rounded-xl border-stone-200 bg-white"
              disabled={!runtimeEnabled}
            />
            <p className="text-xs text-stone-500">默认 403，只对 Cloudflare/挑战类错误触发。</p>
          </div>

          <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700">
            <Checkbox
              checked={Boolean(runtime.skip_ssl_verify)}
              onCheckedChange={(checked) => setProxyRuntimeField("skip_ssl_verify", Boolean(checked))}
              disabled={!runtimeEnabled}
            />
            跳过 SSL 校验
          </label>

          <div className="flex items-end justify-end">
            <Button
              type="button"
              variant="outline"
              className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
              onClick={() => void handleTestRuntimeProxy()}
              disabled={isTestingProxy || !runtimeEnabled}
            >
              {isTestingProxy ? <LoaderCircle className="size-4 animate-spin" /> : <PlugZap className="size-4" />}
              测试当前清障代理
            </Button>
          </div>

          {proxyResult ? (
            <div className={`rounded-xl border px-3 py-2 text-xs leading-6 md:col-span-2 ${proxyResult.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}`}>
              {proxyResult.ok
                ? `代理可用：HTTP ${proxyResult.status}，用时 ${proxyResult.latency_ms} ms，来源 ${proxyResult.proxy_source ?? "unknown"}`
                : `代理不可用：${proxyResult.error ?? "未知错误"}（用时 ${proxyResult.latency_ms} ms）`}
            </div>
          ) : null}
        </div>

        <div className="space-y-4 rounded-xl border border-stone-200 bg-white px-4 py-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2 text-sm font-medium text-stone-800">
              <Cookie className="size-4 text-stone-500" />
              Cloudflare Clearance
            </div>
            <span className={`rounded-full px-3 py-1 text-xs ${clearance.enabled ? "bg-emerald-50 text-emerald-700" : "bg-stone-100 text-stone-500"}`}>
              {clearance.enabled ? clearanceMode : "disabled"}
            </span>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm text-stone-700">Clearance 模式</label>
              <Select
                value={clearanceMode}
                onValueChange={(value) => {
                  const mode = value as ProxyRuntimeClearanceMode;
                  setProxyRuntimeClearanceField("mode", mode);
                  setProxyRuntimeClearanceField("enabled", mode !== "none");
                }}
                disabled={!runtimeEnabled}
              >
                <SelectTrigger className="h-10 rounded-xl border-stone-200 bg-white shadow-none">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">不启用</SelectItem>
                  <SelectItem value="manual">手动 Cookie</SelectItem>
                  <SelectItem value="flaresolverr">FlareSolverr</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label className="text-sm text-stone-700">FlareSolverr URL</label>
              <Input
                value={clearance.flaresolverr_url}
                onChange={(event) => setProxyRuntimeClearanceField("flaresolverr_url", event.target.value)}
                placeholder="http://flaresolverr:8191"
                className="h-10 rounded-xl border-stone-200 bg-white"
                disabled={!runtimeEnabled || clearanceMode !== "flaresolverr"}
              />
            </div>

            <div className="space-y-2 md:col-span-2">
              <label className="text-sm text-stone-700">User-Agent</label>
              <Input
                value={clearance.user_agent}
                onChange={(event) => setProxyRuntimeClearanceField("user_agent", event.target.value)}
                className="h-10 rounded-xl border-stone-200 bg-white font-mono text-xs"
                disabled={!runtimeEnabled || clearanceMode === "none"}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm text-stone-700">超时秒数</label>
              <Input
                value={String(clearance.timeout_sec)}
                onChange={(event) => setProxyRuntimeClearanceField("timeout_sec", event.target.value)}
                placeholder="60"
                className="h-10 rounded-xl border-stone-200 bg-white"
                disabled={!runtimeEnabled || clearanceMode === "none"}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm text-stone-700">刷新间隔秒数</label>
              <Input
                value={String(clearance.refresh_interval)}
                onChange={(event) => setProxyRuntimeClearanceField("refresh_interval", event.target.value)}
                placeholder="3600"
                className="h-10 rounded-xl border-stone-200 bg-white"
                disabled={!runtimeEnabled || clearanceMode === "none"}
              />
            </div>

            <div className="space-y-2 md:col-span-2">
              <label className="text-sm text-stone-700">手动 Cookie</label>
              <Textarea
                value={clearance.cf_cookies}
                onChange={(event) => setProxyRuntimeClearanceField("cf_cookies", event.target.value)}
                placeholder="可选：foo=bar; cf_clearance=..."
                className="min-h-24 rounded-xl border-stone-200 bg-white font-mono text-xs shadow-none"
                disabled={!runtimeEnabled || clearanceMode !== "manual"}
              />
              <p className="text-xs text-stone-500">
                {hasStoredClearance ? "服务端已保存过 Cookie/clearance；留空保存不会清空已有值。" : "留空表示不使用手动 Cookie。"}
              </p>
            </div>

            <div className="space-y-2 md:col-span-2">
              <label className="text-sm text-stone-700">单独 cf_clearance</label>
              <Input
                value={clearance.cf_clearance}
                onChange={(event) => setProxyRuntimeClearanceField("cf_clearance", event.target.value)}
                placeholder="可选：只填写 cf_clearance 值"
                className="h-10 rounded-xl border-stone-200 bg-white font-mono text-xs"
                disabled={!runtimeEnabled || clearanceMode !== "manual"}
              />
            </div>

            <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-stone-700">
              <Checkbox
                checked={Boolean(clearance.warm_up_on_start)}
                onCheckedChange={(checked) => setProxyRuntimeClearanceField("warm_up_on_start", Boolean(checked))}
                disabled={!runtimeEnabled || clearanceMode === "none"}
              />
              启动时预热 Clearance
            </label>

            <div className="space-y-2">
              <label className="text-sm text-stone-700">测试目标 URL</label>
              <Input
                value={targetUrl}
                onChange={(event) => setTargetUrl(event.target.value)}
                placeholder="https://chatgpt.com"
                className="h-10 rounded-xl border-stone-200 bg-white"
                disabled={!runtimeEnabled || clearanceMode === "none"}
              />
            </div>

            <div className="flex justify-end md:col-span-2">
              <Button
                type="button"
                variant="outline"
                className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                onClick={() => void handleTestClearance()}
                disabled={isTestingClearance || !runtimeEnabled || clearanceMode === "none"}
              >
                {isTestingClearance ? <LoaderCircle className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
                测试 Clearance
              </Button>
            </div>

            {clearanceResult ? (
              <div className={`rounded-xl border px-3 py-2 text-xs leading-6 md:col-span-2 ${clearanceResult.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}`}>
                {clearanceResult.ok
                  ? `Clearance 可用：${clearanceResult.has_cookies ? "已获取 Cookie" : "无 Cookie"}，用时 ${clearanceResult.latency_ms} ms`
                  : `Clearance 不可用：${clearanceResult.error ?? clearanceResult.status}（用时 ${clearanceResult.latency_ms} ms）`}
              </div>
            ) : null}
          </div>
        </div>

        <div className="flex justify-end">
          <Button
            type="button"
            className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
            onClick={() => void saveConfig()}
            disabled={isSavingConfig}
          >
            {isSavingConfig ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
            保存配置
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
