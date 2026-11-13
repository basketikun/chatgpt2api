"use client";

import { useState } from "react";
import { ImagePlus, LoaderCircle, Send, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n";
import { httpRequest } from "@/lib/request";

import { pretty, type ChatCompletionResponse, type ChatContentPart, type ChatMessage } from "./types";

type SelectedImage = {
  id: string;
  name: string;
  size: number;
  url: string;
};

const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

function readImage(file: File, locale: string): Promise<SelectedImage> {
  const isFa = locale === "fa";
  const isAr = locale === "ar";
  const isZh = locale === "zh";

  return new Promise((resolve, reject) => {
    if (!file.type.startsWith("image/")) {
      reject(new Error(isFa ? `${file.name} یک فایل تصویری نیست` : isAr ? `${file.name} ليس ملف صورة` : isZh ? `${file.name} 不是图片文件` : `${file.name} is not an image file`));
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      reject(new Error(isFa ? `${file.name} بزرگتر از ۱۰ مگابایت است` : isAr ? `${file.name} يتجاوز 10 ميغابايت` : isZh ? `${file.name} 超过 10MB` : `${file.name} exceeds 10MB`));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const url = String(reader.result || "");
      if (!url.startsWith("data:image/")) {
        reject(new Error(isFa ? `${file.name} بارگذاری نشد` : isAr ? `فشل قراءة ${file.name}` : isZh ? `${file.name} 读取失败` : `Failed to read ${file.name}`));
        return;
      }
      resolve({
        id: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(16).slice(2)}`,
        name: file.name,
        size: file.size,
        url,
      });
    };
    reader.onerror = () => reject(reader.error || new Error(isFa ? `${file.name} بارگذاری نشد` : isAr ? `فشل قراءة ${file.name}` : isZh ? `${file.name} 读取失败` : `Failed to read ${file.name}`));
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
  const { locale } = useI18n();
  const isFa = locale === "fa";
  const isAr = locale === "ar";
  const isZh = locale === "zh";

  const defaultGreeting = isFa
    ? "سلام، لطفاً به یاد داشته باشید که نام پروژه من chatgpt2api است."
    : isAr
      ? "مرحبا، تذكر أن اسم مشروعي هو chatgpt2api."
      : isZh
        ? "你好，先记住我的项目叫 chatgpt2api。"
        : "Hello, please remember my project is called chatgpt2api.";

  const [model, setModel] = useState("auto");
  const [reasoningEffort, setReasoningEffort] = useState("");
  const [input, setInput] = useState(defaultGreeting);
  const [selectedImages, setSelectedImages] = useState<SelectedImage[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [raw, setRaw] = useState<ChatCompletionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleImagesChange = async (files: FileList | null) => {
    if (!files?.length) return;
    setError("");
    try {
      const images = await Promise.all(Array.from(files).map((file) => readImage(file, locale)));
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
          <h2 className="text-sm font-medium text-stone-500 dark:text-stone-400">
            {isFa ? "درخواست" : isAr ? "الطلب" : isZh ? "请求" : "Request"}
          </h2>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-auto pt-4">
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_160px]">
            <div className="space-y-2">
              <Label htmlFor="chat-model">Model</Label>
              <Input id="chat-model" value={model} onChange={(event) => setModel(event.target.value)} className="rounded-md border-stone-200/70 bg-transparent shadow-none dark:border-white/10" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="chat-reasoning-effort">
                {isFa ? "شدت تفکر" : isAr ? "جهد التفكير" : isZh ? "思考强度" : "Reasoning Effort"}
              </Label>
              <Select value={reasoningEffort || "default"} onValueChange={(value) => setReasoningEffort(value === "default" ? "" : value)}>
                <SelectTrigger id="chat-reasoning-effort" className="h-10 rounded-md border-stone-200/70 bg-transparent shadow-none dark:border-white/10">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="default">{isFa ? "پیش‌فرض" : isAr ? "الافتراضي" : isZh ? "默认" : "Default"}</SelectItem>
                  <SelectItem value="low">{isFa ? "کم" : isAr ? "منخفض" : isZh ? "低" : "Low"}</SelectItem>
                  <SelectItem value="medium">{isFa ? "متوسط" : isAr ? "متوسط" : isZh ? "中" : "Medium"}</SelectItem>
                  <SelectItem value="high">{isFa ? "زیاد" : isAr ? "مرتفع" : isZh ? "高" : "High"}</SelectItem>
                  <SelectItem value="xhigh">{isFa ? "خیلی زیاد" : isAr ? "مرتفع جداً" : isZh ? "超高" : "Extra High"}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="chat-input">Message</Label>
            <Textarea id="chat-input" value={input} onChange={(event) => setInput(event.target.value)} className="min-h-32 rounded-md border-stone-200/70 bg-transparent shadow-none dark:border-white/10" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="chat-images">
              {isFa ? "تصاویر" : isAr ? "الصور" : isZh ? "图片" : "Images"}
            </Label>
            <label htmlFor="chat-images" className="flex cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed border-stone-300 bg-stone-50/70 px-3 py-3 text-sm text-stone-600 transition hover:border-stone-400 hover:bg-stone-100 dark:border-white/10 dark:bg-white/[0.03] dark:text-stone-300 dark:hover:bg-white/[0.06]">
              <ImagePlus className="size-4" />
              {isFa ? "انتخاب تصویر" : isAr ? "اختيار الصور" : isZh ? "选择图片" : "Select Images"}
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
                    <button type="button" aria-label={isFa ? `حذف ${image.name}` : isAr ? `إزالة ${image.name}` : isZh ? `移除 ${image.name}` : `Remove ${image.name}`} onClick={() => setSelectedImages((current) => current.filter((item) => item.id !== image.id))} className="absolute top-1 right-1 flex size-7 items-center justify-center rounded-md bg-white/90 text-stone-700 shadow-sm transition hover:bg-white dark:bg-stone-950/90 dark:text-stone-100">
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
              {isFa ? "ارسال" : isAr ? "إرسال" : isZh ? "发送" : "Send"}
            </Button>
            <Button size="sm" variant="outline" onClick={clearChat}>
              {isFa ? "پاک کردن" : isAr ? "مسح" : isZh ? "清空" : "Clear"}
            </Button>
          </div>
          {error ? <div className="rounded-md border border-rose-200 bg-rose-50/60 px-3 py-2 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-300">{error}</div> : null}
          <Textarea value={raw ? pretty(raw) : "{\n  \"messages\": []\n}"} readOnly dir="ltr" className="min-h-72 resize-none rounded-md border-stone-200/70 bg-stone-50/50 p-4 font-mono text-xs leading-5 text-stone-600 shadow-none dark:border-white/10 dark:bg-white/[0.03] dark:text-stone-300" />
        </div>
      </section>
      <section className="flex min-h-0 flex-col">
        <div className="border-b border-stone-200/70 pb-3 dark:border-white/10">
          <h2 className="text-sm font-medium text-stone-500 dark:text-stone-400">
            {isFa ? "گفتگو" : isAr ? "المحادثة" : isZh ? "对话" : "Conversation"}
          </h2>
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
            <div className="flex h-full items-center justify-center text-sm text-stone-400 dark:text-stone-500">
              {isFa ? "پیامی وجود ندارد" : isAr ? "لا توجد رسائل محادثة" : isZh ? "暂无对话消息" : "No messages yet"}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
