"use client";

import { useEffect, useRef, useState } from "react";

import { useSettingsStore } from "@/app/settings/store";
import { fetchDisplaySettings } from "@/lib/api";
import { DEFAULT_DISPLAY_TIMEZONE, normalizeDisplayTimezone } from "@/lib/display-time";

export function useDisplayTimezone() {
  const didLoadRef = useRef(false);
  const config = useSettingsStore((state) => state.config);
  const [displayTimezone, setDisplayTimezone] = useState(DEFAULT_DISPLAY_TIMEZONE);

  useEffect(() => {
    if (config?.display_timezone) {
      setDisplayTimezone(normalizeDisplayTimezone(config.display_timezone));
      return;
    }
    if (didLoadRef.current) {
      return;
    }
    didLoadRef.current = true;
    void fetchDisplaySettings()
      .then((data) => setDisplayTimezone(normalizeDisplayTimezone(data.display_timezone)))
      .catch(() => setDisplayTimezone(DEFAULT_DISPLAY_TIMEZONE));
  }, [config?.display_timezone]);

  return normalizeDisplayTimezone(config?.display_timezone || displayTimezone);
}
