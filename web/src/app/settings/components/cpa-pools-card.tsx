"use client";

import { Import, LoaderCircle, Pencil, Plus, ServerCog, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

import { useI18n } from "@/lib/i18n";
import { useSettingsStore } from "../store";

export function CPAPoolsCard() {
  const { t } = useI18n();
  const pools = useSettingsStore((state) => state.pools);
  const isLoadingPools = useSettingsStore((state) => state.isLoadingPools);
  const deletingId = useSettingsStore((state) => state.deletingId);
  const loadingFilesId = useSettingsStore((state) => state.loadingFilesId);
  const openAddDialog = useSettingsStore((state) => state.openAddDialog);
  const openEditDialog = useSettingsStore((state) => state.openEditDialog);
  const deletePool = useSettingsStore((state) => state.deletePool);
  const browseFiles = useSettingsStore((state) => state.browseFiles);

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-6 p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-stone-100">
              <ServerCog className="size-5 text-stone-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">{t.settings.cpaPoolsTitle}</h2>
              <p className="text-sm text-stone-500">{t.settings.cpaPoolsDesc}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {pools.length > 0 ? <Badge className="rounded-md px-2.5 py-1">{t.settings.connectionsCount(pools.length)}</Badge> : null}
            <Button className="h-9 rounded-xl bg-stone-950 px-4 text-white hover:bg-stone-800" onClick={openAddDialog}>
              <Plus className="size-4" />
              {t.settings.addConnection}
            </Button>
          </div>
        </div>

        {isLoadingPools ? (
          <div className="flex items-center justify-center py-10">
            <LoaderCircle className="size-5 animate-spin text-stone-400" />
          </div>
        ) : pools.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 rounded-xl bg-stone-50 px-6 py-10 text-center">
            <ServerCog className="size-8 text-stone-300" />
            <div className="space-y-1">
              <p className="text-sm font-medium text-stone-600">{t.settings.noCpaConnections}</p>
              <p className="text-sm text-stone-400">{t.settings.noCpaConnectionsDesc}</p>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {pools.map((pool) => {
              const isBusy = deletingId === pool.id || loadingFilesId === pool.id;
              const importJob = pool.import_job ?? null;
              const progress = importJob?.total
                ? Math.round((importJob.completed / importJob.total) * 100)
                : 0;

              return (
                <div key={pool.id} className="flex flex-col gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-stone-800">{pool.name || pool.base_url}</div>
                      <div className="truncate text-xs text-stone-400 font-mono" dir="ltr">{pool.base_url}</div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className="rounded-lg p-2 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
                        onClick={() => openEditDialog(pool)}
                        disabled={isBusy}
                        title={t.common.edit}
                      >
                        <Pencil className="size-4" />
                      </button>
                      <button
                        type="button"
                        className="rounded-lg p-2 text-stone-400 transition hover:bg-rose-50 hover:text-rose-500"
                        onClick={() => void deletePool(pool)}
                        disabled={isBusy}
                        title={t.common.delete}
                      >
                        {deletingId === pool.id ? (
                          <LoaderCircle className="size-4 animate-spin" />
                        ) : (
                          <Trash2 className="size-4" />
                        )}
                      </button>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      className="h-8 rounded-lg border-stone-200 bg-white px-3 text-xs text-stone-600"
                      onClick={() => void browseFiles(pool)}
                      disabled={isBusy}
                    >
                      {loadingFilesId === pool.id ? (
                        <LoaderCircle className="size-3.5 animate-spin" />
                      ) : (
                        <Import className="size-3.5" />
                      )}
                      {t.settings.syncBtn}
                    </Button>
                  </div>

                  {importJob ? (
                    <div className="space-y-2 rounded-xl bg-stone-50 px-3 py-3">
                      <div className="text-xs font-medium tracking-[0.16em] text-stone-400 uppercase">{t.settings.importTask}</div>
                      <div className="rounded-lg border border-stone-200 bg-white px-3 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-stone-700">
                              {importJob.status} ({importJob.completed}/{importJob.total})
                            </div>
                            <div className="truncate text-xs text-stone-400 font-mono" dir="ltr">
                              {importJob.job_id.slice(0, 8)} · {importJob.created_at}
                            </div>
                          </div>
                          <Badge
                            variant={
                              importJob.status === "completed"
                                ? "success"
                                : importJob.status === "failed"
                                  ? "danger"
                                  : "info"
                            }
                            className="rounded-md"
                          >
                            {progress}%
                          </Badge>
                        </div>
                        <div className="mt-3 h-2 overflow-hidden rounded-full bg-stone-200">
                          <div className="h-full rounded-full bg-stone-900 transition-all" style={{ width: `${progress}%` }} />
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2 text-xs text-stone-500">
                          <span>{t.settings.addedLabel(importJob.added)}</span>
                          <span>{t.settings.skippedLabel(importJob.skipped)}</span>
                          <span>{t.settings.refreshedLabel(importJob.refreshed)}</span>
                          <span>{t.settings.failedLabel(importJob.failed)}</span>
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}

        <div className="rounded-xl bg-stone-50 px-4 py-3 text-sm leading-6 text-stone-500">
          <p className="font-medium text-stone-600">{t.settings.instructionsTitle}</p>
          <ul className="mt-1 list-inside list-disc space-y-0.5">
            {t.settings.cpaInstructions.map((instruction, idx) => (
              <li key={idx}>{instruction}</li>
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}
