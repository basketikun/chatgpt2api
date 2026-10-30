"use client";

import { useEffect, useRef, useState } from "react";
import { ImagePlus, LoaderCircle, Send, X } from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { httpRequest } from "@/lib/request";

import { pretty, type ChatCompletionResponse, type ChatContentPart, type ChatMessage } from "./types";

type SelectedImage = {
  id: string;
  name: string;
  size: number;
  url: string;
};

const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

function readImage(file: File, t: TFunction): Promise<SelectedImage> {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith("image/")) {
      reject(new Error(t("chatPanel.errors.notImage", { fileName: file.name })));
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      reject(new Error(t("chatPanel.errors.tooLarge", { fileName: file.name })));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const url = String(reader.result || "");
      if (!url.startsWith("data:image/")) {
        reject(new Error(t("chatPanel.errors.readFailed", { fileName: file.name })));
        return;
      }
      resolve({
        id: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(16).slice(2)}`,
        name: file.name,
        size: file.size,
        url,
      });
    };
    reader.onerror = () => reject(reader.error || new Error(t("chatPanel.errors.readFailed", { fileName: file.name })));
    reader.readAsDataURL(file);
  });
}

function messageText(message: ChatMessage): string {
  if (typeof message.content === "string") {
    return message.content;
  }
  return message.content
    .filter((part): part is { type: "text"; text: string } => part.type === "text")
    .map((part) => part.text)
    .join("");
}

function messageImages(message: ChatMessage): string[] {
  if (!Array.isArray(message.content)) {
    return [];
  }
  return message.content
    .filter((part): part is { type: "image_url"; image_url: { url: string } } => part.type === "image_url")
    .map((part) => part.image_url.url);
}

export function ChatPanel() {
  const { t, i18n } = useTranslation("debug");
  const [model, setModel] = useState("auto");
  const [reasoningEffort, setReasoningEffort] = useState("");
  const [input, setInput] = useState(t("chatPanel.defaultInput"));
  const isDefaultInputRef = useRef(true);

  // The initial language is pinned to the zh fallback until the detected locale
  // is applied after mount (see i18n/config.ts), so recompute the untouched
  // default once the real locale is known instead of freezing it in zh.
  useEffect(() => {
    if (isDefaultInputRef.current) setInput(t("chatPanel.defaultInput"));
  }, [i18n.language, t]);

  const [selectedImages, setSelectedImages] = useState<SelectedImage[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [raw, setRaw] = useState<ChatCompletionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleImagesChange = async (files: FileList | null) => {
    if (!files?.length) return;
    setError("");
    try {
      const images = await Promise.all(Array.from(files).map((file) => readImage(file, t)));
      setSelectedImages((current) => [...current, ...images].slice(0, 4));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const sendChat = async () => {
    const text = input.trim();
    if (!text && !selectedImages.length) return;
    const content: string | ChatContentPart[] = selectedImages.length
      ? [
          ...(text ? [{ type: "text" as const, text }] : []),
          ...selectedImages.map((image) => ({ type: "image_url" as const, image_url: { url: image.url } })),
        ]
      : text;
    const nextMessages: ChatMessage[] = [...messages, { role: "user", content }];
    setMessages(nextMessages);
    isDefaultInputRef.current = false;
    setInput("");
    setSelectedImages([]);
    setLoading(true);
    setError("");
    try {
      const body = {
        model: model.trim() || "auto",
        messages: nextMessages,
        ...(reasoningEffort ? { reasoning_effort: reasoningEffort } : {}),
      };
      const result = await httpRequest<ChatCompletionResponse>("/v1/chat/completions", { method: "POST", body });
      setRaw(result);
      setMessages([...nextMessages, { role: "assistant", content: String(result.choices?.[0]?.message?.content || "") }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([]);
    setSelectedImages([]);
    setRaw(null);
    setError("");
  };

  return (
    <div className="grid h-full min-h-0 gap-8 lg:grid-cols-[360px_minmax(0,1fr)]">
      <section className="flex min-h-0 flex-col lg:border-r lg:border-stone-200/70 lg:pr-8 dark:lg:border-white/10">
        <div className="border-b border-stone-200/70 pb-3 dark:border-white/10">
          <h2 className="text-sm font-medium text-stone-500 dark:text-stone-400">{t("chatPanel.requestTitle")}</h2>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-auto pt-4">
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_160px]">
            <div className="space-y-2">
              <Label htmlFor="chat-model">Model</Label>
              <Input id="chat-model" value={model} onChange={(event) => setModel(event.target.value)} className="rounded-md border-stone-200/70 bg-transparent shadow-none dark:border-white/10" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="chat-reasoning-effort">{t("chatPanel.reasoningEffort.label")}</Label>
              <Select value={reasoningEffort || "default"} onValueChange={(value) => setReasoningEffort(value === "default" ? "" : value)}>
                <SelectTrigger id="chat-reasoning-effort" className="h-10 rounded-md border-stone-200/70 bg-transparent shadow-none dark:border-white/10">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="default">{t("chatPanel.reasoningEffort.default")}</SelectItem>
                  <SelectItem value="low">{t("chatPanel.reasoningEffort.low")}</SelectItem>
                  <SelectItem value="medium">{t("chatPanel.reasoningEffort.medium")}</SelectItem>
                  <SelectItem value="high">{t("chatPanel.reasoningEffort.high")}</SelectItem>
                  <SelectItem value="xhigh">{t("chatPanel.reasoningEffort.xhigh")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="chat-input">Message</Label>
            <Textarea id="chat-input" value={input} onChange={(event) => { isDefaultInputRef.current = false; setInput(event.target.value); }} className="min-h-32 rounded-md border-stone-200/70 bg-transparent shadow-none dark:border-white/10" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="chat-images">{t("chatPanel.imagesLabel")}</Label>
            <label htmlFor="chat-images" className="flex cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed border-stone-300 bg-stone-50/70 px-3 py-3 text-sm text-stone-600 transition hover:border-stone-400 hover:bg-stone-100 dark:border-white/10 dark:bg-white/[0.03] dark:text-stone-300 dark:hover:bg-white/[0.06]">
              <ImagePlus className="size-4" />
              {t("chatPanel.selectImages")}
            </label>
            <input id="chat-images" type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple className="sr-only" onChange={(event) => {
              void handleImagesChange(event.target.files);
              event.currentTarget.value = "";
            }} />
            {selectedImages.length ? (
              <div className="grid grid-cols-2 gap-2">
                {selectedImages.map((image) => (
                  <div key={image.id} className="group relative overflow-hidden rounded-md border border-stone-200 bg-white dark:border-white/10 dark:bg-white/[0.04]">
                    <img src={image.url} alt={image.name} className="aspect-square w-full object-cover" />
                    <button type="button" aria-label={t("chatPanel.removeImage", { name: image.name })} onClick={() => setSelectedImages((current) => current.filter((item) => item.id !== image.id))} className="absolute top-1 right-1 flex size-7 items-center justify-center rounded-md bg-white/90 text-stone-700 shadow-sm transition hover:bg-white dark:bg-stone-950/90 dark:text-stone-100">
                      <X className="size-4" />
                    </button>
                    <div className="absolute inset-x-0 bottom-0 truncate bg-white/90 px-2 py-1 text-xs text-stone-600 dark:bg-stone-950/90 dark:text-stone-300">{image.name}</div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => void sendChat()} disabled={loading || (!input.trim() && !selectedImages.length)}>
              {loading ? <LoaderCircle className="animate-spin" /> : <Send />}
              {t("chatPanel.send")}
            </Button>
            <Button size="sm" variant="outline" onClick={clearChat}>
              {t("chatPanel.clear")}
            </Button>
          </div>
          {error ? <div className="rounded-md border border-rose-200 bg-rose-50/60 px-3 py-2 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-300">{error}</div> : null}
          <Textarea value={raw ? pretty(raw) : "{\n  \"messages\": []\n}"} readOnly className="min-h-72 resize-none rounded-md border-stone-200/70 bg-stone-50/50 p-4 font-mono text-xs leading-5 text-stone-600 shadow-none dark:border-white/10 dark:bg-white/[0.03] dark:text-stone-300" />
        </div>
      </section>
      <section className="flex min-h-0 flex-col">
        <div className="border-b border-stone-200/70 pb-3 dark:border-white/10">
          <h2 className="text-sm font-medium text-stone-500 dark:text-stone-400">{t("chatPanel.title")}</h2>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-auto pt-4">
          {messages.length ? messages.map((message, index) => (
            <div key={`${message.role}-${index}`} className="space-y-1.5 text-sm">
              <div className="text-xs font-medium uppercase tracking-wide text-stone-400 dark:text-stone-500">{message.role}</div>
              {messageImages(message).length ? (
                <div className="flex flex-wrap gap-2">
                  {messageImages(message).map((url, imageIndex) => (
                    <img key={`${index}-${imageIndex}`} src={url} alt="" className="h-28 w-28 rounded-md border border-stone-200 object-cover dark:border-white/10" />
                  ))}
                </div>
              ) : null}
              {messageText(message) ? <div className="whitespace-pre-wrap leading-7 text-stone-700 dark:text-stone-300">{messageText(message)}</div> : null}
            </div>
          )) : (
            <div className="flex h-full items-center justify-center text-sm text-stone-400 dark:text-stone-500">{t("chatPanel.emptyConversation")}</div>
          )}
        </div>
      </section>
    </div>
  );
}
