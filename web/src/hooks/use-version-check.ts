"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import webConfig from "@/constants/common-env";
import { parseChangelog, type ReleaseInfo } from "@/lib/release";

const latestVersionUrl =
  "https://raw.githubusercontent.com/basketikun/chatgpt2api/main/VERSION";
const latestChangelogUrl =
  "https://raw.githubusercontent.com/basketikun/chatgpt2api/main/CHANGELOG.md";

function readLocalReleases(): ReleaseInfo[] {
  return JSON.parse(process.env.NEXT_PUBLIC_APP_RELEASES || "[]");
}

function toVersionParts(version: string) {
  const match = version.trim().match(/^v?(\d+)\.(\d+)\.(\d+)/);
  return match ? match.slice(1).map(Number) : null;
}

function isNewerVersion(latestVersion: string, currentVersion: string) {
  const latest = toVersionParts(latestVersion);
  const current = toVersionParts(currentVersion);
  if (!latest || !current) return false;
  return latest.some(
    (value, index) =>
      value > current[index] &&
      latest.slice(0, index).every((part, prevIndex) => part === current[prevIndex]),
  );
}

export function useVersionCheck() {
  const { t } = useTranslation("common");
  const currentVersion = webConfig.appVersion;
  const localReleases = useMemo(readLocalReleases, []);
  const [latestVersion, setLatestVersion] = useState(currentVersion);
  const [releases, setReleases] = useState<ReleaseInfo[]>(localReleases);
  const [checking, setChecking] = useState(false);
  const [open, setOpen] = useState(false);
  const hasNewVersion = isNewerVersion(latestVersion, currentVersion);

  const checkLatestRelease = useCallback(
    async (showMessage = false) => {
      setChecking(true);
      try {
        const [versionResponse, changelogResponse] = await Promise.all([
          fetch(latestVersionUrl),
          fetch(latestChangelogUrl),
        ]);
        if (!versionResponse.ok || !changelogResponse.ok) throw new Error();
        const [version, changelog] = await Promise.all([
          versionResponse.text(),
          changelogResponse.text(),
        ]);
        setLatestVersion(version.trim() || currentVersion);
        if (changelog.trim()) setReleases(parseChangelog(changelog));
        if (showMessage) toast.success(t("versionCheck.fetchSuccess"));
      } catch {
        setLatestVersion(currentVersion);
        setReleases(localReleases);
        if (showMessage) toast.error(t("versionCheck.fetchFailed"));
      } finally {
        setChecking(false);
      }
    },
    [currentVersion, localReleases, t],
  );

  const openReleaseModal = () => {
    setOpen(true);
    void checkLatestRelease();
  };

  return {
    open,
    setOpen,
    openReleaseModal,
    latestVersion,
    releases,
    checking,
    hasNewVersion,
    checkLatestRelease,
  };
}
