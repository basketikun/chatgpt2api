"use client";

import { useTranslation } from "react-i18next";

import { EditableFilePanel } from "./editable-file-panel";

export function PsdPanel() {
  const { t } = useTranslation("debug");
  return <EditableFilePanel title={t("psdPanel.title")} kind="psd" endpoint="/v1/psd/generations" defaultPrompt={t("psdPanel.defaultPrompt")} imageRequired />;
}
