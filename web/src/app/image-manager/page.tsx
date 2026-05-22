"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, Copy, Download, ImageIcon, LoaderCircle, Maximize2, Plus, RefreshCw, Search, Tag, Trash2, X } from "lucide-react";
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
import { deleteImageTag, deleteManagedImages, downloadImages, downloadSingleImage, fetchImageTags, fetchManagedImages, setImageTags, type ManagedImage } from "@/lib/api";
import { useAuthGuard } from "@/lib/use-auth-guard";

const LONG_PRESS_MS = 800;

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
  const [items, setItems] = useState<ManagedImage[]>([]);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [lightboxIndex, setLightboxIndex] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<ManagedImage | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [allTags, setAllTags] = useState<string[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagEditTarget, setTagEditTarget] = useState<ManagedImage | null>(null);
  const [tagInput, setTagInput] = useState("");
  const [dialogVisible, setDialogVisible] = useState(false);
  const deleteTargetRef = useRef<ManagedImage | null>(null);
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [deleteMode, setDeleteMode] = useState<"selected" | "filtered" | null>(null);
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
  const selectedCount = deleteMode === "filtered" ? items.length : selectedPaths.length;
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
      toast.error(error instanceof Error ? error.message : "Không tải được ảnh");
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
      toast.success("Đã xóa ảnh");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Không xóa được");
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
      toast.error(error instanceof Error ? error.message : "Không đặt được nhãn");
    }
  };

  const handleAddTag = (item: ManagedImage) => {
    const tag = tagInput.trim();
    if (!tag) return;
    const current = item.tags ?? [];
    if (current.includes(tag)) {
      toast.error("Nhãn đã tồn tại");
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
      toast.success(`nhãn"${tag}"đã xóa，影响 ${result.removed_from}  ảnh`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Không xóa được nhãn");
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
      toast.success(`đã xóa ${data.removed}  ảnh`);
      setDeleteMode(null);
      setSelectedPaths([]);
      await loadImages();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Không xóa được ảnh");
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
      toast.success(`đã tải ${paths.length}  ảnh`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Tải thất bại");
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
          <h1 className="text-2xl font-semibold tracking-tight">Quản lý ảnh</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <DateRangeFilter startDate={startDate} endDate={endDate} onChange={(start, end) => { setStartDate(start); setEndDate(end); }} />
          <Button variant="outline" onClick={clearFilters} className="h-10 rounded-xl border-stone-200 bg-white px-4 text-stone-700">
            Xóa bộ lọc
          </Button>
          <Button onClick={() => void loadImages()} disabled={isLoading} className="h-10 rounded-xl bg-stone-900 px-4 text-white hover:bg-stone-800">
            {isLoading ? <LoaderCircle className="size-4 animate-spin" /> : <Search className="size-4" />}
            Tìm kiếm
          </Button>
          <Button variant="outline" onClick={() => setDeleteMode("filtered")} disabled={isDeleting || items.length === 0 || (!startDate && !endDate)} className="h-10 rounded-xl border-rose-200 bg-white px-4 text-rose-600 hover:bg-rose-50">
            <Trash2 className="size-4" />
            Xóa theo ngày
          </Button>
        </div>
      </div>

      {allTags.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-stone-500">
            <Tag className="mr-1 inline size-3.5" />
            Lọc nhãn：
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
                Xóa
              </Badge>
            </button>
          ) : null}
        </div>
      ) : null}

      <Card className="rounded-2xl border-stone-200 bg-white/90 shadow-sm">
        <CardContent className="p-0">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-200 px-5 py-4">
            <div className="flex flex-wrap items-center gap-3 text-sm text-stone-600">
              <ImageIcon className="size-4" />
              共 {filteredItems.length} 
              {selectedTags.length > 0 ? <span className="text-stone-500">（lọc từ {items.length} ）</span> : null}
              <label className="flex items-center gap-2">
                <Checkbox checked={currentPageSelected} onCheckedChange={(checked) => togglePaths(currentRows.map(imageKey), Boolean(checked))} />
                Chọn cả trang
              </label>
              <label className="flex items-center gap-2">
                <Checkbox checked={allSelected} onCheckedChange={(checked) => togglePaths(filteredItems.map(imageKey), Boolean(checked))} />
                Chọn tất cả
              </label>
              {selectedPaths.length > 0 ? <span>Đã chọn {selectedPaths.length} </span> : null}
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" className="h-8 rounded-lg px-3 text-stone-500" onClick={() => void loadImages()} disabled={isLoading}>
                <RefreshCw className={`size-4 ${isLoading ? "animate-spin" : ""}`} />
                刷新
              </Button>
              <button type="button" className="text-sm text-stone-500 hover:text-stone-900 disabled:text-stone-700" onClick={() => setSelectedPaths([])} disabled={selectedPaths.length === 0 || isDeleting}>
                Bỏ chọn
              </button>
              <Button variant="outline" className="h-8 rounded-lg border-stone-200 bg-white px-3 text-stone-600 hover:bg-stone-800" onClick={() => void handleBatchDownload()} disabled={selectedPaths.length === 0 || isDownloading || isDeleting}>
                {isDownloading ? <LoaderCircle className="size-4 animate-spin" /> : <Download className="size-4" />}
                Tải đã chọn
              </Button>
              <Button variant="outline" className="h-8 rounded-lg border-rose-200 bg-white px-3 text-rose-600 hover:bg-rose-50" onClick={() => setDeleteMode("selected")} disabled={selectedPaths.length === 0 || isDeleting}>
                <Trash2 className="size-4" />
                Xóa đã chọn
              </Button>
            </div>
          </div>
          <div className="grid gap-0 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {currentRows.map((item) => {
              const imageIndex = filteredItems.findIndex((row) => row.url === item.url);
              return (
              <div key={item.rel} className="group border-r border-b border-stone-200 p-4 transition hover:bg-stone-800">
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
                    title="Xóa ảnh"
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
                        className="size-8 rounded-lg text-stone-500 hover:bg-stone-200 hover:text-stone-700"
                        onClick={() => void handleSingleDownload(item)}
                        title="Tải ảnh"
                      >
                        <Download className="size-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8 rounded-lg text-stone-500 hover:bg-stone-200 hover:text-stone-700"
                        onClick={() => {
                          void navigator.clipboard.writeText(item.url);
                          toast.success("Đã sao chép địa chỉ ảnh");
                        }}
                      >
                        <Copy className="size-4" />
                      </Button>
                      <Checkbox checked={selectedSet.has(imageKey(item))} onCheckedChange={(checked) => togglePaths([imageKey(item)], Boolean(checked))} />
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
                          className="inline-flex size-5 items-center justify-center rounded-full border border-dashed border-stone-300 text-stone-500 hover:border-stone-500 hover:text-stone-600"
                          title="thêmnhãn"
                        >
                          <Plus className="size-3" />
                        </button>
                      </PopoverTrigger>
                      <PopoverContent align="start" className="w-56 p-2">
                        <div className="space-y-2">
                          <div className="text-xs font-medium text-stone-500">thêmnhãn</div>
                          <div className="flex gap-1">
                            <Input
                              value={tagInput}
                              onChange={(e) => setTagInput(e.target.value)}
                              placeholder="Nhập tên nhãn"
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
                            <div className="flex flex-wrap gap-1 border-t border-stone-200 pt-2">
                              {allTags.filter((t) => !(item.tags ?? []).includes(t)).map((tag) => (
                                <button
                                  key={tag}
                                  type="button"
                                  onClick={() => {
                                    void handleSetTags(item, [...(item.tags ?? []), tag]);
                                    setTagEditTarget(null);
                                  }}
                                >
                                  <Badge variant="outline" className="cursor-pointer rounded-md text-[10px] hover:bg-stone-200">
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
          <div className="flex items-center justify-end gap-2 border-t border-stone-200 px-4 py-3 text-sm text-stone-500">
            <span>第 {safePage} / {pageCount} 页，共 {filteredItems.length} </span>
            <Button variant="outline" size="icon" className="size-9 rounded-lg border-stone-200 bg-white" disabled={safePage <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>
              <ChevronLeft className="size-4" />
            </Button>
            <Button variant="outline" size="icon" className="size-9 rounded-lg border-stone-200 bg-white" disabled={safePage >= pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))}>
              <ChevronRight className="size-4" />
            </Button>
          </div>
          {!isLoading && filteredItems.length === 0 ? <div className="px-6 py-14 text-center text-sm text-stone-500">Không tìm thấy ảnh nào</div> : null}
        </CardContent>
      </Card>

      <Dialog open={dialogVisible} onOpenChange={(open) => { if (!open) closeDialog(); }}>
        <DialogContent className="max-w-sm overflow-hidden rounded-2xl">
          <DialogHeader>
            <DialogTitle className="pr-8">Xác nhận xóa</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-stone-600">
            Xác nhận xóa ảnh này? Thao tác này không thể hoàn tác.
          </p>
          {deleteTarget ? (
            <div className="flex items-center gap-3 overflow-hidden rounded-xl border border-stone-200 bg-stone-100 p-3">
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
              Hủy
            </Button>
            <Button variant="destructive" onClick={() => void handleDelete()} disabled={isDeleting} className="rounded-xl">
              {isDeleting ? <LoaderCircle className="mr-1 size-4 animate-spin" /> : <Trash2 className="mr-1 size-4" />}
              Xóa
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
      <Dialog open={Boolean(deleteMode)} onOpenChange={(open) => (!open ? setDeleteMode(null) : null)}>
        <DialogContent showCloseButton={false} className="rounded-2xl p-6">
          <DialogHeader className="gap-2">
            <DialogTitle>{deleteMode === "filtered" ? "Xóa ảnh theo ngày" : "Xóa ảnh đã chọn"}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-stone-600">
            Xác nhận xóa {selectedCount}   ảnh？Xóakhông thể hoàn tác。
          </p>
          <DialogFooter>
            <Button variant="outline" className="rounded-xl" onClick={() => setDeleteMode(null)} disabled={isDeleting}>
              Hủy
            </Button>
            <Button className="rounded-xl bg-rose-600 text-white hover:bg-rose-700" onClick={() => void confirmDelete()} disabled={isDeleting || selectedCount === 0}>
              {isDeleting ? <LoaderCircle className="size-4 animate-spin" /> : null}
              Xác nhận xóa
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={Boolean(tagDeleteTarget)} onOpenChange={(open) => { if (!open) setTagDeleteTarget(null); }}>
        <DialogContent className="max-w-sm rounded-2xl">
          <DialogHeader>
            <DialogTitle>Xóanhãn</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-stone-600">
            确定要Xóanhãn <span className="font-semibold">"{tagDeleteTarget}"</span>? Nhãn sẽ bị xóa khỏi tất cả ảnh.
          </p>
          <DialogFooter>
            <Button variant="outline" className="rounded-xl" onClick={() => setTagDeleteTarget(null)}>
              Hủy
            </Button>
            <Button
              variant="destructive"
              className="rounded-xl"
              onClick={() => {
                if (tagDeleteTarget) void handleDeleteTag(tagDeleteTarget);
                setTagDeleteTarget(null);
              }}
            >
              Xác nhận xóa
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
    return <div className="flex min-h-[40vh] items-center justify-center"><LoaderCircle className="size-5 animate-spin text-stone-500" /></div>;
  }
  return <ImageManagerContent />;
}
