"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { ImageLightbox } from "@/components/image-lightbox";
import { editImage, fetchAccounts, generateImage, type Account, type ImageModel } from "@/lib/api";
import { ImageComposer } from "@/app/image/components/image-composer";
import { ImageResults } from "@/app/image/components/image-results";
import { ImageSidebar } from "@/app/image/components/image-sidebar";
import {
  clearImageConversations,
  deleteImageConversation,
  listImageConversations,
  saveImageConversation,
  type ImageConversation,
  type ImageConversationMode,
  type StoredImage,
  type StoredReferenceImage,
} from "@/store/image-conversations";

const imageModelOptions: Array<{ label: string; value: ImageModel }> = [
  { label: "gpt-image-2", value: "gpt-image-2" },
  { label: "gpt-image-1", value: "gpt-image-1" },
];

function buildConversationTitle(prompt: string) {
  const trimmed = prompt.trim();
  if (trimmed.length <= 5) {
    return trimmed;
  }
  return `${trimmed.slice(0, 5)}...`;
}

function formatConversationTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatAvailableQuota(accounts: Account[]) {
  const availableAccounts = accounts.filter((account) => account.status !== "禁用");
  return String(availableAccounts.reduce((sum, account) => sum + Math.max(0, account.quota), 0));
}

async function normalizeConversationHistory(items: ImageConversation[]) {
  const normalized = items.map((item) =>
    item.status === "generating"
      ? {
          ...item,
          status: "error" as const,
          error: item.images.some((image) => image.status === "success")
            ? item.error || "生成已中断"
            : "页面已刷新，生成已中断",
          images: item.images.map((image) =>
            image.status === "loading"
              ? {
                  ...image,
                  status: "error" as const,
                  error: "页面已刷新，生成已中断",
                }
              : image,
          ),
        }
      : item,
  );

  await Promise.all(
    normalized
      .filter((item, index) => item !== items[index])
      .map((item) => saveImageConversation(item)),
  );

  return normalized;
}

function createId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("读取参考图失败"));
    reader.readAsDataURL(file);
  });
}

