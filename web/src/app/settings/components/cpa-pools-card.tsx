"use client";

import { Import, LoaderCircle, Pencil, Plus, ServerCog, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

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

  return (
    <Card className="rounded-2xl card-3d card-tint-indigo">
      <CardContent className="space-y-6 p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-stone-100">
              <ServerCog className="size-5 text-stone-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">Quản lý kết nối CPA</h2>
              <p className="text-sm text-stone-500">Cấu hình kết nối trước, sau đó tìm và chọn tài khoản từ xa để nhập vào kho địa phương.</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {pools.length > 0 ? <Badge className="rounded-md px-2.5 py-1">{pools.length} 个kết nối</Badge> : null}
            <Button className="h-9 rounded-xl bg-stone-900 px-4 text-white hover:bg-stone-800" onClick={openAddDialog}>
              <Plus className="size-4" />
              Thêm kết nối
            </Button>
          </div>
        </div>

        {isLoadingPools ? (
          <div className="flex items-center justify-center py-10">
            <LoaderCircle className="size-5 animate-spin text-stone-500" />
          </div>
        ) : pools.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 rounded-xl bg-stone-100 px-6 py-10 text-center">
            <ServerCog className="size-8 text-stone-700" />
            <div className="space-y-1">
              <p className="text-sm font-medium text-stone-600">Chưa có kết nối CPA nào</p>
              <p className="text-sm text-stone-500">Nhấn "Thêm kết nối" để lưu thông tin CLIProxyAPI của bạn.</p>
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
                      <div className="truncate text-xs text-stone-500">{pool.base_url}</div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className="rounded-lg p-2 text-stone-500 transition hover:bg-stone-200 hover:text-stone-700"
                        onClick={() => openEditDialog(pool)}
                        disabled={isBusy}
                        title="Chỉnh sửa"
                      >
                        <Pencil className="size-4" />
                      </button>
                      <button
                        type="button"
                        className="rounded-lg p-2 text-stone-500 transition hover:bg-rose-50 hover:text-rose-500"
                        onClick={() => void deletePool(pool)}
                        disabled={isBusy}
                        title="Xóa"
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
                      Đồng bộ
                    </Button>
                  </div>

                  {importJob ? (
                    <div className="space-y-2 rounded-xl bg-stone-100 px-3 py-3">
                      <div className="text-xs font-medium tracking-[0.16em] text-stone-500 uppercase">Tác vụ nhập</div>
                      <div className="rounded-lg border border-stone-200 bg-white px-3 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-stone-700">
                              Trạng thái {importJob.status}，Đã 处理 {importJob.completed}/{importJob.total}
                            </div>
                            <div className="truncate text-xs text-stone-500">
                              Tác vụ {importJob.job_id.slice(0, 8)} · {importJob.created_at}
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
                          <div className="h-full rounded-full bg-white transition-all" style={{ width: `${progress}%` }} />
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2 text-xs text-stone-500">
                          <span>Mới {importJob.added}</span>
                          <span>Bỏ qua {importJob.skipped}</span>
                          <span>Làm mới {importJob.refreshed}</span>
                          <span>thất bại {importJob.failed}</span>
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}

        <div className="rounded-xl bg-stone-100 px-4 py-3 text-sm leading-6 text-stone-500">
          <p className="font-medium text-stone-600">Hướng dẫn sử dụng</p>
          <ul className="mt-1 list-inside list-disc space-y-0.5">
            <li>Khi vào trang, hệ thống sẽ đọc các kết nối CPA đã cấu hình.</li>
            <li>Nhấn "Đồng bộ" trên một kết nối để đọc danh sách tài khoản từ xa và hiển thị cho bạn chọn.</li>
            <li>Sau khi xác nhận chọn, backend sẽ tải access_token và nhập vào kho địa phương.</li>
            <li>Frontend chỉ hiển thị tiến độ, không tham gia trực tiếp vào việc tải.</li>
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}


