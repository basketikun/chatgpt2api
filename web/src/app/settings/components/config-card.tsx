"use client";

import { Cloud, LoaderCircle, PlugZap, RefreshCw, Save } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { ImageStorageMode } from "@/lib/api";
import { testProxy, type ProxyTestResult } from "@/lib/api";

import { useSettingsStore } from "../store";

export function ConfigCard() {
  const { t } = useTranslation("settings");
  const [isTestingProxy, setIsTestingProxy] = useState(false);
  const [proxyTestResult, setProxyTestResult] = useState<ProxyTestResult | null>(null);
  const logLevelOptions = ["debug", "info", "warning", "error"];
  const config = useSettingsStore((state) => state.config);
  const isLoadingConfig = useSettingsStore((state) => state.isLoadingConfig);
  const isSavingConfig = useSettingsStore((state) => state.isSavingConfig);
  const setRefreshAccountIntervalMinute = useSettingsStore((state) => state.setRefreshAccountIntervalMinute);
  const setImageRetentionDays = useSettingsStore((state) => state.setImageRetentionDays);
  const setImagePollTimeoutSecs = useSettingsStore((state) => state.setImagePollTimeoutSecs);
  const setImageAccountConcurrency = useSettingsStore((state) => state.setImageAccountConcurrency);
  const setImageSettleEnabled = useSettingsStore((state) => state.setImageSettleEnabled);
  const setImageRemoveConversationAfterResult = useSettingsStore((state) => state.setImageRemoveConversationAfterResult);
  const setImageRemoveConversationAlways = useSettingsStore((state) => state.setImageRemoveConversationAlways);
  const setImageSettleSecs = useSettingsStore((state) => state.setImageSettleSecs);
  const setImageTimeoutRetrySecs = useSettingsStore((state) => state.setImageTimeoutRetrySecs);
  const setAutoRemoveInvalidAccounts = useSettingsStore((state) => state.setAutoRemoveInvalidAccounts);
  const setAutoRemoveRateLimitedAccounts = useSettingsStore((state) => state.setAutoRemoveRateLimitedAccounts);
  const setAutoReloginAfterRefresh = useSettingsStore((state) => state.setAutoReloginAfterRefresh);
  const setLogLevel = useSettingsStore((state) => state.setLogLevel);
  const setProxy = useSettingsStore((state) => state.setProxy);
  const setBaseUrl = useSettingsStore((state) => state.setBaseUrl);
  const setGlobalSystemPrompt = useSettingsStore((state) => state.setGlobalSystemPrompt);
  const setDefaultUpstreamModelName = useSettingsStore((state) => state.setDefaultUpstreamModelName);
  const setDefaultThinkingEffort = useSettingsStore((state) => state.setDefaultThinkingEffort);
  const setSensitiveWordsText = useSettingsStore((state) => state.setSensitiveWordsText);
  const setAIReviewField = useSettingsStore((state) => state.setAIReviewField);
  const setImageStorageField = useSettingsStore((state) => state.setImageStorageField);
  const testImageStorage = useSettingsStore((state) => state.testImageStorage);
  const syncImagesToWebDAV = useSettingsStore((state) => state.syncImagesToWebDAV);
  const isTestingImageStorage = useSettingsStore((state) => state.isTestingImageStorage);
  const isSyncingImageStorage = useSettingsStore((state) => state.isSyncingImageStorage);
  const saveConfig = useSettingsStore((state) => state.saveConfig);

  const handleTestProxy = async () => {
    const candidate = String(config?.proxy || "").trim();
    if (!candidate) {
      toast.error(t("core.fields.proxy.toasts.fillUrlFirst"));
      return;
    }
    setIsTestingProxy(true);
    setProxyTestResult(null);
    try {
      const data = await testProxy(candidate);
      setProxyTestResult(data.result);
      if (data.result.ok) {
        toast.success(t("core.fields.proxy.toasts.testAvailable", { latency: data.result.latency_ms, status: data.result.status }));
      } else {
        toast.error(t("core.fields.proxy.toasts.testUnavailable", { error: data.result.error ?? t("core.fields.proxy.toasts.unknownError") }));
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("core.fields.proxy.toasts.testFailed"));
    } finally {
      setIsTestingProxy(false);
    }
  };

  if (isLoadingConfig) {
    return (
      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="flex items-center justify-center p-10">
          <LoaderCircle className="size-5 animate-spin text-stone-400" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-4 p-6">
        <div className="rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm leading-6 text-stone-600">
          {t("core.banner")}
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <label className="text-sm text-stone-700">{t("core.fields.refreshInterval.label")}</label>
            <Input
              value={String(config?.refresh_account_interval_minute || "")}
              onChange={(event) => setRefreshAccountIntervalMinute(event.target.value)}
              placeholder={t("core.fields.refreshInterval.placeholder")}
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">{t("core.fields.refreshInterval.hint")}</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">{t("core.fields.proxy.label")}</label>
            <Input
              value={String(config?.proxy || "")}
              onChange={(event) => {
                setProxy(event.target.value);
                setProxyTestResult(null);
              }}
              placeholder="http://127.0.0.1:7890"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs leading-5 text-stone-500">
              {t("core.fields.proxy.hint")}
            </p>
            {proxyTestResult ? (
              <div
                className={`rounded-xl border px-3 py-2 text-xs leading-6 ${
                  proxyTestResult.ok
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-rose-200 bg-rose-50 text-rose-800"
                }`}
              >
                {proxyTestResult.ok
                  ? t("core.fields.proxy.testResult.available", { status: proxyTestResult.status, latency: proxyTestResult.latency_ms })
                  : t("core.fields.proxy.testResult.unavailable", { error: proxyTestResult.error ?? t("core.fields.proxy.toasts.unknownError"), latency: proxyTestResult.latency_ms })}
              </div>
            ) : null}
            <div className="flex justify-end">
              <Button
                type="button"
                variant="outline"
                className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                onClick={() => void handleTestProxy()}
                disabled={isTestingProxy}
              >
                {isTestingProxy ? <LoaderCircle className="size-4 animate-spin" /> : <PlugZap className="size-4" />}
                {t("core.fields.proxy.testButton")}
              </Button>
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">{t("core.fields.imageBaseUrl.label")}</label>
            <Input
              value={String(config?.base_url || "")}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="https://example.com"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">{t("core.fields.imageBaseUrl.hint")}</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">{t("core.fields.defaultUpstreamModel.label")}</label>
            <Input
              value={String(config?.default_upstream_model_name || "")}
              onChange={(event) => setDefaultUpstreamModelName(event.target.value)}
              placeholder="gpt-5-5"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">{t("core.fields.defaultUpstreamModel.hint")}</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">{t("core.fields.defaultThinkingEffort.label")}</label>
            <Select
              value={String(config?.default_thinking_effort || "auto")}
              onValueChange={(value) => setDefaultThinkingEffort(value as "auto" | "standard" | "extended" | "max")}
            >
              <SelectTrigger className="h-10 rounded-xl border-stone-200 bg-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">{t("core.fields.defaultThinkingEffort.options.auto")}</SelectItem>
                <SelectItem value="standard">Standard</SelectItem>
                <SelectItem value="extended">Extended</SelectItem>
                <SelectItem value="max">Max</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-stone-500">{t("core.fields.defaultThinkingEffort.hint")}</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">{t("core.fields.imageRetentionDays.label")}</label>
            <Input
              value={String(config?.image_retention_days || "")}
              onChange={(event) => setImageRetentionDays(event.target.value)}
              placeholder="30"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">{t("core.fields.imageRetentionDays.hint")}</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">{t("core.fields.imagePollTimeout.label")}</label>
            <Input
              value={String(config?.image_poll_timeout_secs || "")}
              onChange={(event) => setImagePollTimeoutSecs(event.target.value)}
              placeholder="120"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">{t("core.fields.imagePollTimeout.hint")}</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">{t("core.fields.imageAccountConcurrency.label")}</label>
            <Input
              value={String(config?.image_account_concurrency || "")}
              onChange={(event) => setImageAccountConcurrency(event.target.value)}
              placeholder="1"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">{t("core.fields.imageAccountConcurrency.hint")}</p>
          </div>
          <div className="space-y-2">
            <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700">
              <Checkbox
                checked={Boolean(config?.auto_remove_invalid_accounts)}
                onCheckedChange={(checked) => setAutoRemoveInvalidAccounts(Boolean(checked))}
              />
              {t("core.fields.autoRemoveInvalidAccounts.label")}
            </label>
            <p className="text-xs text-stone-500">{t("core.fields.autoRemoveInvalidAccounts.hint")}</p>
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3">
              <Checkbox
                checked={Boolean(config?.image_settle_enabled !== false)}
                onCheckedChange={(checked) => setImageSettleEnabled(Boolean(checked))}
              />
              <span className="text-sm text-stone-700">{t("core.fields.imageSettleEnabled.label")}</span>
            </div>
            <p className="text-xs text-stone-500">{t("core.fields.imageSettleEnabled.hint")}</p>
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3">
              <Checkbox
                checked={Boolean(config?.image_remove_conversation_after_result)}
                onCheckedChange={(checked) => setImageRemoveConversationAfterResult(Boolean(checked))}
              />
              <span className="text-sm text-stone-700">{t("core.fields.imageRemoveConversationAfterResult.label")}</span>
            </div>
            <p className="text-xs text-stone-500">{t("core.fields.imageRemoveConversationAfterResult.hint")}</p>
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3">
              <Checkbox
                checked={Boolean(config?.image_remove_conversation_always)}
                onCheckedChange={(checked) => setImageRemoveConversationAlways(Boolean(checked))}
              />
              <span className="text-sm text-stone-700">{t("core.fields.imageRemoveConversationAlways.label")}</span>
            </div>
            <p className="text-xs text-stone-500">{t("core.fields.imageRemoveConversationAlways.hint")}</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">{t("core.fields.imageTimeoutRetrySecs.label")}</label>
            <Input
              value={String(config?.image_timeout_retry_secs || "30")}
              onChange={(event) => setImageTimeoutRetrySecs(event.target.value)}
              placeholder="30"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">{t("core.fields.imageTimeoutRetrySecs.hint")}</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">{t("core.fields.imageSettleSecs.label")}</label>
            <Input
              value={String(config?.image_settle_secs || "2.0")}
              onChange={(event) => setImageSettleSecs(event.target.value)}
              placeholder="2.0"
              className="h-10 rounded-xl border-stone-200 bg-white disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!config?.image_settle_enabled}
            />
            <p className="text-xs text-stone-500">{t("core.fields.imageSettleSecs.hint")}</p>
          </div>
          <div className="flex gap-4 md:col-span-2">
            <div className="flex-1 space-y-2">
              <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700">
                <Checkbox
                  checked={Boolean(config?.auto_relogin_after_refresh)}
                  onCheckedChange={(checked) => setAutoReloginAfterRefresh(Boolean(checked))}
                />
                {t("core.fields.autoReloginAfterRefresh.label")}
              </label>
              <p className="text-xs text-stone-500">{t("core.fields.autoReloginAfterRefresh.hint")}</p>
            </div>
            <div className="flex-1" aria-hidden="true" />
          </div>
          <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700">
            <Checkbox
              checked={Boolean(config?.auto_remove_rate_limited_accounts)}
              onCheckedChange={(checked) => setAutoRemoveRateLimitedAccounts(Boolean(checked))}
            />
            {t("core.fields.autoRemoveRateLimitedAccounts.label")}
          </label>
          <div className="space-y-3 rounded-xl border border-stone-200 bg-white px-4 py-3">
            <div>
              <label className="text-sm text-stone-700">{t("core.fields.logLevel.label")}</label>
              <p className="mt-1 text-xs text-stone-500">{t("core.fields.logLevel.hint")}</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {logLevelOptions.map((level) => (
                <label key={level} className="flex items-center gap-2 text-sm capitalize text-stone-700">
                  <Checkbox
                    checked={Boolean(config?.log_levels?.includes(level))}
                    onCheckedChange={(checked) => setLogLevel(level, Boolean(checked))}
                  />
                  {level}
                </label>
              ))}
            </div>
          </div>
          <div className="space-y-2 md:col-span-2">
            <label className="text-sm text-stone-700">{t("core.fields.globalSystemPrompt.label")}</label>
            <Textarea
              value={String(config?.global_system_prompt || "")}
              onChange={(event) => setGlobalSystemPrompt(event.target.value)}
              placeholder={t("core.fields.globalSystemPrompt.placeholder")}
              className="min-h-28 rounded-xl border-stone-200 bg-white font-mono text-xs shadow-none"
            />
            <p className="text-xs text-stone-500">{t("core.fields.globalSystemPrompt.hint")}</p>
          </div>
          <div className="space-y-2 md:col-span-2">
            <label className="text-sm text-stone-700">{t("core.fields.sensitiveWords.label")}</label>
            <Textarea
              value={(config?.sensitive_words || []).join("\n")}
              onChange={(event) => setSensitiveWordsText(event.target.value)}
              placeholder={t("core.fields.sensitiveWords.placeholder")}
              className="min-h-28 rounded-xl border-stone-200 bg-white font-mono text-xs shadow-none"
            />
            <p className="text-xs text-stone-500">{t("core.fields.sensitiveWords.hint")}</p>
          </div>
          <div className="space-y-4 rounded-xl border border-stone-200 bg-white px-4 py-3 md:col-span-2">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <label className="flex items-center gap-3 text-sm text-stone-700">
                <Checkbox
                  checked={Boolean(config?.image_storage?.enabled)}
                  onCheckedChange={(checked) => setImageStorageField("enabled", Boolean(checked))}
                />
                {t("core.imageStorage.enableLabel")}
              </label>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                  onClick={() => void testImageStorage()}
                  disabled={isTestingImageStorage || !config?.image_storage?.enabled}
                >
                  {isTestingImageStorage ? <LoaderCircle className="size-4 animate-spin" /> : <Cloud className="size-4" />}
                  {t("core.imageStorage.testButton")}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                  onClick={() => void syncImagesToWebDAV()}
                  disabled={isSyncingImageStorage || !config?.image_storage?.enabled || config?.image_storage?.mode === "local"}
                >
                  {isSyncingImageStorage ? <LoaderCircle className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
                  {t("core.imageStorage.syncButton")}
                </Button>
              </div>
            </div>
            <p className="text-xs leading-6 text-stone-500">
              {t("core.imageStorage.syncHint")}
            </p>
            <div className="rounded-lg border border-stone-100 bg-stone-50 px-3 py-2 text-xs text-stone-600">
              {t("core.imageStorage.currentModeLabel")}
              <span className="ml-1 font-medium text-stone-900">
                {config?.image_storage?.enabled
                  ? config.image_storage.mode === "both"
                    ? t("core.imageStorage.modes.both")
                    : config.image_storage.mode === "webdav"
                      ? t("core.imageStorage.modes.webdav")
                      : t("core.imageStorage.modes.local")
                  : t("core.imageStorage.modes.local")}
              </span>
              <span className="ml-2 text-stone-400">{t("core.imageStorage.modeSaveHint")}</span>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <label className="text-sm text-stone-700">{t("core.imageStorage.fields.saveMode.label")}</label>
                <Select
                  value={String(config?.image_storage?.mode || "local")}
                  onValueChange={(value) => setImageStorageField("mode", value as ImageStorageMode)}
                  disabled={!config?.image_storage?.enabled}
                >
                  <SelectTrigger className="h-10 rounded-xl border-stone-200 bg-white shadow-none">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="local">{t("core.imageStorage.modes.local")}</SelectItem>
                    <SelectItem value="webdav">{t("core.imageStorage.modes.webdav")}</SelectItem>
                    <SelectItem value="both">{t("core.imageStorage.modes.both")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2 md:col-span-2">
                <label className="text-sm text-stone-700">WebDAV URL</label>
                <Input
                  value={String(config?.image_storage?.webdav_url || "")}
                  onChange={(event) => setImageStorageField("webdav_url", event.target.value)}
                  placeholder="https://example.com/dav"
                  className="h-10 rounded-xl border-stone-200 bg-white"
                  disabled={!config?.image_storage?.enabled}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">{t("core.imageStorage.fields.username.label")}</label>
                <Input
                  value={String(config?.image_storage?.webdav_username || "")}
                  onChange={(event) => setImageStorageField("webdav_username", event.target.value)}
                  className="h-10 rounded-xl border-stone-200 bg-white"
                  disabled={!config?.image_storage?.enabled}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">{t("core.imageStorage.fields.password.label")}</label>
                <Input
                  type="password"
                  value={String(config?.image_storage?.webdav_password || "")}
                  onChange={(event) => setImageStorageField("webdav_password", event.target.value)}
                  className="h-10 rounded-xl border-stone-200 bg-white"
                  disabled={!config?.image_storage?.enabled}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">{t("core.imageStorage.fields.remotePath.label")}</label>
                <Input
                  value={String(config?.image_storage?.webdav_root_path || "")}
                  onChange={(event) => setImageStorageField("webdav_root_path", event.target.value)}
                  placeholder="chatgpt2api/images"
                  className="h-10 rounded-xl border-stone-200 bg-white"
                  disabled={!config?.image_storage?.enabled}
                />
              </div>
              <div className="space-y-2 md:col-span-3">
                <label className="text-sm text-stone-700">{t("core.imageStorage.fields.publicBaseUrl.label")}</label>
                <Input
                  value={String(config?.image_storage?.public_base_url || "")}
                  onChange={(event) => setImageStorageField("public_base_url", event.target.value)}
                  placeholder="https://cdn.example.com/chatgpt2api/images"
                  className="h-10 rounded-xl border-stone-200 bg-white"
                  disabled={!config?.image_storage?.enabled}
                />
                <p className="text-xs text-stone-500">{t("core.imageStorage.fields.publicBaseUrl.hint")}</p>
              </div>
            </div>
          </div>
          <div className="space-y-4 rounded-xl border border-stone-200 bg-white px-4 py-3 md:col-span-2">
            <label className="flex items-center gap-3 text-sm text-stone-700">
              <Checkbox
                checked={Boolean(config?.ai_review?.enabled)}
                onCheckedChange={(checked) => setAIReviewField("enabled", Boolean(checked))}
              />
              {t("core.aiReview.enableLabel")}
            </label>
            <p className="text-xs leading-6 text-stone-500">
              {t("core.aiReview.hint")}
            </p>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <label className="text-sm text-stone-700">Base URL</label>
                <Input value={String(config?.ai_review?.base_url || "")} onChange={(event) => setAIReviewField("base_url", event.target.value)} placeholder="https://api.openai.com" className="h-10 rounded-xl border-stone-200 bg-white" />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">API Key</label>
                <Input value={String(config?.ai_review?.api_key || "")} onChange={(event) => setAIReviewField("api_key", event.target.value)} placeholder="sk-..." className="h-10 rounded-xl border-stone-200 bg-white" />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">Model</label>
                <Input value={String(config?.ai_review?.model || "")} onChange={(event) => setAIReviewField("model", event.target.value)} placeholder="gpt-5.4-mini" className="h-10 rounded-xl border-stone-200 bg-white" />
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-sm text-stone-700">{t("core.aiReview.fields.prompt.label")}</label>
              <Textarea value={String(config?.ai_review?.prompt || "")} onChange={(event) => setAIReviewField("prompt", event.target.value)} placeholder={t("core.aiReview.fields.prompt.placeholder")} className="min-h-24 rounded-xl border-stone-200 bg-white text-xs shadow-none" />
            </div>
          </div>
        </div>

        <div className="flex justify-end">
          <Button
            className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
            onClick={() => void saveConfig()}
            disabled={isSavingConfig}
          >
            {isSavingConfig ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
            {t("core.actions.save")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