export default function ImagePage() {
  const didLoadQuotaRef = useRef(false);
  const resultsViewportRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [imagePrompt, setImagePrompt] = useState("");
  const [imageCount, setImageCount] = useState("1");
  const [imageMode, setImageMode] = useState<ImageConversationMode>("generate");
  const [imageModel, setImageModel] = useState<ImageModel>("gpt-image-2");
  const [referenceImageFiles, setReferenceImageFiles] = useState<File[]>([]);
  const [referenceImages, setReferenceImages] = useState<StoredReferenceImage[]>([]);
  const [conversations, setConversations] = useState<ImageConversation[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [generatingIds, setGeneratingIds] = useState<Set<string>>(new Set());
  const [availableQuota, setAvailableQuota] = useState("加载中");
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState(0);

  const selectedConversation = useMemo(
    () => conversations.find((item) => item.id === selectedConversationId) ?? null,
    [conversations, selectedConversationId],
  );
  const parsedCount = useMemo(() => Math.max(1, Math.min(10, Number(imageCount) || 1)), [imageCount]);
  const isSelectedGenerating = selectedConversationId !== null && generatingIds.has(selectedConversationId);
  const hasAnyGenerating = generatingIds.size > 0;

  const addGeneratingId = useCallback((id: string) => {
    setGeneratingIds((prev) => new Set(prev).add(id));
  }, []);

  const removeGeneratingId = useCallback((id: string) => {
    setGeneratingIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, []);

  const lightboxImages = useMemo(
    () =>
      (selectedConversation?.images ?? [])
        .filter((img): img is StoredImage & { b64_json: string } => img.status === "success" && !!img.b64_json)
        .map((img) => ({ id: img.id, src: `data:image/png;base64,${img.b64_json}` })),
    [selectedConversation],
  );

  const openLightbox = useCallback(
    (imageId: string) => {
      const idx = lightboxImages.findIndex((img) => img.id === imageId);
      if (idx >= 0) {
        setLightboxIndex(idx);
        setLightboxOpen(true);
      }
    },
    [lightboxImages],
  );

  useEffect(() => {
    let cancelled = false;

    const loadHistory = async () => {
      try {
        const items = await listImageConversations();
        const normalizedItems = await normalizeConversationHistory(items);
        if (cancelled) {
          return;
        }
        setConversations(normalizedItems);
      } catch (error) {
        const message = error instanceof Error ? error.message : "读取会话记录失败";
        toast.error(message);
      } finally {
        if (!cancelled) {
          setIsLoadingHistory(false);
        }
      }
    };

    void loadHistory();
    return () => {
      cancelled = true;
    };
  }, []);

  const loadQuota = useCallback(async () => {
    try {
      const data = await fetchAccounts();
      setAvailableQuota(formatAvailableQuota(data.items));
    } catch {
      setAvailableQuota((prev) => (prev === "加载中" ? "—" : prev));
    }
  }, []);

  useEffect(() => {
    if (didLoadQuotaRef.current) {
      return;
    }
    didLoadQuotaRef.current = true;

    const syncQuota = async () => {
      await loadQuota();
    };

    const handleFocus = () => {
      void syncQuota();
    };

    void syncQuota();
    window.addEventListener("focus", handleFocus);
    return () => {
      window.removeEventListener("focus", handleFocus);
    };
  }, [loadQuota]);

  useEffect(() => {
    if (!selectedConversation && !isSelectedGenerating) {
      return;
    }

    resultsViewportRef.current?.scrollTo({
      top: resultsViewportRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [selectedConversation, isSelectedGenerating]);

  const persistConversation = async (conversation: ImageConversation) => {
    setConversations((prev) => {
      const next = [conversation, ...prev.filter((item) => item.id !== conversation.id)];
      return next.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    });
    await saveImageConversation(conversation);
  };

  const updateConversation = async (
    conversationId: string,
    updater: (current: ImageConversation | null) => ImageConversation,
  ) => {
    let nextConversation: ImageConversation | null = null;

    setConversations((prev) => {
      const current = prev.find((item) => item.id === conversationId) ?? null;
      nextConversation = updater(current);
      const next = [nextConversation, ...prev.filter((item) => item.id !== conversationId)];
      return next.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    });

    if (nextConversation) {
      await saveImageConversation(nextConversation);
    }
  };

  const resetComposer = useCallback(() => {
    setImagePrompt("");
    setImageCount("1");
    setReferenceImageFiles([]);
    setReferenceImages([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  const handleCreateDraft = () => {
    setSelectedConversationId(null);
    resetComposer();
    textareaRef.current?.focus();
  };

  const handleDeleteConversation = async (id: string) => {
    const nextConversations = conversations.filter((item) => item.id !== id);
    setConversations(nextConversations);
    setSelectedConversationId((prev) => (prev === id ? null : prev));

    try {
      await deleteImageConversation(id);
    } catch (error) {
      const message = error instanceof Error ? error.message : "删除会话失败";
      toast.error(message);
      const items = await listImageConversations();
      setConversations(items);
    }
  };

  const handleClearHistory = async () => {
    try {
      await clearImageConversations();
      setConversations([]);
      setSelectedConversationId(null);
      toast.success("已清空历史记录");
    } catch (error) {
      const message = error instanceof Error ? error.message : "清空历史记录失败";
      toast.error(message);
    }
  };

  const appendReferenceImages = useCallback(async (files: File[]) => {
    if (files.length === 0) {
      return;
    }

    try {
      const previews = await Promise.all(
        files.map(async (file) => ({
          name: file.name,
          type: file.type || "image/png",
          dataUrl: await readFileAsDataUrl(file),
        })),
      );
      setReferenceImageFiles((prev) => [...prev, ...files]);
      setReferenceImages((prev) => [...prev, ...previews]);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "读取参考图失败";
      toast.error(message);
    }
  }, []);

  const handleReferenceImageChange = useCallback(async (files: File[]) => {
    if (files.length === 0) {
      setReferenceImageFiles([]);
      setReferenceImages([]);
      return;
    }

    await appendReferenceImages(files);
  }, [appendReferenceImages]);

  const handleRemoveReferenceImage = useCallback((index: number) => {
    setReferenceImageFiles((prev) => {
      const next = prev.filter((_, currentIndex) => currentIndex !== index);
      if (next.length === 0 && fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      return next;
    });
    setReferenceImages((prev) => prev.filter((_, currentIndex) => currentIndex !== index));
  }, []);

  const handleGenerateImage = async () => {
    const prompt = imagePrompt.trim();
    if (!prompt) {
      toast.error("请输入提示词");
      return;
    }

    if (imageMode === "edit" && referenceImageFiles.length === 0) {
      toast.error("请先上传参考图");
      return;
    }

    const now = new Date().toISOString();
    const conversationId = createId();
    const draftReferenceImages = imageMode === "edit" ? referenceImages : [];

    const draftConversation: ImageConversation = {
      id: conversationId,
      title: buildConversationTitle(prompt),
      prompt,
      model: imageModel,
      mode: imageMode,
      referenceImages: draftReferenceImages,
      count: parsedCount,
      images: Array.from({ length: parsedCount }, (_, index) => ({
        id: `${conversationId}-${index}`,
        status: "loading",
      })),
      createdAt: now,
      status: "generating",
    };

    addGeneratingId(conversationId);
    setSelectedConversationId(conversationId);
    resetComposer();

    try {
      await persistConversation(draftConversation);

      const tasks = Array.from({ length: parsedCount }, async (_, index) => {
        try {
          const data =
            imageMode === "edit" && referenceImageFiles.length > 0
              ? await editImage(referenceImageFiles, prompt, imageModel)
              : await generateImage(prompt, imageModel);
          const first = data.data?.[0];
          if (!first?.b64_json) {
            throw new Error(`第 ${index + 1} 张没有返回图片数据`);
          }

          const nextImage: StoredImage = {
            id: `${conversationId}-${index}`,
            status: "success",
            b64_json: first.b64_json,
          };

          await updateConversation(conversationId, (current) => ({
            ...(current ?? draftConversation),
            images: (current?.images ?? draftConversation.images).map((image) =>
              image.id === nextImage.id ? nextImage : image,
            ),
          }));

          return nextImage;
        } catch (error) {
          const message = error instanceof Error ? error.message : `第 ${index + 1} 张生成失败`;
          const failedImage: StoredImage = {
            id: `${conversationId}-${index}`,
            status: "error",
            error: message,
          };

          await updateConversation(conversationId, (current) => ({
            ...(current ?? draftConversation),
            images: (current?.images ?? draftConversation.images).map((image) =>
              image.id === failedImage.id ? failedImage : image,
            ),
          }));

          throw error;
        }
      });

      const settled = await Promise.allSettled(tasks);
      const successCount = settled.filter((item): item is PromiseFulfilledResult<StoredImage> => item.status === "fulfilled")
        .length;
      const failedCount = settled.length - successCount;

      if (successCount === 0) {
        const firstError = settled.find((item) => item.status === "rejected");
        throw new Error(firstError?.status === "rejected" ? String(firstError.reason) : "生成图片失败");
      }

      await updateConversation(conversationId, (current) => ({
        ...(current ?? draftConversation),
        status: failedCount > 0 ? "error" : "success",
        error: failedCount > 0 ? `其中 ${failedCount} 张生成失败` : undefined,
      }));
      await loadQuota();

      if (failedCount > 0) {
        toast.error(`已完成 ${successCount} 张，另有 ${failedCount} 张未生成成功`);
      } else {
        toast.success(imageMode === "edit" ? `已完成 ${successCount} 张图片编辑` : `已生成 ${successCount} 张图片`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : imageMode === "edit" ? "编辑图片失败" : "生成图片失败";
      await persistConversation({
        ...draftConversation,
        status: "error",
        error: message,
        images: draftConversation.images.map((image) =>
          image.status === "loading"
            ? {
                ...image,
                status: "error",
                error: message,
              }
            : image,
        ),
      });
      toast.error(message);
    } finally {
      removeGeneratingId(conversationId);
    }
  };

  return (
    <>
      <section className="mx-auto grid h-[calc(100vh-5rem)] min-h-0 w-full max-w-[1380px] grid-cols-1 gap-3 px-3 pb-6 lg:grid-cols-[240px_minmax(0,1fr)]">
        <ImageSidebar
          conversations={conversations}
          isLoadingHistory={isLoadingHistory}
          generatingIds={generatingIds}
          selectedConversationId={selectedConversationId}
          onCreateDraft={handleCreateDraft}
          onClearHistory={handleClearHistory}
          onSelectConversation={setSelectedConversationId}
          onDeleteConversation={handleDeleteConversation}
          formatConversationTime={formatConversationTime}
        />

        <div className="flex min-h-0 flex-col gap-4">
          <div
            ref={resultsViewportRef}
            className="hide-scrollbar min-h-0 flex-1 overflow-y-auto px-2 py-3 sm:px-4 sm:py-4"
          >
            <ImageResults
              selectedConversation={selectedConversation}
              isSelectedGenerating={isSelectedGenerating}
              openLightbox={openLightbox}
              formatConversationTime={formatConversationTime}
            />
          </div>

          <ImageComposer
            mode={imageMode}
            prompt={imagePrompt}
            model={imageModel}
            imageCount={imageCount}
            availableQuota={availableQuota}
            hasAnyGenerating={hasAnyGenerating}
            generatingCount={generatingIds.size}
            referenceImages={referenceImages}
            textareaRef={textareaRef}
            fileInputRef={fileInputRef}
            imageModelOptions={imageModelOptions}
            onModeChange={setImageMode}
            onPromptChange={setImagePrompt}
            onModelChange={setImageModel}
            onImageCountChange={setImageCount}
            onSubmit={handleGenerateImage}
            onPickReferenceImage={() => fileInputRef.current?.click()}
            onReferenceImageChange={handleReferenceImageChange}
            onRemoveReferenceImage={handleRemoveReferenceImage}
          />
        </div>
      </section>

      <ImageLightbox
        images={lightboxImages}
        currentIndex={lightboxIndex}
        open={lightboxOpen}
        onOpenChange={setLightboxOpen}
        onIndexChange={setLightboxIndex}
      />
    </>
  );
}
