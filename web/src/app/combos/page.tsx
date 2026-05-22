"use client";

import { useEffect, useState } from "react";
import {
  Combine, Plus, Trash2, ArrowDown, MessageSquare,
  ImageIcon, Eye, X, ChevronDown, Save, Video, Camera,
  Pencil, Check, ArrowUp,
} from "lucide-react";
import { request } from "@/lib/request";
import { cn } from "@/lib/utils";
import { useLangStore } from "@/store/lang";
import { translations, TranslationKey } from "@/lib/i18n";

type ModelInfo = {
  id: string;
  owned_by: string;
  capability: string;
  capabilities: string[];
  capability_labels: string[];
  enabled: boolean;
};

type ComboModels = Record<string, string[]>;

const CAP_COLORS: Record<string, string> = {
  chat: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  vision: "bg-purple-500/10 text-purple-400 border-purple-500/20",
  image: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  video: "bg-rose-500/10 text-rose-400 border-rose-500/20",
};

const CAP_ICONS: Record<string, typeof MessageSquare> = {
  chat: MessageSquare, vision: Eye, image: ImageIcon, video: Video,
};

const TINT_CYCLE = ["card-tint-indigo", "card-tint-emerald", "card-tint-amber", "card-tint-violet", "card-tint-sky", "card-tint-rose"] as const;

