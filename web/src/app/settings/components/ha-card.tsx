"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { useSettingsStore } from "../store";

export function HACard() {
  const config = useSettingsStore((state) => state.config);
  const saveConfig = useSettingsStore((state) => state.saveConfig);
  const ha = config?.home_assistant || {};
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => { setUrl(ha.url || ""); setToken(ha.token || ""); }, [ha.url, ha.token]);

  const save = async () => {
    await saveConfig({ ...config, home_assistant: { url: url.trim(), token: token.trim() } });
    setSaved(true); setTimeout(() => setSaved(false), 2000);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Home Assistant</CardTitle>
        <CardDescription>Kết nối HA qua Long-Lived Access Token để AI biết trạng thái nhà thông minh và điều khiển thiết bị.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <label className="text-sm">HA URL</label>
          <Input value={url} onChange={e => setUrl(e.target.value)} placeholder="http://172.16.10.200:8123" />
        </div>
        <div>
          <label className="text-sm">Long-Lived Access Token</label>
          <Input type="password" value={token} onChange={e => setToken(e.target.value)} placeholder="Lấy tại HA → Profile → Long-Lived Access Tokens" />
          <p className="text-xs text-muted-foreground mt-1">Vào Home Assistant → Profile → Long-Lived Access Tokens → Create Token → Copy.</p>
        </div>
        <Button onClick={save}>{saved ? "Đã lưu!" : "Lưu"}</Button>
      </CardContent>
    </Card>
  );
}
