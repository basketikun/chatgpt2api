"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { useSettingsStore } from "../store";

export function HACard() {
  const config = useSettingsStore((state) => state.config);
  const saveConfig = useSettingsStore((state) => state.saveConfig);
  const ha = (config?.home_assistant as any) || {};
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [refreshInterval, setRefreshInterval] = useState("3600");
  const [refreshTimes, setRefreshTimes] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setUrl(ha.url || "");
    setToken(ha.token || "");
    setRefreshInterval(String(ha.refresh_interval ?? 3600));
    setRefreshTimes(Array.isArray(ha.refresh_times) ? ha.refresh_times.join(", ") : "");
  }, [ha.url, ha.token, ha.refresh_interval, ha.refresh_times]);

  const save = async () => {
    const intervalNum = Math.max(60, parseInt(refreshInterval) || 3600);
    const times = refreshTimes
      .split(",")
      .map(t => t.trim())
      .filter(t => /^\d{1,2}:\d{2}$/.test(t));
    await saveConfig({
      ...config,
      home_assistant: {
        url: url.trim(),
        token: token.trim(),
        refresh_interval: intervalNum,
        refresh_times: times,
      },
    });
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
        <div>
          <label className="text-sm">Chu kỳ làm mới danh sách thiết bị (giây)</label>
          <Input type="number" min="60" value={refreshInterval} onChange={e => setRefreshInterval(e.target.value)} placeholder="3600" />
          <p className="text-xs text-muted-foreground mt-1">Mặc định 3600 (1 giờ). Tối thiểu 60. Hệ thống sẽ tự fetch lại danh sách entity từ HA mỗi N giây.</p>
        </div>
        <div>
          <label className="text-sm">Giờ làm mới cố định (HH:MM, ngăn cách bằng dấu phẩy)</label>
          <Input value={refreshTimes} onChange={e => setRefreshTimes(e.target.value)} placeholder="00:30, 06:00, 18:00" />
          <p className="text-xs text-muted-foreground mt-1">Tùy chọn. Ngoài chu kỳ ở trên, fetch thêm vào các giờ cố định trong ngày. Để trống nếu không cần.</p>
        </div>
        <Button onClick={save}>{saved ? "Đã lưu!" : "Lưu"}</Button>
      </CardContent>
    </Card>
  );
}
