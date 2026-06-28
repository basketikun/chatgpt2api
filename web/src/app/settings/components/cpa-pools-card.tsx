"use client";

import { Import, LoaderCircle, Pencil, Plus, ServerCog, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { DEFAULT_DISPLAY_TIMEZONE, formatDisplayDateTime, normalizeDisplayTimezone } from "@/lib/display-time";

import { useSettingsStore } from "../store";

export function CPAPoolsCard() {
  const pools = useSettingsStore((state) => state.pools);
  const isLoadingPools = useSettingsStore((state) => state.isLoadingPools);
  const deletingId = useSettingsStore((state) => state.deletingId);
  const loadingFilesId = useSettingsStore((state) => state.loadingFilesId);
  const openAddDialog = useSettingsStore((state) => state.openAddDialog);
  const openEditDialog = useSettingsStore((state) => state.openEditDialog);
  const deletePool = useSettingsStore((state) => state.deletePool);
  const browseFiles = useSettingsStore((state) => state.browseFiles);
  const config = useSettingsStore((state) => state.config);
  const displayTimezone = normalizeDisplayTimezone(config?.display_timezone || DEFAULT_DISPLAY_TIMEZONE);

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-6 p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-stone-100">
              <ServerCog className="size-5 text-stone-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">CPA 连接管理</h2>
              <p className="text-sm text-stone-500">先配置连接，再按需查询远程账号并选择导入到本地号池。</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {pools.length > 0 ? <Badge className="rounded-md px-2.5 py-1">{pools.length} 个连接</Badge> : null}
            <Button className="h-9 rounded-xl bg-stone-950 px-4 text-white hover:bg-stone-800" onClick={openAddDialog}>
              <Plus className="size-4" />
              添加连接
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
              <p className="text-sm font-medium text-stone-600">暂无 CPA 连接</p>
              <p className="text-sm text-stone-400">点击「添加连接」保存你的 CLIProxyAPI 信息。</p>
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
                      <div className="truncate text-xs text-stone-400">{pool.base_url}</div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className="rounded-lg p-2 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
                        onClick={() => openEditDialog(pool)}
                        disabled={isBusy}
                        title="编辑"
                      >
                        <Pencil className="size-4" />
                      </button>
                      <button
                        type="button"
                        className="rounded-lg p-2 text-stone-400 transition hover:bg-rose-50 hover:text-rose-500"
                        onClick={() => void deletePool(pool)}
                        disabled={isBusy}
                        title="删除"
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
                      同步
                    </Button>
                  </div>

                  {importJob ? (
                    <div className="space-y-2 rounded-xl bg-stone-50 px-3 py-3">
                      <div className="text-xs font-medium tracking-[0.16em] text-stone-400 uppercase">导入任务</div>
                      <div className="rounded-lg border border-stone-200 bg-white px-3 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-stone-700">
                              状态 {importJob.status}，已处理 {importJob.completed}/{importJob.total}
                            </div>
                            <div className="truncate text-xs text-stone-400">
                              任务 {importJob.job_id.slice(0, 8)} · {formatDisplayDateTime(importJob.created_at, displayTimezone, importJob.created_at)}
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
                          <span>新增 {importJob.added}</span>
                          <span>跳过 {importJob.skipped}</span>
                          <span>刷新 {importJob.refreshed}</span>
                          <span>失败 {importJob.failed}</span>
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
          <p className="font-medium text-stone-600">使用说明</p>
          <ul className="mt-1 list-inside list-disc space-y-0.5">
            <li>页面进入后先读取系统里已配置的 CPA 连接。</li>
            <li>点击某个连接的「同步」后，会先读取远程账号列表并展示给前端选择。</li>
            <li>确认选择后，后端后台下载对应 access_token 并导入本地号池。</li>
            <li>前端只轮询导入进度，不直接参与 download。</li>
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}
