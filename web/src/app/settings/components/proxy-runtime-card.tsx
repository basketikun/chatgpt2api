"use client";

import { AlertTriangle, Cookie, LoaderCircle, PlugZap, Save, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("settings");
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
        toast.success(t("proxy.runtime.toasts.proxyAvailable", { latency: data.result.latency_ms, status: data.result.status }));
      } else {
        toast.error(t("proxy.runtime.toasts.proxyUnavailable", { error: data.result.error ?? t("proxy.runtime.toasts.unknownError") }));
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("proxy.runtime.toasts.testProxyFailed"));
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
        toast.success(t("proxy.runtime.toasts.clearanceSuccess", { latency: data.result.latency_ms }));
      } else {
        toast.error(t("proxy.runtime.toasts.clearanceFailed", { error: data.result.error ?? data.result.status }));
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("proxy.runtime.toasts.clearanceTestFailed"));
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
              {t("proxy.runtime.title")}
            </div>
            <p className="mt-1 text-xs leading-6 text-stone-500">
              {t("proxy.runtime.description")}
            </p>
          </div>
          <span className={`rounded-full px-3 py-1 text-xs ${runtimeEnabled ? "bg-emerald-50 text-emerald-700" : "bg-stone-100 text-stone-500"}`}>
            {runtimeEnabled ? t("proxy.runtime.status.enabled") : t("proxy.runtime.status.disabled")}
          </span>
        </div>

        <div className="rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-xs leading-6 text-stone-600">
          {t("proxy.runtime.priorityNote")}
        </div>

        <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-6 text-amber-800">
          <AlertTriangle className="mt-1 size-4 shrink-0" />
          <span>{t("proxy.runtime.dockerWarning")}</span>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700 md:col-span-2">
            <Checkbox
              checked={runtimeEnabled}
              onCheckedChange={(checked) => setProxyRuntimeField("enabled", Boolean(checked))}
            />
            {t("proxy.runtime.fields.enable")}
          </label>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">{t("proxy.runtime.fields.egressMode.label")}</label>
            <Select
              value={runtime.egress_mode}
              onValueChange={(value) => setProxyRuntimeField("egress_mode", value as ProxyRuntimeEgressMode)}
              disabled={!runtimeEnabled}
            >
              <SelectTrigger className="h-10 rounded-xl border-stone-200 bg-white shadow-none">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="direct">{t("proxy.runtime.fields.egressMode.direct")}</SelectItem>
                <SelectItem value="single_proxy">{t("proxy.runtime.fields.egressMode.singleProxy")}</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-stone-500">{t("proxy.runtime.fields.egressMode.hint")}</p>
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">{t("proxy.runtime.fields.proxyUrl.label")}</label>
            <Input
              value={runtime.proxy_url}
              onChange={(event) => setProxyRuntimeField("proxy_url", event.target.value)}
              placeholder="http://privoxy:8118"
              className="h-10 rounded-xl border-stone-200 bg-white"
              disabled={!runtimeEnabled || runtime.egress_mode !== "single_proxy"}
            />
            <p className="text-xs leading-5 text-stone-500">
              {t("proxy.runtime.fields.proxyUrl.hint")}
            </p>
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">{t("proxy.runtime.fields.resourceProxyUrl.label")}</label>
            <Input
              value={runtime.resource_proxy_url}
              onChange={(event) => setProxyRuntimeField("resource_proxy_url", event.target.value)}
              placeholder={t("proxy.runtime.fields.resourceProxyUrl.placeholder")}
              className="h-10 rounded-xl border-stone-200 bg-white"
              disabled={!runtimeEnabled || runtime.egress_mode !== "single_proxy"}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">{t("proxy.runtime.fields.resetStatusCodes.label")}</label>
            <Input
              value={runtime.reset_session_status_codes.join(",")}
              onChange={(event) => setProxyRuntimeStatusCodesText(event.target.value)}
              placeholder="403"
              className="h-10 rounded-xl border-stone-200 bg-white"
              disabled={!runtimeEnabled}
            />
            <p className="text-xs text-stone-500">{t("proxy.runtime.fields.resetStatusCodes.hint")}</p>
          </div>

          <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700">
            <Checkbox
              checked={Boolean(runtime.skip_ssl_verify)}
              onCheckedChange={(checked) => setProxyRuntimeField("skip_ssl_verify", Boolean(checked))}
              disabled={!runtimeEnabled}
            />
            {t("proxy.runtime.fields.skipSslVerify")}
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
              {t("proxy.runtime.actions.testProxy")}
            </Button>
          </div>

          {proxyResult ? (
            <div className={`rounded-xl border px-3 py-2 text-xs leading-6 md:col-span-2 ${proxyResult.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}`}>
              {proxyResult.ok
                ? t("proxy.runtime.testResult.available", { status: proxyResult.status, latency: proxyResult.latency_ms, source: proxyResult.proxy_source ?? "unknown" })
                : t("proxy.runtime.testResult.unavailable", { error: proxyResult.error ?? t("proxy.runtime.toasts.unknownError"), latency: proxyResult.latency_ms })}
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
              <label className="text-sm text-stone-700">{t("proxy.runtime.clearance.modeLabel")}</label>
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
                  <SelectItem value="none">{t("proxy.runtime.clearance.modeOptions.none")}</SelectItem>
                  <SelectItem value="manual">{t("proxy.runtime.clearance.modeOptions.manual")}</SelectItem>
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
              <label className="text-sm text-stone-700">{t("proxy.runtime.clearance.timeoutLabel")}</label>
              <Input
                value={String(clearance.timeout_sec)}
                onChange={(event) => setProxyRuntimeClearanceField("timeout_sec", event.target.value)}
                placeholder="60"
                className="h-10 rounded-xl border-stone-200 bg-white"
                disabled={!runtimeEnabled || clearanceMode === "none"}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm text-stone-700">{t("proxy.runtime.clearance.refreshIntervalLabel")}</label>
              <Input
                value={String(clearance.refresh_interval)}
                onChange={(event) => setProxyRuntimeClearanceField("refresh_interval", event.target.value)}
                placeholder="3600"
                className="h-10 rounded-xl border-stone-200 bg-white"
                disabled={!runtimeEnabled || clearanceMode === "none"}
              />
            </div>

            <div className="space-y-2 md:col-span-2">
              <label className="text-sm text-stone-700">{t("proxy.runtime.clearance.modeOptions.manual")}</label>
              <Textarea
                value={clearance.cf_cookies}
                onChange={(event) => setProxyRuntimeClearanceField("cf_cookies", event.target.value)}
                placeholder={t("proxy.runtime.clearance.manualCookiePlaceholder")}
                className="min-h-24 rounded-xl border-stone-200 bg-white font-mono text-xs shadow-none"
                disabled={!runtimeEnabled || clearanceMode !== "manual"}
              />
              <p className="text-xs text-stone-500">
                {hasStoredClearance ? t("proxy.runtime.clearance.manualCookieHint.stored") : t("proxy.runtime.clearance.manualCookieHint.empty")}
              </p>
            </div>

            <div className="space-y-2 md:col-span-2">
              <label className="text-sm text-stone-700">{t("proxy.runtime.clearance.cfClearanceLabel")}</label>
              <Input
                value={clearance.cf_clearance}
                onChange={(event) => setProxyRuntimeClearanceField("cf_clearance", event.target.value)}
                placeholder={t("proxy.runtime.clearance.cfClearancePlaceholder")}
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
              {t("proxy.runtime.clearance.warmUpLabel")}
            </label>

            <div className="space-y-2">
              <label className="text-sm text-stone-700">{t("proxy.runtime.clearance.testUrlLabel")}</label>
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
                {t("proxy.runtime.clearance.testButton")}
              </Button>
            </div>

            {clearanceResult ? (
              <div className={`rounded-xl border px-3 py-2 text-xs leading-6 md:col-span-2 ${clearanceResult.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"}`}>
                {clearanceResult.ok
                  ? t("proxy.runtime.clearance.testResult.available", {
                      cookieStatus: clearanceResult.has_cookies
                        ? t("proxy.runtime.clearance.testResult.hasCookies")
                        : t("proxy.runtime.clearance.testResult.noCookies"),
                      latency: clearanceResult.latency_ms,
                    })
                  : t("proxy.runtime.clearance.testResult.unavailable", { error: clearanceResult.error ?? clearanceResult.status, latency: clearanceResult.latency_ms })}
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
            {t("proxy.runtime.actions.save")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
