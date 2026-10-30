"use client";

import { useTranslation } from "react-i18next";

import { EditableFilePanel } from "./editable-file-panel";

export function PptPanel() {
  const { t } = useTranslation("debug");
  return <EditableFilePanel title={t("pptPanel.title")} kind="ppt" endpoint="/v1/ppt/generations" defaultPrompt={t("pptPanel.defaultPrompt")} />;
}
