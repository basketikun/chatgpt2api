"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { AlertCircle, CheckCircle2, Clock3, FileArchive, FileText, History, ImagePlus, LoaderCircle, Pencil, Play, Plus, RefreshCw, Trash2, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n";
import { httpRequest } from "@/lib/request";
import { cn } from "@/lib/utils";
import {
  listDeletedEditableFileIds,
  listEditableFileDrafts,
  saveDeletedEditableFileIds,
  saveEditableFileDrafts,
  type EditableFileDraft,
} from "@/store/editable-file-history";

import type { EditableFileTask } from "./types";

type Props = {
  title: string;
  kind: "ppt" | "psd";
  endpoint: string;
  defaultPrompt: string;
  imageRequired?: boolean;
};

const MAX_HISTORY = 20;
const DRAFT_ID = "__draft__";
const taskIdOf = (task: EditableFileTask | null | undefined) => task?.taskId || task?.id || "";
const isRunning = (task: EditableFileTask | null | undefined) => task?.status === "queued" || task?.status === "running";
const statusClass = (status: string) => status === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/20 dark:text-emerald-300" : status === "error" ? "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-300" : "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-300";
const formatElapsed = (seconds: number) => `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
const titleOfPrompt = (prompt: string, fallback: string) => prompt.trim().replace(/\s+/g, " ").slice(0, 24) || fallback;
const createClientTaskId = () => `${Date.now()}-${Math.random().toString(16).slice(2)}`;

const readFile = (file: File) => new Promise<string>((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result || ""));
  reader.onerror = () => reject(reader.error);
  reader.readAsDataURL(file);
});

const mergeTasks = (current: EditableFileTask[], updates: EditableFileTask[]) => {
  const next = [...current];
  for (const update of updates) {
    const id = taskIdOf(update);
    if (!id) continue;
    const index = next.findIndex((item) => taskIdOf(item) === id);
    const merged = { ...(index >= 0 ? next[index] : {}), ...update, polled_at: Date.now() };
    if (index >= 0) next[index] = merged;
    else next.unshift(merged);
  }
  return next.slice(0, MAX_HISTORY);
};

const removeTasks = (current: EditableFileTask[], ids: string[]) => {
  const missing = new Set(ids);
  return missing.size ? current.filter((task) => !missing.has(taskIdOf(task))) : current;
};

const fileNameOf = (url: string) => {
  try {
    return decodeURIComponent(new URL(url).pathname.split("/").pop() || "");
  } catch {
    return decodeURIComponent(url.split("/").pop() || "");
  }
};

function ResultFile({ href, icon, label, downloadText }: { href?: string; icon: ReactNode; label: string; downloadText: string }) {
  if (!href) return null;
  return (
    <div className="flex items-center gap-3 rounded-md border border-stone-200 bg-stone-50/80 px-3 py-3 dark:border-white/10 dark:bg-white/[0.04]">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-white text-stone-700 shadow-sm dark:bg-white/10 dark:text-stone-200">
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-stone-950 dark:text-stone-50">{label}</div>
        <div className="truncate text-xs text-stone-500 dark:text-stone-400">{fileNameOf(href)}</div>
      </div>
      <Button size="sm" asChild>
        <a href={href} target="_blank" rel="noreferrer">{downloadText}</a>
      </Button>
    </div>
  );
}

export function EditableFilePanel({ title, kind, endpoint, defaultPrompt, imageRequired }: Props) {
  const { t, locale } = useI18n();
  const isFa = locale === "fa";
  const isAr = locale === "ar";
  const isZh = locale === "zh";

  const statusText = (status: string) => {
    const map: Record<string, string> = {
      queued: isFa ? "در صف" : isAr ? "في الانتظار" : isZh ? "排队中" : "Queued",
      running: isFa ? "در حال پردازش" : isAr ? "جارٍ المعالجة" : isZh ? "生成中" : "Running",
      success: isFa ? "تکمیل شده" : isAr ? "مكتمل" : isZh ? "已完成" : "Success",
      error: isFa ? "ناموفق" : isAr ? "فشل" : isZh ? "失败" : "Failed",
    };
    return map[status] || status;
  };

  const [prompt, setPrompt] = useState(defaultPrompt);
  const [images, setImages] = useState<string[]>([]);
  const [tasks, setTasks] = useState<EditableFileTask[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState("");
  const [drafts, setDrafts] = useState<Record<string, EditableFileDraft>>({});
  const [renamingId, setRenamingId] = useState("");
  const [renamingTitle, setRenamingTitle] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState<{ type: "one" | "all"; id?: string; ids?: string[] } | null>(null);

  useEffect(() => {
    setDrafts(listEditableFileDrafts());
  }, []);

  const visibleTasks = useMemo(() => {
    const deleted = new Set(listDeletedEditableFileIds());
    return tasks.filter((task) => !deleted.has(taskIdOf(task)) && task.kind === kind);
  }, [tasks, kind]);

  const selectedTask = useMemo(() => {
    return visibleTasks.find((task) => taskIdOf(task) === selectedId) || null;
  }, [visibleTasks, selectedId]);

  const running = useMemo(() => isRunning(selectedTask), [selectedTask]);

  const elapsedOf = (task: EditableFileTask | null | undefined) => {
    if (!task) return 0;
    if (task.duration_ms) return Math.floor(task.duration_ms / 1000);
    const start = task.created_at ? new Date(task.created_at).getTime() : 0;
    if (!start) return 0;
    const end = task.status === "running" || task.status === "queued" ? Date.now() : (task.polled_at || Date.now());
    return Math.max(0, Math.floor((end - start) / 1000));
  };

  const fetchTasks = useCallback(async (ids?: string[]) => {
    setPolling(true);
    try {
      const url = ids?.length ? `/v1/editable-file-tasks?ids=${ids.join(",")}` : "/v1/editable-file-tasks";
      const data = await httpRequest<{ items: EditableFileTask[]; missing_ids?: string[] }>(url);
      setTasks((current) => {
        const merged = mergeTasks(current, data.items || []);
        return data.missing_ids?.length ? removeTasks(merged, data.missing_ids) : merged;
      });
    } catch {
      // ignore
    } finally {
      setPolling(false);
    }
  }, []);

  useEffect(() => {
    void fetchTasks();
  }, [fetchTasks]);

  useEffect(() => {
    const runningIds = visibleTasks.filter(isRunning).map(taskIdOf).filter(Boolean);
    if (!runningIds.length) return;
    const timer = setInterval(() => void fetchTasks(runningIds), 3000);
    return () => clearInterval(timer);
  }, [visibleTasks, fetchTasks]);

  const appendFiles = async (fileList: FileList | null) => {
    if (!fileList) return;
    const nextImages: string[] = [];
    for (let i = 0; i < fileList.length; i += 1) {
      try {
        nextImages.push(await readFile(fileList[i]));
      } catch {
        // ignore
      }
    }
    setImages((current) => [...current, ...nextImages]);
  };

  const createDraft = () => {
    setSelectedId(DRAFT_ID);
    setPrompt(defaultPrompt);
    setImages([]);
    setError("");
  };

  const renameTask = (id: string, newTitle: string) => {
    const trimmed = newTitle.trim();
    if (!trimmed) return;
    const nextDrafts = { ...drafts, [id]: { ...(drafts[id] || {}), title: trimmed } };
    setDrafts(nextDrafts);
    saveEditableFileDrafts(nextDrafts);
  };

  const confirmDelete = () => {
    if (!deleteConfirm) return;
    const deleted = new Set(listDeletedEditableFileIds());
    if (deleteConfirm.type === "all") {
      deleteConfirm.ids?.forEach((id) => deleted.add(id));
      if (deleteConfirm.ids?.includes(selectedId)) setSelectedId("");
    } else if (deleteConfirm.id) {
      deleted.add(deleteConfirm.id);
      if (selectedId === deleteConfirm.id) setSelectedId("");
    }
    saveDeletedEditableFileIds(Array.from(deleted));
    setDeleteConfirm(null);
  };

  const submit = async () => {
    const trimmed = prompt.trim();
    if (imageRequired && !images.length) {
      setError(isFa ? "لطفاً حداقل یک تصویر مرجع اضافه کنید" : isAr ? "يرجى إضافة صورة مرجعية واحدة على الأقل" : isZh ? "请至少添加一张参考图" : "Please provide at least one reference image");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const clientTaskId = createClientTaskId();
      const res = await httpRequest<EditableFileTask>(endpoint, {
        method: "POST",
        body: { prompt: trimmed, base64_images: images, client_task_id: clientTaskId },
      });
      const id = taskIdOf(res);
      const nextDrafts = { ...drafts, [id]: { prompt: trimmed, images, title: titleOfPrompt(trimmed, `${kind.toUpperCase()} ${isFa ? "تسک" : isAr ? "مهمة" : isZh ? "任务" : "Task"}`) } };
      setDrafts(nextDrafts);
      saveEditableFileDrafts(nextDrafts);
      setTasks((current) => mergeTasks(current, [res]));
      setSelectedId(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const refreshAll = () => void fetchTasks();
  const selectTask = (id: string) => {
    setRenamingId("");
    setSelectedId(id);
    const draft = drafts[id];
    const task = visibleTasks.find((item) => taskIdOf(item) === id);
    setPrompt(draft?.prompt || task?.prompt_preview || defaultPrompt);
    setImages(Array.isArray(draft?.images) ? draft.images : []);
  };
  const startRename = (id: string) => {
    setRenamingId(id);
    setRenamingTitle(drafts[id]?.title || titleOfPrompt(drafts[id]?.prompt || "", `${kind.toUpperCase()} ${isFa ? "تسک" : isAr ? "مهمة" : isZh ? "任务" : "Task"}`));
  };
  const commitRename = () => {
    renameTask(renamingId, renamingTitle);
    setRenamingId("");
    setRenamingTitle("");
  };

  const downloadText = isFa ? "دانلود" : isAr ? "تنزيل" : isZh ? "下载" : "Download";

  return (
    <>
    <div className="grid h-full min-h-[calc(100vh-148px)] overflow-hidden rounded-lg border border-stone-200 bg-white shadow-sm dark:border-white/10 dark:bg-stone-950 lg:grid-cols-[288px_420px_minmax(0,1fr)]">
      <aside className="flex min-h-0 flex-col border-b border-stone-200 bg-stone-50/70 dark:border-white/10 dark:bg-white/[0.02] lg:border-r lg:border-b-0">
        <div className="flex h-14 items-center justify-between border-b border-stone-200 px-4 dark:border-white/10">
          <div className="flex items-center gap-2 text-sm font-semibold text-stone-950 dark:text-stone-50">
            <History className="size-4" />
            {isFa ? "تاریخچه" : isAr ? "السجل" : isZh ? "历史记录" : "History"}
          </div>
          <div className="flex gap-1">
            <Button size="sm" variant="ghost" onClick={createDraft}>
              <Plus />
            </Button>
            <Button size="sm" variant="ghost" onClick={refreshAll} disabled={polling}>
              {polling ? <LoaderCircle className="animate-spin" /> : <RefreshCw />}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setDeleteConfirm({ type: "all", ids: tasks.filter((task) => task.kind === kind).map(taskIdOf).filter(Boolean) })} disabled={!visibleTasks.length}>
              <Trash2 />
            </Button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-2">
          {visibleTasks.length ? visibleTasks.map((task) => {
            const id = taskIdOf(task);
            const taskTitle = drafts[id]?.title || titleOfPrompt(task.prompt_preview || drafts[id]?.prompt || "", task.kind?.toUpperCase() || title);
            return (
              <div key={id} className={cn("group mb-2 rounded-md border px-3 py-2.5 transition", selectedId === id ? "border-stone-950 bg-white shadow-sm dark:border-white/60 dark:bg-white/10" : "border-transparent bg-transparent hover:border-stone-200 hover:bg-white dark:hover:border-white/10 dark:hover:bg-white/[0.05]")}>
                <div className="flex items-start gap-2">
                  <button type="button" onClick={() => selectTask(id)} className="min-w-0 flex-1 text-start">
                    <div className="flex min-w-0 items-center justify-between gap-2">
                      {renamingId === id ? (
                        <input
                          value={renamingTitle}
                          onChange={(event) => setRenamingTitle(event.target.value)}
                          onBlur={commitRename}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") commitRename();
                            if (event.key === "Escape") setRenamingId("");
                          }}
                          onClick={(event) => event.stopPropagation()}
                          className="min-w-0 flex-1 rounded border border-stone-300 bg-white px-2 py-1 text-sm font-semibold outline-none focus:border-stone-500 dark:border-white/15 dark:bg-stone-950"
                          autoFocus
                        />
                      ) : (
                        <span className="truncate text-sm font-semibold text-stone-950 dark:text-stone-50">{taskTitle}</span>
                      )}
                      <span className={cn("shrink-0 rounded-full border px-2 py-0.5 text-[11px]", statusClass(task.status))}>{statusText(task.status)}</span>
                    </div>
                    <div className="mt-2 flex items-center gap-2 text-xs text-stone-500 dark:text-stone-400">
                      <Clock3 className="size-3.5" />
                      <span className="tabular-nums">{formatElapsed(elapsedOf(task))}</span>
                      <span className="truncate">{task.created_at || id}</span>
                    </div>
                    {(task.prompt_preview || drafts[id]?.prompt) ? <div className="mt-2 line-clamp-2 text-xs leading-5 text-stone-500 dark:text-stone-400">{task.prompt_preview || drafts[id]?.prompt}</div> : null}
                  </button>
                  <div className="flex shrink-0 opacity-100 sm:opacity-0 sm:transition sm:group-hover:opacity-100">
                    <Button size="sm" variant="ghost" onClick={() => startRename(id)} className="size-7 px-0">
                      <Pencil className="size-3.5" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setDeleteConfirm({ type: "one", id })} className="size-7 px-0 text-stone-400 hover:text-rose-500">
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </div>
              </div>
            );
          }) : (
            <div className="flex h-full items-center justify-center text-sm text-stone-400 dark:text-stone-500">{isFa ? "بدون سابقه" : isAr ? "لا توجد سجلات" : isZh ? "暂无记录" : "No records"}</div>
          )}
        </div>
      </aside>

      <section className="flex min-h-0 flex-col border-b border-stone-200 dark:border-white/10 lg:border-r lg:border-b-0">
        <div className="flex h-14 items-center justify-between border-b border-stone-200 px-5 dark:border-white/10">
          <h2 className="text-sm font-semibold text-stone-950 dark:text-stone-50">{title}</h2>
          <Button size="sm" onClick={() => void submit()} disabled={submitting || running}>
            {submitting ? <LoaderCircle className="animate-spin" /> : <Play />}
            {isFa ? "تولید" : isAr ? "توليد" : isZh ? "生成" : "Generate"}
          </Button>
        </div>
        <div className="min-h-0 flex-1 space-y-5 overflow-auto p-5">
          <div className="space-y-2">
            <Label htmlFor={`${endpoint}-prompt`} className="text-xs font-semibold text-stone-700 dark:text-stone-300">{isFa ? "توضیحات و نیازمندی‌ها" : isAr ? "الوصف والمتطلبات" : isZh ? "需求" : "Requirements"}</Label>
            <Textarea id={`${endpoint}-prompt`} value={prompt} onChange={(event) => setPrompt(event.target.value)} className="min-h-56 rounded-md border-stone-200 bg-white text-sm leading-6 shadow-none dark:border-white/10 dark:bg-white/[0.03]" />
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-semibold text-stone-700 dark:text-stone-300">{isFa ? "تصاویر مرجع" : isAr ? "الصور المرجعية" : isZh ? "参考图" : "Reference Images"}</Label>
              <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-500 dark:bg-white/10 dark:text-stone-400">{images.length}</span>
            </div>
            <label className="group flex h-24 cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed border-stone-300 bg-stone-50 text-sm font-medium text-stone-600 transition hover:border-stone-950 hover:bg-white dark:border-white/15 dark:bg-white/[0.03] dark:text-stone-300 dark:hover:border-white/50">
              <ImagePlus className="size-4 transition group-hover:scale-110" />
              {isFa ? "آپلود تصویر" : isAr ? "رفع صورة" : isZh ? "上传图片" : "Upload Image"}
              <Input type="file" accept="image/*" multiple onChange={(event) => void appendFiles(event.target.files)} className="hidden" />
            </label>
            {images.length ? (
              <div className="grid grid-cols-4 gap-2">
                {images.slice(0, 8).map((src, index) => (
                  <img key={`${src.slice(0, 28)}-${index}`} src={src} alt="" className="aspect-square rounded-md border border-stone-200 object-cover dark:border-white/10" />
                ))}
              </div>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => setImages([])}>
              <Trash2 />
              {isFa ? "پاک کردن تصاویر" : isAr ? "مسح الصور" : isZh ? "清空图片" : "Clear Images"}
            </Button>
          </div>
          {error ? <div className="flex gap-2 rounded-md border border-rose-200 bg-rose-50/70 px-3 py-2 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-300"><AlertCircle className="mt-0.5 size-4 shrink-0" />{error}</div> : null}
        </div>
      </section>

      <section className="flex min-h-0 flex-col">
        <div className="flex h-14 items-center justify-between border-b border-stone-200 px-5 dark:border-white/10">
          <h2 className="text-sm font-semibold text-stone-950 dark:text-stone-50">{isFa ? "وضعیت تولید" : isAr ? "حالة التوليد" : isZh ? "生成状态" : "Status"}</h2>
          {selectedTask ? <span className={cn("rounded-full border px-2.5 py-1 text-xs", statusClass(selectedTask.status))}>{statusText(selectedTask.status)}</span> : null}
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-5">
          {selectedTask ? (
            <div className="space-y-5">
              <div className="grid gap-3 sm:grid-cols-[150px_150px_minmax(0,1fr)]">
                <div className="rounded-md border border-stone-200 bg-stone-50 p-4 dark:border-white/10 dark:bg-white/[0.03]">
                  <div className="text-xs text-stone-500 dark:text-stone-400">{isFa ? "وضعیت" : isAr ? "الحالة" : isZh ? "状态" : "Status"}</div>
                  <div className="mt-2 flex items-center gap-2 text-sm font-semibold text-stone-950 dark:text-stone-50">
                    {selectedTask.status === "success" ? <CheckCircle2 className="size-4 text-emerald-500" /> : selectedTask.status === "error" ? <XCircle className="size-4 text-rose-500" /> : <LoaderCircle className="size-4 animate-spin text-amber-500" />}
                    {statusText(selectedTask.status)}
                  </div>
                </div>
                <div className="rounded-md border border-stone-200 bg-stone-50 p-4 dark:border-white/10 dark:bg-white/[0.03]">
                  <div className="text-xs text-stone-500 dark:text-stone-400">{isFa ? "زمان سپری‌شده" : isAr ? "الوقت المنقضي" : isZh ? "已执行" : "Elapsed"}</div>
                  <div className="mt-2 text-2xl font-semibold tabular-nums text-stone-950 dark:text-stone-50">{formatElapsed(elapsedOf(selectedTask))}</div>
                </div>
                <div className="rounded-md border border-stone-200 bg-stone-50 p-4 dark:border-white/10 dark:bg-white/[0.03]">
                  <div className="text-xs text-stone-500 dark:text-stone-400">Task ID</div>
                  <div className="mt-2 truncate font-mono text-xs text-stone-700 dark:text-stone-300">{taskIdOf(selectedTask)}</div>
                </div>
              </div>

              {selectedTask.result ? (
                <div className="space-y-3 rounded-md border border-stone-200 bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
                  <div className="text-sm font-semibold text-stone-950 dark:text-stone-50">{isFa ? "نتیجه تولید" : isAr ? "نتيجة التوليد" : isZh ? "生成结果" : "Result"}</div>
                  <ResultFile href={selectedTask.result.primary_url} icon={<FileText className="size-4" />} label={kind === "ppt" ? (isFa ? "فایل PPT" : isAr ? "ملف PPT" : isZh ? "PPT 文件" : "PPT File") : (isFa ? "فایل PSD" : isAr ? "ملف PSD" : isZh ? "PSD 文件" : "PSD File")} downloadText={downloadText} />
                  <ResultFile href={selectedTask.result.zip_url} icon={<FileArchive className="size-4" />} label={isFa ? "بسته متریال" : isAr ? "حزمة الملحقات" : isZh ? "素材包" : "Asset Package"} downloadText={downloadText} />
                </div>
              ) : null}

              {selectedTask.error ? <div className="rounded-md border border-rose-200 bg-rose-50/70 px-3 py-2 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-300">{selectedTask.error}</div> : null}
            </div>
          ) : (
            <div className="flex h-full min-h-80 items-center justify-center text-sm text-stone-400 dark:text-stone-500">{isFa ? "تسک فعالی وجود ندارد" : isAr ? "لا توجد مهام" : isZh ? "暂无任务" : "No active tasks"}</div>
          )}
        </div>
      </section>
    </div>
    <Dialog open={!!deleteConfirm} onOpenChange={(open) => !open && setDeleteConfirm(null)}>
      <DialogContent className="rounded-xl" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{deleteConfirm?.type === "all" ? (isFa ? "پاک کردن تاریخچه" : isAr ? "مسح السجل" : isZh ? "清空历史记录" : "Clear History") : (isFa ? "حذف سابقه" : isAr ? "حذف السجل" : isZh ? "删除历史记录" : "Delete History")}</DialogTitle>
          <DialogDescription>
            {deleteConfirm?.type === "all" ? (isFa ? "آیا از پاک کردن کامل تاریخچه اطمینان دارید؟" : isAr ? "هل أنت متأكد من مسح السجل بالكامل؟" : isZh ? "确认清空当前类型的历史记录吗？" : "Clear all history of this type?") : (isFa ? "آیا از حذف این مورد اطمینان دارید؟" : isAr ? "هل أنت متأكد من حذف هذا السجل؟" : isZh ? "确认删除这条历史记录吗？" : "Delete this history record?")}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setDeleteConfirm(null)}>{t.common.cancel}</Button>
          <Button variant="destructive" onClick={confirmDelete}>{t.common.delete}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
}
