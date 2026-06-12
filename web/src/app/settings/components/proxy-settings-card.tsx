"use client";

import { useState } from "react";
import { Link2, LoaderCircle, PlugZap, Save } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { testProxy, type ProxyTestResult } from "@/lib/api";

import { useSettingsStore } from "../store";

export function ProxySettingsCard() {
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<ProxyTestResult | null>(null);
  const config = useSettingsStore((state) => state.config);
  const isLoadingConfig = useSettingsStore((state) => state.isLoadingConfig);
  const isSavingConfig = useSettingsStore((state) => state.isSavingConfig);
  const setProxy = useSettingsStore((state) => state.setProxy);
  const saveConfig = useSettingsStore((state) => state.saveConfig);

  const proxy = config?.proxy ?? "";

  const handleTest = async () => {
    const candidate = proxy.trim();
    if (!candidate) {
      toast.error("Please fill in the proxy address first");
      return;
    }
    setIsTesting(true);
    setTestResult(null);
    try {
      const data = await testProxy(candidate);
      setTestResult(data.result);
      if (data.result.ok) {
        toast.success(`Proxy available (${data.result.latency_ms} ms, HTTP ${data.result.status})`);
      } else {
        toast.error(`Proxy unavailable: ${data.result.error ?? "Unknown error"}`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Proxy test failed");
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-6 p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-stone-100">
              <Link2 className="size-5 text-stone-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">Global Proxy</h2>
              <p className="text-sm text-stone-500">Configure a unified proxy for outbound requests in the system. Takes effect immediately after saving.</p>
            </div>
          </div>
          <Badge variant={proxy.trim() ? "success" : "secondary"} className="w-fit rounded-md px-2.5 py-1">
            {proxy.trim() ? "Configured" : "Not configured"}
          </Badge>
        </div>

        {isLoadingConfig ? (
          <div className="flex items-center justify-center py-10">
            <LoaderCircle className="size-5 animate-spin text-stone-400" />
          </div>
        ) : (
          <>
            <div className="space-y-2">
              <label className="text-sm font-medium text-stone-700">Proxy Address</label>
              <Input
                value={proxy}
                onChange={(event) => {
                  setProxy(event.target.value);
                  setTestResult(null);
                }}
                placeholder="http://user:pass@127.0.0.1:7890"
                className="h-11 rounded-xl border-stone-200 bg-white"
              />
              <p className="text-sm text-stone-500">
                Leave empty for no proxy. Fill in the full address, e.g. `http://127.0.0.1:7890`, `http://username:password@127.0.0.1:7890` or `socks5://127.0.0.1:7890`.
              </p>
            </div>

            {testResult ? (
              <div
                className={`rounded-xl border px-4 py-3 text-sm leading-6 ${
                  testResult.ok
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-rose-200 bg-rose-50 text-rose-800"
                }`}
              >
                {testResult.ok
                  ? `Proxy available: HTTP ${testResult.status}, took ${testResult.latency_ms} ms`
                  : `Proxy unavailable: ${testResult.error ?? "Unknown error"} (took ${testResult.latency_ms} ms)`}
              </div>
            ) : null}

            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                className="h-10 rounded-xl border-stone-200 bg-white px-5 text-stone-700"
                onClick={() => void handleTest()}
                disabled={isTesting || isLoadingConfig}
              >
                {isTesting ? <LoaderCircle className="size-4 animate-spin" /> : <PlugZap className="size-4" />}
                Test Proxy
              </Button>
              <Button
                className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
                onClick={() => void saveConfig()}
                disabled={isSavingConfig}
              >
                {isSavingConfig ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
                Save Config
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
