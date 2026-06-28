"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { AlertCircle, CheckCircle2, Clock3, FileArchive, FileText, History, ImagePlus, LoaderCircle, Pencil, Play, Plus, RefreshCw, Trash2, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { formatDisplayDateTime } from "@/lib/display-time";
import { httpRequest } from "@/lib/request";
import { useDisplayTimezone } from "@/lib/use-display-timezone";
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
const statusText = (status: string) => ({ queued: "排队中", running: "生成中", success: "已完成", error: "失败" }[status] || status);
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

function ResultFile({ href, icon, label }: { href?: string; icon: ReactNode; label: string }) {
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
        <a href={href} target="_blank" rel="noreferrer">下载</a>
      </Button>
    </div>
  );
}

export function EditableFilePanel({ title, kind, endpoint, defaultPrompt, imageRequired }: Props) {
  const displayTimezone = useDisplayTimezone();
  const [prompt, setPrompt] = useState(defaultPrompt);
  const [images, setImages] = useState<string[]>([]);
  const [tasks, setTasks] = useState<EditableFileTask[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  const [drafts, setDrafts] = useState<Record<string, EditableFileDraft>>({});
  const [deletedIds, setDeletedIds] = useState<Set<string>>(new Set());
  const [renamingId, setRenamingId] = useState("");
  const [renamingTitle, setRenamingTitle] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState<{ type: "one"; id: string } | { type: "all"; ids: string[] } | null>(null);
  const visibleTasks = useMemo(() => tasks.filter((task) => task.kind === kind && !deletedIds.has(taskIdOf(task))).slice(0, MAX_HISTORY), [deletedIds, kind, tasks]);
  const selectedTask = selectedId === DRAFT_ID ? null : visibleTasks.find((task) => taskIdOf(task) === selectedId) || visibleTasks[0] || null;
  const running = visibleTasks.some(isRunning);
  const runningIds = visibleTasks.filter(isRunning).map(taskIdOf).join(",");

  const elapsedOf = (task: EditableFileTask | null | undefined) => {
    if (!task) return 0;
    const base = Math.max(0, Number(task.elapsed_seconds || 0));
    return Math.max(0, isRunning(task) && task.polled_at ? base + Math.floor((now - task.polled_at) / 1000) : base);
  };

  const fetchTasks = useCallback(async (ids: string[] = []) => {
    const taskIds = Array.from(new Set(ids.filter(Boolean))).slice(0, MAX_HISTORY);
    setPolling(true);
    try {
      const path = taskIds.length ? `/v1/editable-file-tasks?ids=${taskIds.map(encodeURIComponent).join(",")}` : "/v1/editable-file-tasks";
      const result = await httpRequest<{ items: EditableFileTask[]; missing_ids?: string[] }>(path);
      const missingIds = result.missing_ids || [];
      const hidden = await listDeletedEditableFileIds(kind);
      setTasks((current) => (taskIds.length ? mergeTasks(removeTasks(current, missingIds), result.items || []) : (result.items || [])).filter((task) => !hidden.has(taskIdOf(task))));
      setSelectedId((current) => missingIds.includes(current) ? "" : current);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPolling(false);
    }
  }, [kind]);

  useEffect(() => {
    void listEditableFileDrafts(kind).then(setDrafts);
    void listDeletedEditableFileIds(kind).then(setDeletedIds);
    void fetchTasks();
  }, [fetchTasks, kind]);

  useEffect(() => {
    if (selectedId === DRAFT_ID) return;
    const draft = drafts[selectedId];
    const task = visibleTasks.find((item) => taskIdOf(item) === selectedId);
    setPrompt(draft?.prompt || task?.prompt_preview || defaultPrompt);
    setImages(Array.isArray(draft?.images) ? draft.images : []);
  }, [defaultPrompt, drafts, selectedId, visibleTasks]);

  useEffect(() => {
    if (selectedId === DRAFT_ID) return;
    if (visibleTasks.length && (!selectedId || !visibleTasks.some((task) => taskIdOf(task) === selectedId))) setSelectedId(taskIdOf(visibleTasks[0]));
    if (!visibleTasks.length && selectedId) setSelectedId("");
  }, [selectedId, visibleTasks]);

  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  useEffect(() => {
    const ids = runningIds.split(",").filter(Boolean);
    if (!ids.length) return;
    const timer = window.setInterval(() => void fetchTasks(ids), 5000);
    return () => window.clearInterval(timer);
  }, [fetchTasks, runningIds]);

  const appendFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    const values = await Promise.all(Array.from(files).map(readFile));
    setImages((current) => [...current, ...values]);
  };

  const persistDrafts = (updater: (current: Record<string, EditableFileDraft>) => Record<string, EditableFileDraft>) => {
    setDrafts((current) => {
      const next = updater(current);
      void saveEditableFileDrafts(kind, next);
      return next;
    });
  };

  const createDraft = () => {
    setError("");
    setSelectedId(DRAFT_ID);
    setPrompt(defaultPrompt);
    setImages([]);
  };

  const renameTask = (id: string, title: string) => {
    const trimmed = title.trim();
    if (!id || !trimmed) return;
    persistDrafts((current) => ({ ...current, [id]: { ...(current[id] || {}), title: trimmed } }));
  };

  const deleteTask = (id: string) => {
    if (!id) return;
    const nextDeleted = new Set(deletedIds);
    nextDeleted.add(id);
    void saveDeletedEditableFileIds(kind, nextDeleted);
    setDeletedIds(nextDeleted);
    setTasks((current) => current.filter((task) => taskIdOf(task) !== id));
    persistDrafts((current) => {
      const next = { ...current };
      delete next[id];
      return next;
    });
    if (selectedId === id) setSelectedId("");
  };

  const clearHistory = () => {
    const ids = deleteConfirm?.type === "all" ? deleteConfirm.ids : tasks.filter((task) => task.kind === kind).map(taskIdOf).filter(Boolean);
    if (!ids.length) return;
    const nextDeleted = new Set([...deletedIds, ...ids]);
    void saveDeletedEditableFileIds(kind, nextDeleted);
    setDeletedIds(nextDeleted);
    setTasks((current) => current.filter((task) => task.kind !== kind || !ids.includes(taskIdOf(task))));
    persistDrafts((current) => {
      const next = { ...current };
      ids.forEach((id) => delete next[id]);
      return next;
    });
    setSelectedId("");
  };

  const confirmDelete = () => {
    if (!deleteConfirm) return;
    if (deleteConfirm.type === "one") deleteTask(deleteConfirm.id);
    else clearHistory();
    setDeleteConfirm(null);
  };

  const submit = async () => {
    setError("");
    setSubmitting(true);
    try {
      const base64_images = images;
      if (imageRequired && !base64_images.length) throw new Error("base64_images is empty");
      const task = await httpRequest<EditableFileTask>(endpoint, { method: "POST", body: { client_task_id: createClientTaskId(), prompt, base64_images } });
      const polledAt = Date.now();
      const id = taskIdOf(task);
      const draft = { prompt: prompt.trim(), images: base64_images, title: titleOfPrompt(prompt, title) };
      const nextTask = { ...task, prompt_preview: draft.prompt, polled_at: polledAt };
      setNow(polledAt);
      persistDrafts((current) => ({ ...current, [id]: draft }));
      setTasks((current) => mergeTasks(current.filter((item) => taskIdOf(item) !== taskIdOf(nextTask)), [nextTask]));
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
    setRenamingTitle(drafts[id]?.title || titleOfPrompt(drafts[id]?.prompt || "", `${kind.toUpperCase()} 任务`));
  };
  const commitRename = () => {
    renameTask(renamingId, renamingTitle);
    setRenamingId("");
    setRenamingTitle("");
  };

  return (
    <>
    <div className="grid h-full min-h-[calc(100vh-148px)] overflow-hidden rounded-lg border border-stone-200 bg-white shadow-sm dark:border-white/10 dark:bg-stone-950 lg:grid-cols-[288px_420px_minmax(0,1fr)]">
      <aside className="flex min-h-0 flex-col border-b border-stone-200 bg-stone-50/70 dark:border-white/10 dark:bg-white/[0.02] lg:border-r lg:border-b-0">
        <div className="flex h-14 items-center justify-between border-b border-stone-200 px-4 dark:border-white/10">
          <div className="flex items-center gap-2 text-sm font-semibold text-stone-950 dark:text-stone-50">
            <History className="size-4" />
            历史记录
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
                  <button type="button" onClick={() => selectTask(id)} className="min-w-0 flex-1 text-left">
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
                      <span className="truncate">{formatDisplayDateTime(task.created_at, displayTimezone, task.created_at || id)}</span>
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
            <div className="flex h-full items-center justify-center text-sm text-stone-400 dark:text-stone-500">暂无记录</div>
          )}
        </div>
      </aside>

      <section className="flex min-h-0 flex-col border-b border-stone-200 dark:border-white/10 lg:border-r lg:border-b-0">
        <div className="flex h-14 items-center justify-between border-b border-stone-200 px-5 dark:border-white/10">
          <h2 className="text-sm font-semibold text-stone-950 dark:text-stone-50">{title}</h2>
          <Button size="sm" onClick={() => void submit()} disabled={submitting || running}>
            {submitting ? <LoaderCircle className="animate-spin" /> : <Play />}
            生成
          </Button>
        </div>
        <div className="min-h-0 flex-1 space-y-5 overflow-auto p-5">
          <div className="space-y-2">
            <Label htmlFor={`${endpoint}-prompt`} className="text-xs font-semibold text-stone-700 dark:text-stone-300">需求</Label>
            <Textarea id={`${endpoint}-prompt`} value={prompt} onChange={(event) => setPrompt(event.target.value)} className="min-h-56 rounded-md border-stone-200 bg-white text-sm leading-6 shadow-none dark:border-white/10 dark:bg-white/[0.03]" />
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-semibold text-stone-700 dark:text-stone-300">参考图</Label>
              <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-500 dark:bg-white/10 dark:text-stone-400">{images.length}</span>
            </div>
            <label className="group flex h-24 cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed border-stone-300 bg-stone-50 text-sm font-medium text-stone-600 transition hover:border-stone-950 hover:bg-white dark:border-white/15 dark:bg-white/[0.03] dark:text-stone-300 dark:hover:border-white/50">
              <ImagePlus className="size-4 transition group-hover:scale-110" />
              上传图片
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
              清空图片
            </Button>
          </div>
          {error ? <div className="flex gap-2 rounded-md border border-rose-200 bg-rose-50/70 px-3 py-2 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-300"><AlertCircle className="mt-0.5 size-4 shrink-0" />{error}</div> : null}
        </div>
      </section>

      <section className="flex min-h-0 flex-col">
        <div className="flex h-14 items-center justify-between border-b border-stone-200 px-5 dark:border-white/10">
          <h2 className="text-sm font-semibold text-stone-950 dark:text-stone-50">生成状态</h2>
          {selectedTask ? <span className={cn("rounded-full border px-2.5 py-1 text-xs", statusClass(selectedTask.status))}>{statusText(selectedTask.status)}</span> : null}
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-5">
          {selectedTask ? (
            <div className="space-y-5">
              <div className="grid gap-3 sm:grid-cols-[150px_150px_minmax(0,1fr)]">
                <div className="rounded-md border border-stone-200 bg-stone-50 p-4 dark:border-white/10 dark:bg-white/[0.03]">
                  <div className="text-xs text-stone-500 dark:text-stone-400">状态</div>
                  <div className="mt-2 flex items-center gap-2 text-sm font-semibold text-stone-950 dark:text-stone-50">
                    {selectedTask.status === "success" ? <CheckCircle2 className="size-4 text-emerald-500" /> : selectedTask.status === "error" ? <XCircle className="size-4 text-rose-500" /> : <LoaderCircle className="size-4 animate-spin text-amber-500" />}
                    {statusText(selectedTask.status)}
                  </div>
                </div>
                <div className="rounded-md border border-stone-200 bg-stone-50 p-4 dark:border-white/10 dark:bg-white/[0.03]">
                  <div className="text-xs text-stone-500 dark:text-stone-400">已执行</div>
                  <div className="mt-2 text-2xl font-semibold tabular-nums text-stone-950 dark:text-stone-50">{formatElapsed(elapsedOf(selectedTask))}</div>
                </div>
                <div className="rounded-md border border-stone-200 bg-stone-50 p-4 dark:border-white/10 dark:bg-white/[0.03]">
                  <div className="text-xs text-stone-500 dark:text-stone-400">Task ID</div>
                  <div className="mt-2 truncate font-mono text-xs text-stone-700 dark:text-stone-300">{taskIdOf(selectedTask)}</div>
                </div>
              </div>

              {selectedTask.result ? (
                <div className="space-y-3 rounded-md border border-stone-200 bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
                  <div className="text-sm font-semibold text-stone-950 dark:text-stone-50">生成结果</div>
                  <ResultFile href={selectedTask.result.primary_url} icon={<FileText className="size-4" />} label={kind === "ppt" ? "PPT 文件" : "PSD 文件"} />
                  <ResultFile href={selectedTask.result.zip_url} icon={<FileArchive className="size-4" />} label="素材包" />
                </div>
              ) : null}

              {selectedTask.error ? <div className="rounded-md border border-rose-200 bg-rose-50/70 px-3 py-2 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-300">{selectedTask.error}</div> : null}
            </div>
          ) : (
            <div className="flex h-full min-h-80 items-center justify-center text-sm text-stone-400 dark:text-stone-500">暂无任务</div>
          )}
        </div>
      </section>
    </div>
    <Dialog open={!!deleteConfirm} onOpenChange={(open) => !open && setDeleteConfirm(null)}>
      <DialogContent className="rounded-xl" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{deleteConfirm?.type === "all" ? "清空历史记录" : "删除历史记录"}</DialogTitle>
          <DialogDescription>
            {deleteConfirm?.type === "all" ? "确认清空当前类型的历史记录吗？" : "确认删除这条历史记录吗？"}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setDeleteConfirm(null)}>取消</Button>
          <Button variant="destructive" onClick={confirmDelete}>确认删除</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
}
