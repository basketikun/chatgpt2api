"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, Copy, Download, ImageIcon, LoaderCircle, Maximize2, Plus, RefreshCw, Search, Tag, Trash2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { DateRangeFilter } from "@/components/date-range-filter";
import { ImageLightbox } from "@/components/image-lightbox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { compressAllImages, deleteImageTag, deleteManagedImages, deleteToTarget, downloadImages, downloadSingleImage, fetchImageStorage, fetchImageTags, fetchManagedImages, setImageTags, type ImageStorageStats, type ManagedImage } from "@/lib/api";
import { useAuthGuard } from "@/lib/use-auth-guard";

const LONG_PRESS_MS = 800;
const IMAGE_MANAGER_CHECKBOX_CLASS = "border-stone-300 bg-white/80 dark:border-white/35 dark:bg-white/5 data-[state=checked]:border-stone-950 dark:data-[state=checked]:border-white";

function formatSize(size: number) {
  return size > 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(2)} MB` : `${Math.ceil(size / 1024)} KB`;
}

function imageKey(item: ManagedImage) {
  return item.rel || item.url;
}

function useLongPress(onLongPress: () => void, ms = LONG_PRESS_MS) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeRef = useRef(false);

  const start = useCallback((e: React.MouseEvent | React.TouchEvent) => {
    activeRef.current = true;
    timerRef.current = setTimeout(() => {
      if (activeRef.current) {
        onLongPress();
      }
    }, ms);
  }, [onLongPress, ms]);

  const stop = useCallback(() => {
    activeRef.current = false;
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  return {
    onMouseDown: start,
    onMouseUp: stop,
    onMouseLeave: stop,
    onTouchStart: start,
    onTouchEnd: stop,
  };
}

function ImageManagerContent() {
  const { t } = useTranslation("image-manager");
  const { t: tCommon } = useTranslation("common");
  const [items, setItems] = useState<ManagedImage[]>([]);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [lightboxIndex, setLightboxIndex] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [deleteStartDate, setDeleteStartDate] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<ManagedImage | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [allTags, setAllTags] = useState<string[]>([]);
  const [storage, setStorage] = useState<ImageStorageStats | null>(null);
  const [storageLoading, setStorageLoading] = useState(false);
  const [compressResult, setCompressResult] = useState<string>("");
  const [targetFreeMb, setTargetFreeMb] = useState(500);

  const loadStorage = useCallback(async () => {
    try {
      setStorageLoading(true);
      const data = await fetchImageStorage();
      setStorage(data);
    } catch { /* ignore */ }
    finally { setStorageLoading(false); }
  }, []);

  useEffect(() => { void loadStorage(); }, [loadStorage]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagEditTarget, setTagEditTarget] = useState<ManagedImage | null>(null);
  const [tagInput, setTagInput] = useState("");
  const [dialogVisible, setDialogVisible] = useState(false);
  const deleteTargetRef = useRef<ManagedImage | null>(null);
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [deleteMode, setDeleteMode] = useState<"selected" | "filtered" | "byDate" | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);

  const filteredItems = selectedTags.length > 0
    ? items.filter((item) => selectedTags.every((t) => (item.tags ?? []).includes(t)))
    : items;

  const lightboxImages = filteredItems.map((item) => ({
    id: item.name,
    src: item.url,
    sizeLabel: formatSize(item.size),
    dimensions: item.width && item.height ? `${item.width} x ${item.height}` : undefined,
  }));
  const pageSize = 12;
  const pageCount = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const safePage = Math.min(page, pageCount);
  const currentRows = filteredItems.slice((safePage - 1) * pageSize, safePage * pageSize);
  const selectedSet = useMemo(() => new Set(selectedPaths), [selectedPaths]);
  const selectedCount = deleteMode === "filtered" ? items.length : deleteMode === "byDate" ? 0 : selectedPaths.length;
  const currentPageSelected = currentRows.length > 0 && currentRows.every((item) => selectedSet.has(imageKey(item)));
  const allSelected = filteredItems.length > 0 && filteredItems.every((item) => selectedSet.has(imageKey(item)));

  const loadImages = async () => {
    setIsLoading(true);
    try {
      const [data, tagsData] = await Promise.all([
        fetchManagedImages({ start_date: startDate, end_date: endDate }),
        fetchImageTags(),
      ]);
      setItems(data.items);
      setAllTags(tagsData.tags);
      setSelectedPaths((current) => current.filter((path) => data.items.some((item) => imageKey(item) === path)));
      setPage(1);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("toasts.loadImagesFailed"));
    } finally {
      setIsLoading(false);
    }
  };

  const closeDialog = useCallback(() => {
    setDialogVisible(false);
    setTimeout(() => setDeleteTarget(null), 200);
  }, []);

  const openDeleteDialog = useCallback((item: ManagedImage) => {
    deleteTargetRef.current = item;
    setDeleteTarget(item);
    setDialogVisible(true);
  }, []);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      await deleteManagedImages({ paths: [deleteTarget.rel] });
      setItems((prev) => prev.filter((item) => item.rel !== deleteTarget.rel));
      setSelectedPaths((prev) => prev.filter((p) => p !== imageKey(deleteTarget)));
      toast.success(t("toasts.imageDeleted"));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("toasts.deleteFailed"));
    } finally {
      setIsDeleting(false);
      closeDialog();
    }
  };

  const handleSetTags = async (item: ManagedImage, tags: string[]) => {
    try {
      const result = await setImageTags(item.rel, tags);
      setItems((prev) => prev.map((i) => i.rel === item.rel ? { ...i, tags: result.tags } : i));
      const tagsData = await fetchImageTags();
      setAllTags(tagsData.tags);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("toasts.setTagsFailed"));
    }
  };

  const handleAddTag = (item: ManagedImage) => {
    const tag = tagInput.trim();
    if (!tag) return;
    const current = item.tags ?? [];
    if (current.includes(tag)) {
      toast.error(t("toasts.tagExists"));
      return;
    }
    void handleSetTags(item, [...current, tag]);
    setTagInput("");
  };

  const handleRemoveTag = (item: ManagedImage, tag: string) => {
    void handleSetTags(item, (item.tags ?? []).filter((t) => t !== tag));
  };

  const toggleFilterTag = (tag: string) => {
    setSelectedTags((prev) => prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]);
    setPage(1);
  };

  const [pressingTag, setPressingTag] = useState<string | null>(null);
  const pressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [tagDeleteTarget, setTagDeleteTarget] = useState<string | null>(null);

  const handleDeleteTag = async (tag: string) => {
    try {
      const result = await deleteImageTag(tag);
      setAllTags((prev) => prev.filter((t) => t !== tag));
      setSelectedTags((prev) => prev.filter((t) => t !== tag));
      setItems((prev) => prev.map((item) => ({
        ...item,
        tags: (item.tags ?? []).filter((t) => t !== tag),
      })));
      toast.success(t("toasts.tagDeleted", { tag, count: result.removed_from }));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("toasts.deleteTagFailed"));
    }
  };

  const startTagPress = useCallback((tag: string) => {
    setPressingTag(tag);
    pressTimerRef.current = setTimeout(() => {
      setPressingTag(null);
      setTagDeleteTarget(tag);
    }, LONG_PRESS_MS);
  }, []);

  const stopTagPress = useCallback(() => {
    setPressingTag(null);
    if (pressTimerRef.current) {
      clearTimeout(pressTimerRef.current);
      pressTimerRef.current = null;
    }
  }, []);

  const clearFilters = () => {
    setStartDate("");
    setEndDate("");
    setSelectedTags([]);
  };

  const togglePaths = (paths: string[], checked: boolean) => {
    setSelectedPaths((current) => checked ? Array.from(new Set([...current, ...paths])) : current.filter((path) => !paths.includes(path)));
  };

  const confirmDelete = async () => {
    if (!deleteMode || selectedCount === 0) return;
    setIsDeleting(true);
    try {
      const data = await deleteManagedImages(deleteMode === "filtered" ? { start_date: startDate, end_date: endDate, all_matching: true } : { paths: selectedPaths });
      toast.success(t("toasts.deleteSuccessCount", { count: data.removed }));
      setDeleteMode(null);
      setSelectedPaths([]);
      await loadImages();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("toasts.deleteImagesFailed"));
    } finally {
      setIsDeleting(false);
    }
  };

  const handleBatchDownload = async () => {
    const paths = deleteMode === "filtered" ? items.map((item) => item.rel) : selectedPaths;
    if (paths.length === 0) return;
    setIsDownloading(true);
    try {
      await downloadImages(paths);
      toast.success(t("toasts.downloadSuccessCount", { count: paths.length }));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("toasts.downloadFailed"));
    } finally {
      setIsDownloading(false);
    }
  };

  const handleSingleDownload = async (item: ManagedImage) => {
    await downloadSingleImage(item.rel);
  };

  useEffect(() => {
    void loadImages();
  }, [startDate, endDate]);

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <div className="text-xs font-semibold tracking-[0.18em] text-stone-500 uppercase">Images</div>
          <h1 className="text-2xl font-semibold tracking-tight">{tCommon("nav.imageManager")}</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <DateRangeFilter startDate={startDate} endDate={endDate} onChange={(start, end) => { setStartDate(start); setEndDate(end); }} />
          <Button variant="outline" onClick={clearFilters} className="h-10 rounded-xl border-stone-200 bg-white px-4 text-stone-700">
            {t("filters.clear")}
          </Button>
          <Button onClick={() => void loadImages()} disabled={isLoading} className="h-10 rounded-xl bg-stone-950 px-4 text-white hover:bg-stone-800">
            {isLoading ? <LoaderCircle className="size-4 animate-spin" /> : <Search className="size-4" />}
            {t("filters.search")}
          </Button>
          <Button variant="outline" onClick={() => setDeleteMode("filtered")} disabled={isDeleting || items.length === 0 || (!startDate && !endDate)} className="h-10 rounded-xl border-rose-200 bg-white px-4 text-rose-600 hover:bg-rose-50">
            <Trash2 className="size-4" />
            {t("filters.deleteMatchingDate")}
          </Button>
        </div>
      </div>

      {allTags.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-stone-500">
            <Tag className="mr-1 inline size-3.5" />
            {t("tagsFilter.label")}
          </span>
          {allTags.map((tag) => {
            const isPressing = pressingTag === tag;
            return (
              <span
                key={tag}
                className="relative inline-flex items-center"
                onMouseDown={() => startTagPress(tag)}
                onMouseUp={stopTagPress}
                onMouseLeave={stopTagPress}
                onTouchStart={() => startTagPress(tag)}
                onTouchEnd={stopTagPress}
              >
                <button
                  type="button"
                  onClick={() => toggleFilterTag(tag)}
                >
                  <Badge
                    variant={selectedTags.includes(tag) ? "default" : "outline"}
                    className={`cursor-pointer rounded-md transition-all hover:opacity-80 ${isPressing ? "ring-2 ring-red-400 ring-offset-1" : ""}`}
                  >
                    {tag}
                  </Badge>
                </button>
                {isPressing ? (
                  <span className="pointer-events-none absolute inset-0 overflow-hidden rounded-md">
                    <span className="absolute inset-0 animate-[grow_800ms_linear_forwards] rounded-md bg-red-400/20" />
                  </span>
                ) : null}
              </span>
            );
          })}
          {selectedTags.length > 0 ? (
            <button type="button" onClick={() => setSelectedTags([])}>
              <Badge variant="secondary" className="cursor-pointer rounded-md">
                <X className="mr-0.5 size-3" />
                {t("tagsFilter.clear")}
              </Badge>
            </button>
          ) : null}
        </div>
      ) : null}

      {/* Storage Stats Panel */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mb-4">
        {storage ? (
          <>
            <div className="rounded-xl border border-stone-200 bg-white/80 p-3">
              <div className="text-xs text-stone-500">{t("storage.diskTotal")}</div>
              <div className="text-lg font-bold text-stone-800">{storage.disk_total_mb >= 1024 ? `${(storage.disk_total_mb / 1024).toFixed(1)} GB` : `${storage.disk_total_mb} MB`}</div>
            </div>
            <div className="rounded-xl border border-stone-200 bg-white/80 p-3">
              <div className="text-xs text-stone-500">{t("storage.diskFree")}</div>
              <div className={`text-lg font-bold ${storage.disk_free_mb < 200 ? "text-red-500" : storage.disk_free_mb < 500 ? "text-yellow-500" : "text-green-600"}`}>{storage.disk_free_mb >= 1024 ? `${(storage.disk_free_mb / 1024).toFixed(1)} GB` : `${storage.disk_free_mb} MB`}</div>
            </div>
            <div className="rounded-xl border border-stone-200 bg-white/80 p-3">
              <div className="text-xs text-stone-500">{t("storage.imageCount")}</div>
              <div className="text-lg font-bold text-stone-800">{storage.image_count}</div>
            </div>
            <div className="rounded-xl border border-stone-200 bg-white/80 p-3">
              <div className="text-xs text-stone-500">{t("storage.imageSize")}</div>
              <div className="text-lg font-bold text-stone-800">{storage.image_size_mb >= 1024 ? `${(storage.image_size_mb / 1024).toFixed(1)} GB` : `${storage.image_size_mb} MB`}</div>
            </div>
            <div className="rounded-xl border border-stone-200 bg-white/80 p-3 col-span-2 flex items-center gap-2 flex-wrap">
              <span className="text-xs text-stone-500 w-full">{t("storage.quickActionsLabel")}</span>
              <Button size="sm" variant="outline" className="h-7 text-xs" disabled={storageLoading} onClick={() => { void loadStorage(); }}>
                <RefreshCw className={`size-3 mr-1 ${storageLoading ? "animate-spin" : ""}`} />{t("actions.refresh")}
              </Button>
              <Button size="sm" variant="outline" className="h-7 text-xs"
                onClick={async () => {
                  try { const r = await compressAllImages(); setCompressResult(t("storageActions.compressSuccess", { savedMb: r.saved_mb })); void loadStorage(); }
                  catch { setCompressResult(t("storageActions.compressFailed")); }
                }}>
                🗜️ {t("storageActions.compress")}
              </Button>
              <Button size="sm" variant="outline" className="h-7 text-xs border-rose-200 text-rose-600"
                onClick={() => setDeleteMode("byDate")}>
                🗑️ {t("storageActions.deleteByDate")}
              </Button>
              <form onSubmit={async (e) => { e.preventDefault();
                try {
                  const r = await deleteToTarget(targetFreeMb);
                  toast.success(t("storageActions.cleanupSuccess", { count: r.removed, freedMb: r.freed_mb ?? 0 }));
                  void loadStorage();
                } catch { toast.error(t("storageActions.cleanupFailed")); }
              }} className="flex items-center gap-1">
                <Button size="sm" variant="outline" className="h-7 text-xs border-amber-200 text-amber-700" type="submit">
                  🧹 {t("storageActions.cleanupTo")}
                </Button>
                <Input className="h-7 w-14 text-xs text-center px-1" type="number" min={50} value={targetFreeMb}
                  onChange={(e) => setTargetFreeMb(Number(e.target.value) || 500)} />
                <span className="text-xs text-stone-400">MB {t("storageActions.remainingUnit")}</span>
              </form>
              {compressResult ? <span className="text-xs text-green-600 ml-1">{compressResult}</span> : null}
            </div>
          </>
        ) : (
          <div className="rounded-xl border border-stone-200 bg-white/80 p-3 col-span-full text-center text-sm text-stone-400">
            {storageLoading ? t("storage.loading") : t("storage.loadFailed")}
          </div>
        )}
      </div>

      {/* Delete by date dialog */}
      <Dialog open={deleteMode === "byDate"} onOpenChange={() => setDeleteMode(null)}>
        <DialogContent className="sm:max-w-md rounded-2xl">
          <DialogHeader><DialogTitle>{t("byDateDialog.title")}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <label className="text-sm text-stone-600 shrink-0">{t("actions.delete")}</label>
              <Input className="h-9 text-sm" type="date" value={deleteStartDate} onChange={(e) => setDeleteStartDate(e.target.value)} />
              <span className="text-sm text-stone-400">{t("byDateDialog.beforeSuffix")}</span>
            </div>
            <p className="text-xs text-stone-500">{t("byDateDialog.warning")}</p>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteMode(null)}>{tCommon("canvasDialog.cancel")}</Button>
            <Button variant="destructive" disabled={!deleteStartDate || isDeleting}
              onClick={async () => {
                if (!deleteStartDate) return;
                try {
                  setIsDeleting(true);
                  const r = await deleteManagedImages({ end_date: deleteStartDate, all_matching: true });
                  toast.success(t("toasts.deleteSuccessCount", { count: r.removed }));
                  setDeleteMode(null);
                  void loadStorage();
                  void loadImages();
                } catch { toast.error(t("toasts.deleteFailed")); }
                finally { setIsDeleting(false); }
              }}>
              {isDeleting ? <LoaderCircle className="size-4 animate-spin" /> : null}
              {t("actions.confirmDelete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="p-0">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-100 px-5 py-4">
            <div className="flex flex-wrap items-center gap-3 text-sm text-stone-600">
              <ImageIcon className="size-4" />
              {t("toolbar.total", { total: filteredItems.length })}
              {selectedTags.length > 0 ? <span className="text-stone-400">{t("toolbar.filteredFrom", { total: items.length })}</span> : null}
              <label className="flex items-center gap-2">
                <Checkbox className={IMAGE_MANAGER_CHECKBOX_CLASS} checked={currentPageSelected} onCheckedChange={(checked) => togglePaths(currentRows.map(imageKey), Boolean(checked))} />
                {t("toolbar.selectPage")}
              </label>
              <label className="flex items-center gap-2">
                <Checkbox className={IMAGE_MANAGER_CHECKBOX_CLASS} checked={allSelected} onCheckedChange={(checked) => togglePaths(filteredItems.map(imageKey), Boolean(checked))} />
                {t("toolbar.selectAll")}
              </label>
              {selectedPaths.length > 0 ? <span>{t("toolbar.selected", { total: selectedPaths.length })}</span> : null}
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" className="h-8 rounded-lg px-3 text-stone-500" onClick={() => void loadImages()} disabled={isLoading}>
                <RefreshCw className={`size-4 ${isLoading ? "animate-spin" : ""}`} />
                {t("actions.refresh")}
              </Button>
              <button type="button" className="text-sm text-stone-500 hover:text-stone-900 disabled:text-stone-300" onClick={() => setSelectedPaths([])} disabled={selectedPaths.length === 0 || isDeleting}>
                {t("toolbar.clearSelection")}
              </button>
              <Button variant="outline" className="h-8 rounded-lg border-stone-200 bg-white px-3 text-stone-600 hover:bg-stone-50" onClick={() => void handleBatchDownload()} disabled={selectedPaths.length === 0 || isDownloading || isDeleting}>
                {isDownloading ? <LoaderCircle className="size-4 animate-spin" /> : <Download className="size-4" />}
                {t("toolbar.downloadSelected")}
              </Button>
              <Button variant="outline" className="h-8 rounded-lg border-rose-200 bg-white px-3 text-rose-600 hover:bg-rose-50" onClick={() => setDeleteMode("selected")} disabled={selectedPaths.length === 0 || isDeleting}>
                <Trash2 className="size-4" />
                {t("toolbar.deleteSelected")}
              </Button>
            </div>
          </div>
          <div className="grid gap-0 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {currentRows.map((item) => {
              const imageIndex = filteredItems.findIndex((row) => row.url === item.url);
              return (
              <div key={item.rel} className="group border-r border-b border-stone-100 p-4 transition hover:bg-stone-50 dark:hover:bg-white/5">
                <div className="relative">
                  <button
                    type="button"
                    className="relative block aspect-square w-full cursor-zoom-in overflow-hidden rounded-lg bg-stone-100 text-left"
                    onClick={() => {
                      setLightboxIndex(imageIndex);
                      setLightboxOpen(true);
                    }}
                  >
                    <img
                      src={item.thumbnail_url || item.url}
                      alt={item.name}
                      className="h-full w-full object-cover transition group-hover:scale-[1.02]"
                      onError={(event) => {
                        if (event.currentTarget.src !== item.url) {
                          event.currentTarget.src = item.url;
                        }
                      }}
                    />
                    <span className="absolute right-2 bottom-2 rounded-full bg-black/50 p-2 text-white opacity-100 transition sm:opacity-0 sm:group-hover:opacity-100">
                      <Maximize2 className="size-4" />
                    </span>
                  </button>
                  <button
                    type="button"
                    className="absolute top-2 right-2 z-10 inline-flex size-7 items-center justify-center rounded-full bg-black/50 text-white opacity-100 transition hover:bg-red-600 sm:opacity-0 sm:group-hover:opacity-100"
                    title={t("gallery.deleteImageTitle")}
                    onClick={(e) => {
                      e.stopPropagation();
                      openDeleteDialog(item);
                    }}
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
                <div className="mt-3 space-y-2 text-xs text-stone-500">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1 font-medium text-stone-700">
                      <CalendarDays className="size-3.5" />
                      {item.created_at}
                    </div>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8 rounded-lg text-stone-400 hover:bg-stone-100 hover:text-stone-700"
                        onClick={() => void handleSingleDownload(item)}
                        title={tCommon("imageLightbox.download")}
                      >
                        <Download className="size-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8 rounded-lg text-stone-400 hover:bg-stone-100 hover:text-stone-700"
                        onClick={() => {
                          void navigator.clipboard.writeText(item.url);
                          toast.success(t("gallery.urlCopied"));
                        }}
                      >
                        <Copy className="size-4" />
                      </Button>
                      <Checkbox className={IMAGE_MANAGER_CHECKBOX_CLASS} checked={selectedSet.has(imageKey(item))} onCheckedChange={(checked) => togglePaths([imageKey(item)], Boolean(checked))} />
                    </div>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span>{formatSize(item.size)}</span>
                    <span>{item.width && item.height ? `${item.width} x ${item.height}` : "-"}</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-1">
                    {(item.tags ?? []).map((tag) => (
                      <Badge key={tag} variant="secondary" className="gap-0.5 rounded-md py-0 pr-0.5 text-[10px]">
                        {tag}
                        <button
                          type="button"
                          className="inline-flex size-3.5 items-center justify-center rounded-full hover:bg-stone-300"
                          onClick={() => handleRemoveTag(item, tag)}
                        >
                          <X className="size-2.5" />
                        </button>
                      </Badge>
                    ))}
                    <Popover open={tagEditTarget?.rel === item.rel} onOpenChange={(open) => { setTagEditTarget(open ? item : null); setTagInput(""); }}>
                      <PopoverTrigger asChild>
                        <button
                          type="button"
                          className="inline-flex size-5 items-center justify-center rounded-full border border-dashed border-stone-300 text-stone-400 hover:border-stone-500 hover:text-stone-600"
                          title={t("gallery.addTag")}
                        >
                          <Plus className="size-3" />
                        </button>
                      </PopoverTrigger>
                      <PopoverContent align="start" className="w-56 p-2">
                        <div className="space-y-2">
                          <div className="text-xs font-medium text-stone-500">{t("gallery.addTag")}</div>
                          <div className="flex gap-1">
                            <Input
                              value={tagInput}
                              onChange={(e) => setTagInput(e.target.value)}
                              placeholder={t("gallery.tagNamePlaceholder")}
                              className="h-8 text-xs"
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  e.preventDefault();
                                  handleAddTag(item);
                                }
                              }}
                            />
                            <Button
                              size="icon"
                              variant="outline"
                              className="size-8 shrink-0"
                              onClick={() => handleAddTag(item)}
                            >
                              <Plus className="size-3.5" />
                            </Button>
                          </div>
                          {allTags.filter((t) => !(item.tags ?? []).includes(t)).length > 0 ? (
                            <div className="flex flex-wrap gap-1 border-t border-stone-100 pt-2">
                              {allTags.filter((t) => !(item.tags ?? []).includes(t)).map((tag) => (
                                <button
                                  key={tag}
                                  type="button"
                                  onClick={() => {
                                    void handleSetTags(item, [...(item.tags ?? []), tag]);
                                    setTagEditTarget(null);
                                  }}
                                >
                                  <Badge variant="outline" className="cursor-pointer rounded-md text-[10px] hover:bg-stone-100">
                                    {tag}
                                  </Badge>
                                </button>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      </PopoverContent>
                    </Popover>
                  </div>
                </div>
              </div>
            )})}
          </div>
          <div className="flex items-center justify-end gap-2 border-t border-stone-100 px-4 py-3 text-sm text-stone-500">
            <span>{t("pagination.info", { page: safePage, pageCount, total: filteredItems.length })}</span>
            <Button variant="outline" size="icon" className="size-9 rounded-lg border-stone-200 bg-white" disabled={safePage <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>
              <ChevronLeft className="size-4" />
            </Button>
            <Button variant="outline" size="icon" className="size-9 rounded-lg border-stone-200 bg-white" disabled={safePage >= pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))}>
              <ChevronRight className="size-4" />
            </Button>
          </div>
          {!isLoading && filteredItems.length === 0 ? <div className="px-6 py-14 text-center text-sm text-stone-500">{t("empty.noImages")}</div> : null}
        </CardContent>
      </Card>

      <Dialog open={dialogVisible} onOpenChange={(open) => { if (!open) closeDialog(); }}>
        <DialogContent className="max-w-sm overflow-hidden rounded-2xl">
          <DialogHeader>
            <DialogTitle className="pr-8">{t("actions.confirmDelete")}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-stone-600">
            {t("deleteDialog.description")}
          </p>
          {deleteTarget ? (
            <div className="flex items-center gap-3 overflow-hidden rounded-xl border border-stone-200 bg-stone-50 p-3">
              <img
                src={deleteTarget.thumbnail_url || deleteTarget.url}
                alt=""
                className="size-16 shrink-0 rounded-lg object-cover"
                onError={(e) => { if (e.currentTarget.src !== deleteTarget.url) e.currentTarget.src = deleteTarget.url; }}
              />
              <div className="min-w-0 overflow-hidden text-xs text-stone-500">
                <div className="truncate font-medium text-stone-700">{deleteTarget.name}</div>
                <div className="truncate">{deleteTarget.created_at}</div>
                <div>{formatSize(deleteTarget.size)}</div>
              </div>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={closeDialog} className="rounded-xl">
              {tCommon("canvasDialog.cancel")}
            </Button>
            <Button variant="destructive" onClick={() => void handleDelete()} disabled={isDeleting} className="rounded-xl">
              {isDeleting ? <LoaderCircle className="mr-1 size-4 animate-spin" /> : <Trash2 className="mr-1 size-4" />}
              {t("actions.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ImageLightbox
        images={lightboxImages}
        currentIndex={lightboxIndex}
        open={lightboxOpen}
        onOpenChange={setLightboxOpen}
        onIndexChange={setLightboxIndex}
      />
      <Dialog open={deleteMode === "selected" || deleteMode === "filtered"} onOpenChange={(open) => (!open ? setDeleteMode(null) : null)}>
        <DialogContent showCloseButton={false} className="rounded-2xl p-6">
          <DialogHeader className="gap-2">
            <DialogTitle>{deleteMode === "filtered" ? t("bulkDeleteDialog.titleFiltered") : t("bulkDeleteDialog.titleSelected")}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-stone-600">
            {t("bulkDeleteDialog.description", { count: selectedCount })}
          </p>
          <DialogFooter>
            <Button variant="outline" className="rounded-xl" onClick={() => setDeleteMode(null)} disabled={isDeleting}>
              {tCommon("canvasDialog.cancel")}
            </Button>
            <Button className="rounded-xl bg-rose-600 text-white hover:bg-rose-700" onClick={() => void confirmDelete()} disabled={isDeleting || selectedCount === 0}>
              {isDeleting ? <LoaderCircle className="size-4 animate-spin" /> : null}
              {t("actions.confirmDelete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={Boolean(tagDeleteTarget)} onOpenChange={(open) => { if (!open) setTagDeleteTarget(null); }}>
        <DialogContent className="max-w-sm rounded-2xl">
          <DialogHeader>
            <DialogTitle>{t("tagDeleteDialog.title")}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-stone-600">
            {t("tagDeleteDialog.descriptionBefore")} <span className="font-semibold">"{tagDeleteTarget}"</span> {t("tagDeleteDialog.descriptionAfter")}
          </p>
          <DialogFooter>
            <Button variant="outline" className="rounded-xl" onClick={() => setTagDeleteTarget(null)}>
              {tCommon("canvasDialog.cancel")}
            </Button>
            <Button
              variant="destructive"
              className="rounded-xl"
              onClick={() => {
                if (tagDeleteTarget) void handleDeleteTag(tagDeleteTarget);
                setTagDeleteTarget(null);
              }}
            >
              {t("actions.confirmDelete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}

export default function ImageManagerPage() {
  const { isCheckingAuth, session } = useAuthGuard(["admin"]);
  if (isCheckingAuth || !session || session.role !== "admin") {
    return <div className="flex min-h-[40vh] items-center justify-center"><LoaderCircle className="size-5 animate-spin text-stone-400" /></div>;
  }
  return <ImageManagerContent />;
}