function ModelChainView({ models, allModels, t }: { models: string[]; allModels: ModelInfo[]; t: (key: TranslationKey) => string }) {
  return (
    <div>
      <div className="space-y-1.5">
        {models.map((modelId, idx) => {
          const info = allModels.find(m => m.id === modelId);
          const cap = info?.capability || "chat";
          const CapIcon = CAP_ICONS[cap] || MessageSquare;
          return (
            <div key={idx} className="flex items-center gap-2">
              <span className={cn("text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center shrink-0", idx === 0 ? "bg-emerald-500/20 text-emerald-400" : "bg-stone-200 text-stone-500")}>{idx + 1}</span>
              <CapIcon className="size-3 shrink-0 text-stone-500" />
              <span className={cn("rounded-lg px-3 py-1.5 text-xs font-mono", idx === 0 ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-stone-100 text-stone-700")}>{modelId}</span>
              {(info?.capability_labels || ["Chat"]).map((label: string) => {
                const capKey = label === "Chat" ? "chat" : label === t("vision") ? "vision" : label === "Phân tích ảnh" ? "vision" : label === "Video" ? "video" : label === "Phân tích video" ? "video" : "image";
                return <span key={label} className={cn("text-[10px] px-1.5 py-0.5 rounded border", CAP_COLORS[capKey])}>{label}</span>;
              })}
              {idx < models.length - 1 && <ArrowDown className="size-3 text-stone-600" />}
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-stone-500">Thứ tự fallback: thử model ❶ trước → nếu lỗi mới thử model tiếp theo</p>
    </div>
  );
}

function ComboEditView({ editModels, allModels, filteredModels, dropdownOpen, setDropdownOpen, removeFromEdit, addToEdit, moveUpInEdit, moveDownInEdit, cancelEdit, saveEdit }: {
  editModels: string[]; allModels: ModelInfo[]; filteredModels: ModelInfo[];
  dropdownOpen: boolean; setDropdownOpen: (v: boolean) => void;
  removeFromEdit: (idx: number) => void; addToEdit: (id: string) => void;
  moveUpInEdit: (idx: number) => void; moveDownInEdit: (idx: number) => void;
  cancelEdit: () => void; saveEdit: () => void;
}) {
  return (
    <div className="space-y-3">
      {editModels.length > 0 && (
        <div className="space-y-1.5">
          {editModels.map((modelId, idx) => {
            const info = allModels.find(m => m.id === modelId);
            const cap = info?.capability || "chat";
            const CapIcon = CAP_ICONS[cap] || MessageSquare;
            return (
              <div key={idx} className="flex items-center gap-2">
                <span className={cn("text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center shrink-0", idx === 0 ? "bg-emerald-500/20 text-emerald-400" : "bg-stone-200 text-stone-500")}>{idx + 1}</span>
                <CapIcon className="size-3 shrink-0 text-stone-500" />
                <span className="rounded-lg px-3 py-1.5 text-xs font-mono bg-stone-100 text-stone-700 flex-1">{modelId}</span>
                <div className="flex flex-col gap-0.5">
                  <button type="button" onClick={() => moveUpInEdit(idx)} disabled={idx === 0} className="rounded p-0.5 text-stone-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30"><ArrowUp className="size-3" /></button>
                  <button type="button" onClick={() => moveDownInEdit(idx)} disabled={idx === editModels.length - 1} className="rounded p-0.5 text-stone-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30"><ArrowDown className="size-3" /></button>
                </div>
                <button type="button" onClick={() => removeFromEdit(idx)} className="rounded p-0.5 text-stone-400 hover:bg-rose-50 hover:text-rose-500"><X className="size-3.5" /></button>
              </div>
            );
          })}
        </div>
      )}
      <div className="relative">
        <button type="button" onClick={() => setDropdownOpen(true)} className="flex w-full items-center justify-between rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-900 hover:border-stone-600 transition">
          <span className="text-stone-500">+ Thêm model vào chuỗi</span>
          <ChevronDown className="size-4 text-stone-500" />
        </button>
        {dropdownOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setDropdownOpen(false)}>
            <div className="bg-white rounded-2xl shadow-2xl w-[720px] max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between px-5 py-4 border-b border-stone-100 shrink-0">
                <h3 className="text-[15px] font-bold text-slate-900">Thêm Model vào chuỗi</h3>
                <button onClick={() => setDropdownOpen(false)} className="rounded-lg p-1.5 text-stone-400 hover:bg-stone-100 hover:text-stone-700"><X className="size-5" /></button>
              </div>
              <div className="overflow-y-auto flex-1 p-2">
                {filteredModels.filter(m => !editModels.includes(m.id)).length === 0 ? (
                  <p className="px-4 py-8 text-sm text-stone-400 text-center">Đã thêm tất cả model</p>
                ) : (
                  filteredModels.filter(m => !editModels.includes(m.id)).map(m => (
                    <button key={m.id} type="button" onClick={() => { addToEdit(m.id); setDropdownOpen(false); }} className="flex w-full items-center gap-3 px-4 py-2.5 text-left rounded-lg transition mb-0.5 hover:bg-stone-50 border border-transparent">
                      <span className="text-[13px] font-mono text-stone-800 truncate flex-1">{m.id}</span>
                      <span className="text-[10px] text-stone-400">{m.owned_by}</span>
                    </button>
                  ))
                )}
              </div>
              <div className="px-5 py-3 border-t border-stone-100 shrink-0 text-right">
                <button onClick={() => setDropdownOpen(false)} className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800">Xong</button>
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="flex gap-2 justify-end">
        <button type="button" onClick={cancelEdit} className="rounded-lg border border-stone-200 bg-white px-3 py-1.5 text-xs text-stone-500 hover:bg-stone-100">Hủy</button>
        <button type="button" onClick={saveEdit} disabled={editModels.length < 2} className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-3 py-1.5 text-xs text-white hover:bg-stone-800 disabled:opacity-40">
          <Check className="size-3.5" /> Lưu
        </button>
      </div>
    </div>
  );
}

export default function CombosPage() {
  const { lang } = useLangStore();
  const t = (key: TranslationKey) => translations[lang][key] || key;
  const [combos, setCombos] = useState<ComboModels>({});
  const [allModels, setAllModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState("");
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [editingCombo, setEditingCombo] = useState<string | null>(null);
  const [editModels, setEditModels] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [filterCap, setFilterCap] = useState<string>("all");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [editDropdownOpen, setEditDropdownOpen] = useState(false);
  const [modelSearch, setModelSearch] = useState("");

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    setLoading(true);
    try {
      const [comboRes, modelsRes] = await Promise.all([
        request.get("/api/settings"),
        request.get("/api/v1/models-with-capabilities"),
      ]);
      const config = (comboRes.data as any)?.config || {};
      setCombos(config.combo_models || {});
      setAllModels((modelsRes.data as any)?.models?.filter((m: any) => m.enabled !== false) || []);
    } catch (e) { console.error("Failed to load", e); }
    finally { setLoading(false); }
  }

  async function saveCombos(updated: ComboModels) {
    setCombos(updated); setSaved(true); setError("");
    try {
      const res = await request.post("/api/settings", { combo_models: updated });
      const cfg = (res.data as any)?.config || {};
      setCombos(cfg.combo_models || {});
    } catch (e: any) {
      setError(e?.response?.data?.detail?.error || e?.message || t("saveError"));
      await loadAll();
    }
    setTimeout(() => setSaved(false), 2000);
  }

  function addCombo() {
    const name = newName.trim();
    if (!name) return;
    if (selectedModels.length < 2) { setError(t("atLeastTwoModels")); return; }
    saveCombos({ ...combos, [name]: [...selectedModels] });
    setNewName(""); setSelectedModels([]);
  }

  function removeCombo(name: string) {
    const updated = { ...combos }; delete updated[name];
    setCombos(updated); saveCombos(updated);
  }

  function startEdit(name: string) {
    setEditingCombo(name); setEditModels([...(combos[name] || [])]);
  }
  function cancelEdit() { setEditingCombo(null); setEditModels([]); }
  function addToEdit(modelId: string) { if (!editModels.includes(modelId)) setEditModels([...editModels, modelId]); }
  function removeFromEdit(idx: number) { setEditModels(editModels.filter((_, i) => i !== idx)); }
  function moveUpInEdit(idx: number) {
    if (idx <= 0) return;
    const updated = [...editModels];
    [updated[idx - 1], updated[idx]] = [updated[idx], updated[idx - 1]];
    setEditModels(updated);
  }
  function moveDownInEdit(idx: number) {
    if (idx >= editModels.length - 1) return;
    const updated = [...editModels];
    [updated[idx], updated[idx + 1]] = [updated[idx + 1], updated[idx]];
    setEditModels(updated);
  }
  function saveEdit() {
    if (!editingCombo || editModels.length < 2) return;
    saveCombos({ ...combos, [editingCombo]: [...editModels] });
    setEditingCombo(null); setEditModels([]);
  }

  function addModelToSelection(modelId: string) {
    if (!selectedModels.includes(modelId)) setSelectedModels([...selectedModels, modelId]);
    setDropdownOpen(false);
  }
  function removeModelFromSelection(idx: number) { setSelectedModels(selectedModels.filter((_, i) => i !== idx)); }

  const filteredModels = allModels.filter(m => {
    if (modelSearch && !m.id.toLowerCase().includes(modelSearch.toLowerCase())) return false;
    if (filterCap === "all") return true;
    return (m.capabilities || [m.capability]).includes(filterCap);
  });
  const availableForSelection = filteredModels.filter(m => !selectedModels.includes(m.id));

  const counts = { chat: 0, vision: 0, image: 0, video: 0 };
  for (const m of allModels) {
    if (m.enabled === false) continue;
    for (const c of (m.capabilities || [m.capability])) { if (c in counts) counts[c as keyof typeof counts]++; }
  }

  if (loading) return <div className="flex items-center justify-center py-20"><p className="text-stone-500">Đang tải...</p></div>;

  const comboEntries = Object.entries(combos);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1 border-b border-black/[0.04] pb-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-[24px] font-bold tracking-tight text-slate-900">{t("combosTitle")}</h1>
            {saved && <span className="text-[13px] text-emerald-600 font-medium">✓ {t("saved")}</span>}
          </div>
          <button type="button" onClick={() => saveCombos(combos)} className="inline-flex items-center gap-2 rounded-[12px] bg-slate-900 px-4 py-2 text-[14px] font-medium text-white hover:bg-slate-800 transition">
            <Save className="size-4" /> Lưu
          </button>
        </div>
        <p className="text-[14px] text-slate-500">Combo model tự động fallback qua nhiều provider theo thứ tự ưu tiên.</p>
      </div>

      <div className="flex gap-3 flex-wrap">
        <span className="inline-flex items-center gap-1.5 rounded-lg border border-blue-500/20 bg-blue-500/10 px-3 py-1.5 text-xs text-blue-400"><MessageSquare className="size-3" /> {t("chat")}: {counts.chat}</span>
        <span className="inline-flex items-center gap-1.5 rounded-lg border border-purple-500/20 bg-purple-500/10 px-3 py-1.5 text-xs text-purple-400"><Eye className="size-3" /> {t("vision")}: {counts.vision}</span>
        <span className="inline-flex items-center gap-1.5 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-400"><ImageIcon className="size-3" /> {t("imageGen")}: {counts.image}</span>
      </div>

      {/* Add new combo */}
      <div className="rounded-[16px] p-6 card-main">
        <h3 className="mb-4 text-[15px] font-bold text-slate-900">{t("addNewCombo")}</h3>
        <div className="mb-3">
          <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder={t("comboNamePlaceholder")} className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm text-stone-900 placeholder:text-stone-400 focus:border-stone-500 focus:outline-none" />
        </div>
        {selectedModels.length > 0 && (
          <div className="mb-3 space-y-1.5">
            <p className="text-[10px] font-medium uppercase tracking-wider text-stone-500">{t("fallbackOrder").replace("{count}", String(selectedModels.length))}</p>
            {selectedModels.map((modelId, idx) => {
              const info = allModels.find(m => m.id === modelId);
              const cap = info?.capability || "chat";
              const CapIcon = CAP_ICONS[cap] || MessageSquare;
              return (
                <div key={idx} className="flex items-center gap-2 rounded-lg bg-stone-100/50 px-3 py-2">
                  <span className={cn("text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center shrink-0", idx === 0 ? "bg-emerald-500/20 text-emerald-400" : "bg-stone-200 text-stone-500")}>{idx + 1}</span>
                  <CapIcon className="size-3 shrink-0 text-stone-500" />
                  <span className="flex-1 text-xs font-mono text-stone-800 truncate">{modelId}</span>
                  {(info?.capability_labels || ["Chat"]).map((label: string) => {
                    const capKey = label === "Chat" ? "chat" : label === t("vision") ? "vision" : label === "Phân tích ảnh" ? "vision" : label === "Video" ? "video" : label === "Phân tích video" ? "video" : "image";
                    return <span key={label} className={cn("text-[10px] px-1.5 py-0.5 rounded border", CAP_COLORS[capKey])}>{label}</span>;
                  })}
                  <button type="button" onClick={() => removeModelFromSelection(idx)} className="rounded p-0.5 text-stone-500 hover:bg-red-500/10 hover:text-red-400"><X className="size-3.5" /></button>
                  {idx < selectedModels.length - 1 && <ArrowDown className="size-3 text-stone-600 shrink-0" />}
                </div>
              );
            })}
          </div>
        )}
        <div className="flex gap-2 mb-3">
          <div className="flex rounded-lg border border-stone-200 overflow-hidden text-xs">
            {(["all", "chat", "vision", "image", "video"] as const).map(cap => (
              <button key={cap} type="button" onClick={() => setFilterCap(cap)} className={cn("px-3 py-1.5 transition", filterCap === cap ? "bg-stone-900 text-white" : "text-stone-500 hover:text-stone-700")}>
                {cap === "all" ? t("all") : cap === "chat" ? t("chat") : cap === "vision" ? t("vision") : cap === "video" ? "Video" : t("imageGen")}
              </button>
            ))}
          </div>
          <div className="relative flex-1">
            <button type="button" onClick={() => setDropdownOpen(true)} className="flex w-full items-center justify-between rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-900 hover:border-stone-600 transition">
              <span className="text-stone-500">{selectedModels.length > 0 ? `Đã chọn ${selectedModels.length} model` : t("selectModelPlaceholder")}</span><ChevronDown className="size-4 text-stone-500" />
            </button>
            {dropdownOpen && (
              <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
                <div className="bg-white rounded-2xl shadow-2xl w-[720px] max-h-[80vh] flex flex-col">
                  <div className="flex items-center justify-between px-5 py-4 border-b border-stone-100 shrink-0">
                    <h3 className="text-[15px] font-bold text-slate-900">Chọn Model</h3>
                    <button onClick={() => setDropdownOpen(false)} className="rounded-lg p-1.5 text-stone-400 hover:bg-stone-100 hover:text-stone-700"><X className="size-5" /></button>
                  </div>
                  <div className="p-3 border-b border-stone-50 shrink-0">
                    <input autoFocus className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm text-stone-900 placeholder:text-stone-400 focus:border-stone-400 focus:outline-none" placeholder="Tìm model... (lọc theo tên)" onChange={(e) => setModelSearch(e.target.value)} />
                  </div>
                  <div className="overflow-y-auto flex-1 p-2">
                    {availableForSelection.length === 0 ? (
                      <p className="px-4 py-8 text-sm text-stone-400 text-center">{filterCap !== "all" ? t("noModelsInCategory") : t("allModelsSelected")}</p>
                    ) : availableForSelection.map(m => {
                      const CapIcon = CAP_ICONS[m.capability] || MessageSquare;
                      const isSelected = selectedModels.includes(m.id);
                      return (
                        <button key={m.id} type="button" onClick={() => addModelToSelection(m.id)}
                          className={cn("flex w-full items-center gap-3 px-4 py-2.5 text-left rounded-lg transition mb-0.5",
                            isSelected ? "bg-emerald-50 border border-emerald-200" : "hover:bg-stone-50 border border-transparent")}>
                          <CapIcon className="size-4 shrink-0 text-stone-400" />
                          <div className="flex-1 min-w-0">
                            <span className="text-[13px] font-mono text-stone-800 truncate block">{m.id}</span>
                            <span className="text-[10px] text-stone-400">{m.owned_by}</span>
                          </div>
                          {(m.capability_labels || ["Chat"]).map((label: string) => {
                            const capKey = label === "Chat" ? "chat" : label === t("vision") ? "vision" : label === "Phân tích ảnh" ? "vision" : label === "Video" ? "video" : label === "Phân tích video" ? "video" : "image";
                            return <span key={label} className={cn("text-[10px] px-1.5 py-0.5 rounded border shrink-0", CAP_COLORS[capKey])}>{label}</span>;
                          })}
                          {isSelected && <Check className="size-4 text-emerald-500 shrink-0" />}
                        </button>
                      );
                    })}
                  </div>
                  <div className="px-5 py-3 border-t border-stone-100 shrink-0 flex justify-between">
                    <span className="text-xs text-stone-400">{availableForSelection.length} model có sẵn</span>
                    <button onClick={() => setDropdownOpen(false)} className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800">Xong</button>
                  </div>
                </div>
              </div>
            )}
          </div>
          <button type="button" onClick={addCombo} disabled={!newName.trim() || selectedModels.length < 2} className="inline-flex items-center gap-1.5 rounded-lg bg-stone-100 px-4 py-2 text-sm font-medium text-stone-950 transition hover:bg-white disabled:opacity-40 shrink-0">
            <Plus className="size-4" /> Thêm
          </button>
        </div>
        {error && <p className="text-xs text-red-400">{error}</p>}
      </div>

      {/* Existing combos */}
      {comboEntries.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-stone-500">
          <Combine className="size-12 mb-3 opacity-50" /><p>{t("noCombos")}</p><p className="text-xs mt-1">{t("createFirstCombo")}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {comboEntries.map(([name, models], idx) => {
            const isEditing = editingCombo === name;
            return (
            <div key={name} className={cn("group relative overflow-hidden rounded-[16px] p-6 card-3d", TINT_CYCLE[idx % TINT_CYCLE.length], "transition-all duration-300 hover:-translate-y-1")}>
              <div className="absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r from-indigo-500 to-violet-500 opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="flex size-9 items-center justify-center rounded-[10px] bg-slate-50"><Combine className="size-[18px] text-slate-400" /></div>
                  <h3 className="text-[16px] font-bold tracking-tight text-slate-900">{name}</h3>
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500">{models.length} {t("models")}</span>
                </div>
                <div className="flex items-center gap-1">
                  <button type="button" onClick={() => startEdit(name)} className="rounded-[10px] p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700" title="Chỉnh sửa"><Pencil className="size-4" /></button>
                  <button type="button" onClick={() => removeCombo(name)} className="rounded-[10px] p-2 text-slate-400 transition hover:bg-rose-50 hover:text-rose-500"><Trash2 className="size-4" /></button>
                </div>
              </div>
              {isEditing ? (
                <ComboEditView editModels={editModels} allModels={allModels} filteredModels={filteredModels} dropdownOpen={editDropdownOpen} setDropdownOpen={setEditDropdownOpen} removeFromEdit={removeFromEdit} addToEdit={addToEdit} moveUpInEdit={moveUpInEdit} moveDownInEdit={moveDownInEdit} cancelEdit={cancelEdit} saveEdit={saveEdit} />
              ) : (
                <ModelChainView models={models} allModels={allModels} t={t} />
              )}
            </div>
          )})}
        </div>
      )}
    </div>
  );
}
