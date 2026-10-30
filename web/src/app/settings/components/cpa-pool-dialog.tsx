"use client";

import { Eye, EyeOff, Link2, LoaderCircle, Save, Unplug } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import { useSettingsStore } from "../store";

export function CPAPoolDialog() {
  const { t } = useTranslation("settings");
  const { t: tCommon } = useTranslation("common");
  const dialogOpen = useSettingsStore((state) => state.dialogOpen);
  const editingPool = useSettingsStore((state) => state.editingPool);
  const formName = useSettingsStore((state) => state.formName);
  const formBaseUrl = useSettingsStore((state) => state.formBaseUrl);
  const formSecretKey = useSettingsStore((state) => state.formSecretKey);
  const showSecret = useSettingsStore((state) => state.showSecret);
  const isSavingPool = useSettingsStore((state) => state.isSavingPool);
  const setDialogOpen = useSettingsStore((state) => state.setDialogOpen);
  const setFormName = useSettingsStore((state) => state.setFormName);
  const setFormBaseUrl = useSettingsStore((state) => state.setFormBaseUrl);
  const setFormSecretKey = useSettingsStore((state) => state.setFormSecretKey);
  const setShowSecret = useSettingsStore((state) => state.setShowSecret);
  const savePool = useSettingsStore((state) => state.savePool);

  return (
    <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
      <DialogContent showCloseButton={false} className="rounded-2xl p-6">
        <DialogHeader className="gap-2">
          <DialogTitle>{editingPool ? t("cpa.dialog.titleEdit") : t("cpa.actions.addConnection")}</DialogTitle>
          <DialogDescription className="text-sm leading-6">
            {editingPool ? t("cpa.dialog.descriptionEdit") : t("cpa.dialog.descriptionAdd")}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-stone-700">{t("cpa.dialog.nameLabel")}</label>
            <Input
              value={formName}
              onChange={(event) => setFormName(event.target.value)}
              placeholder={t("cpa.dialog.namePlaceholder")}
              className="h-11 rounded-xl border-stone-200 bg-white"
            />
          </div>
          <div className="space-y-2">
            <label className="flex items-center gap-1.5 text-sm font-medium text-stone-700">
              <Link2 className="size-3.5" />
              {t("cpa.dialog.urlLabel")}
            </label>
            <Input
              value={formBaseUrl}
              onChange={(event) => setFormBaseUrl(event.target.value)}
              placeholder="http://your-cpa-host:8317"
              className="h-11 rounded-xl border-stone-200 bg-white"
            />
          </div>
          <div className="space-y-2">
            <label className="flex items-center gap-1.5 text-sm font-medium text-stone-700">
              <Unplug className="size-3.5" />
              Management Secret Key
            </label>
            <div className="relative">
              <Input
                type={showSecret ? "text" : "password"}
                value={formSecretKey}
                onChange={(event) => setFormSecretKey(event.target.value)}
                placeholder={editingPool ? t("cpa.dialog.secretKeyPlaceholderKeep") : t("cpa.dialog.secretKeyPlaceholderNew")}
                className="h-11 rounded-xl border-stone-200 bg-white pr-10"
              />
              <button
                type="button"
                className="absolute top-1/2 right-3 -translate-y-1/2 text-stone-400 transition hover:text-stone-600"
                onClick={() => setShowSecret(!showSecret)}
              >
                {showSecret ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </div>
        </div>
        <DialogFooter className="pt-2">
          <Button
            variant="secondary"
            className="h-10 rounded-xl bg-stone-100 px-5 text-stone-700 hover:bg-stone-200"
            onClick={() => setDialogOpen(false)}
            disabled={isSavingPool}
          >
            {tCommon("canvasDialog.cancel")}
          </Button>
          <Button
            className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
            onClick={() => void savePool()}
            disabled={isSavingPool}
          >
            {isSavingPool ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
            {editingPool ? t("cpa.dialog.saveButton") : t("cpa.dialog.addButton")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
