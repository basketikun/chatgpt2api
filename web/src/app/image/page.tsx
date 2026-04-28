"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { ImageComposer } from "@/app/image/components/image-composer";
import { ImageResults } from "@/app/image/components/image-results";
import { ImageSidebar } from "@/app/image/components/image-sidebar";
import { ImageLightbox } from "@/components/image-lightbox";
import { editImage, fetchRuntimeStatus, generateImage, optimizeImagePrompt, type ImageModel } from "@/lib/api";
import {
  clearImageConversations,
  deleteImageConversation,
  listImageConversations,
  saveImageConversation,
  type ImageConversation,
  type ImageConversationMode,
  type ImageConversationTurn,
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

function formatAvailableQuota(accounts: Array<{ status: string; quota: number }>) {
  const availableAccounts = accounts.filter((account) => account.status !== "禁用");
  return String(availableAccounts.reduce((sum, account) => sum + Math.max(0, account.quota), 0));
}

function createId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function sortConversations(items: ImageConversation[]) {
  return [...items].sort((a, b) => (b.updatedAt || b.createdAt).localeCompare(a.updatedAt || a.createdAt));
}

function updateTurn(
  conversation: ImageConversation,
  turnId: string,
  updater: (turn: ImageConversationTurn) => ImageConversationTurn,
) {
  return {
    ...conversation,
    turns: conversation.turns.map((turn) => (turn.id === turnId ? updater(turn) : turn)),
  };
}

function getLatestSuccessfulImages(conversation: ImageConversation | null): Array<StoredImage & { b64_json: string }> {
  if (!conversation) {
    return [];
  }

  for (let index = conversation.turns.length - 1; index >= 0; index -= 1) {
    const images = conversation.turns[index].images.filter(
      (image): image is StoredImage & { b64_json: string } => image.status === "success" && Boolean(image.b64_json),
    );
    if (images.length > 0) {
      return images;
    }
  }

  return [];
}

function buildReferenceImagesFromStoredImages(images: Array<StoredImage & { b64_json: string }>): StoredReferenceImage[] {
  return images.map((image, index) => ({
    name: `conversation-image-${index + 1}.png`,
    type: "image/png",
    dataUrl: `data:image/png;base64,${image.b64_json}`,
  }));
}

async function buildFilesFromStoredImages(
  images: Array<StoredImage & { b64_json: string }>,
): Promise<File[]> {
  return Promise.all(
    images.map(async (image, index) => {
      const dataUrl = `data:image/png;base64,${image.b64_json}`;
      const response = await fetch(dataUrl);
      const blob = await response.blob();
      return new File([blob], `conversation-image-${index + 1}.png`, {
        type: blob.type || "image/png",
      });
    }),
  );
}

async function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("读取参考图失败"));
    reader.readAsDataURL(file);
  });
}

async function normalizeConversationHistory(items: ImageConversation[]) {
  const normalized = items.map((conversation) => {
    let changed = false;
    const turns = conversation.turns.map((turn) => {
      if (turn.status !== "generating") {
        return turn;
      }

      changed = true;
      return {
        ...turn,
        status: "error" as const,
        error: turn.images.some((image) => image.status === "success")
          ? turn.error || "页面已刷新，本轮生成已中断。"
          : "页面已刷新，本轮生成已中断。",
        images: turn.images.map((image) =>
          image.status === "loading"
            ? {
                ...image,
                status: "error" as const,
                error: "页面已刷新，本轮生成已中断。",
              }
            : image,
        ),
      };
    });

    if (!changed) {
      return conversation;
    }

    return {
      ...conversation,
      updatedAt: turns[turns.length - 1]?.createdAt || conversation.updatedAt || conversation.createdAt,
      turns,
    };
  });

  await Promise.all(
    normalized
      .filter((item, index) => item !== items[index])
      .map((item) => saveImageConversation(item)),
  );

  return sortConversations(normalized);
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
  const [availableQuota, setAvailableQuota] = useState("加载中...");
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState(0);

  const selectedConversation = useMemo(
    () => conversations.find((item) => item.id === selectedConversationId) ?? null,
    [conversations, selectedConversationId],
  );
  const parsedCount = useMemo(() => Math.max(1, Math.min(10, Number(imageCount) || 1)), [imageCount]);
  const isSelectedGenerating = selectedConversationId !== null && generatingIds.has(selectedConversationId);
  const hasAnyGenerating = generatingIds.size > 0;

  const latestConversationImages = useMemo(
    () => getLatestSuccessfulImages(selectedConversation),
    [selectedConversation],
  );
  const implicitReferenceCount =
    imageMode === "edit" && referenceImages.length === 0 ? latestConversationImages.length : 0;

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
      (selectedConversation?.turns ?? []).flatMap((turn) =>
        turn.images
          .filter((img): img is StoredImage & { b64_json: string } => img.status === "success" && !!img.b64_json)
          .map((img) => ({ id: img.id, src: `data:image/png;base64,${img.b64_json}` })),
      ),
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
      const data = await fetchRuntimeStatus();
      setAvailableQuota(String(Math.max(0, data.available_quota)));
    } catch {
      setAvailableQuota((prev) => (prev === "加载中..." ? "--" : prev));
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
    setConversations((prev) => sortConversations([conversation, ...prev.filter((item) => item.id !== conversation.id)]));
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
      return sortConversations([nextConversation, ...prev.filter((item) => item.id !== conversationId)]);
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
    setImageMode("generate");
    resetComposer();
    textareaRef.current?.focus();
  };

  const handleSelectConversation = useCallback(
    (conversationId: string) => {
      setSelectedConversationId(conversationId);
      const conversation = conversations.find((item) => item.id === conversationId) ?? null;
      if (conversation && getLatestSuccessfulImages(conversation).length > 0) {
        setImageMode("edit");
      }
    },
    [conversations],
  );

  const handleDeleteConversation = async (id: string) => {
    const nextConversations = conversations.filter((item) => item.id !== id);
    setConversations(nextConversations);
    setSelectedConversationId((prev) => (prev === id ? null : prev));

    try {
      await deleteImageConversation(id);
      setImageMode("edit");
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

  const handleReferenceImageChange = useCallback(
    async (files: File[]) => {
      if (files.length === 0) {
        setReferenceImageFiles([]);
        setReferenceImages([]);
        return;
      }

      await appendReferenceImages(files);
    },
    [appendReferenceImages],
  );

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

    if (selectedConversationId && generatingIds.has(selectedConversationId)) {
      toast.error("当前会话仍在处理中，请稍后再继续。");
      return;
    }

    let uploadFiles = referenceImageFiles;
    let draftReferenceImages = imageMode === "edit" ? referenceImages : [];

    if (imageMode === "edit" && uploadFiles.length === 0) {
      if (latestConversationImages.length === 0) {
        toast.error("请先上传参考图，或先在当前会话里生成一轮图片。");
        return;
      }
      uploadFiles = await buildFilesFromStoredImages(latestConversationImages);
      draftReferenceImages = buildReferenceImagesFromStoredImages(latestConversationImages);
    }

    const now = new Date().toISOString();
    const conversationId = selectedConversationId ?? createId();
    const turnId = createId();
    let generationPrompt = prompt;
    let promptOptimizer: string | undefined;

    try {
      toast.info("正在优化提示词...");
      const optimized = await optimizeImagePrompt(prompt, imageMode);
      if (optimized.optimized_prompt.trim()) {
        generationPrompt = optimized.optimized_prompt.trim();
        promptOptimizer = optimized.optimizer;
        if (generationPrompt !== prompt) {
          toast.success(`提示词已优化：${prompt.length} -> ${generationPrompt.length} 字符`);
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "提示词优化失败";
      toast.warning(`提示词优化失败，继续使用原提示词：${message}`);
    }

    const draftTurn: ImageConversationTurn = {
      id: turnId,
      prompt,
      optimizedPrompt: generationPrompt !== prompt ? generationPrompt : undefined,
      promptOptimizer,
      model: imageModel,
      mode: imageMode,
      referenceImages: draftReferenceImages,
      count: parsedCount,
      images: Array.from({ length: parsedCount }, (_, index) => ({
        id: `${turnId}-${index}`,
        status: "loading",
      })),
      createdAt: now,
      status: "generating",
    };

    const draftConversation: ImageConversation = selectedConversation
      ? {
          ...selectedConversation,
          updatedAt: now,
          turns: [...selectedConversation.turns, draftTurn],
        }
      : {
          id: conversationId,
          title: buildConversationTitle(prompt),
          createdAt: now,
          updatedAt: now,
          turns: [draftTurn],
        };

    addGeneratingId(conversationId);
    setSelectedConversationId(conversationId);
    resetComposer();

    try {
      await persistConversation(draftConversation);

      const tasks = Array.from({ length: parsedCount }, async (_, index) => {
        try {
          const data =
            imageMode === "edit"
              ? await editImage(uploadFiles, generationPrompt, imageModel)
              : await generateImage(generationPrompt, imageModel, prompt);
          const first = data.data?.[0];
          if (!first?.b64_json) {
            throw new Error(`第 ${index + 1} 张没有返回图片数据`);
          }

          const nextImage: StoredImage = {
            id: `${turnId}-${index}`,
            status: "success",
            b64_json: first.b64_json,
          };

          await updateConversation(conversationId, (current) =>
            updateTurn(current ?? draftConversation, turnId, (turn) => ({
              ...turn,
              images: turn.images.map((image) => (image.id === nextImage.id ? nextImage : image)),
            })),
          );

          return nextImage;
        } catch (error) {
          const message = error instanceof Error ? error.message : `第 ${index + 1} 张生成失败`;
          const failedImage: StoredImage = {
            id: `${turnId}-${index}`,
            status: "error",
            error: message,
          };

          await updateConversation(conversationId, (current) =>
            updateTurn(current ?? draftConversation, turnId, (turn) => ({
              ...turn,
              images: turn.images.map((image) => (image.id === failedImage.id ? failedImage : image)),
            })),
          );

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
        updatedAt: now,
        turns: (current ?? draftConversation).turns.map((turn) =>
          turn.id === turnId
            ? {
                ...turn,
                status: failedCount > 0 ? "error" : "success",
                error: failedCount > 0 ? `其中 ${failedCount} 张生成失败` : undefined,
              }
            : turn,
        ),
      }));
      await loadQuota();

      if (failedCount > 0) {
        toast.error(`已完成 ${successCount} 张，另有 ${failedCount} 张未生成成功`);
      } else {
        toast.success(imageMode === "edit" ? `已完成 ${successCount} 张图片编辑` : `已生成 ${successCount} 张图片`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : imageMode === "edit" ? "编辑图片失败" : "生成图片失败";
      await updateConversation(conversationId, (current) =>
        updateTurn(current ?? draftConversation, turnId, (turn) => ({
          ...turn,
          status: "error",
          error: message,
          images: turn.images.map((image) =>
            image.status === "loading"
              ? {
                  ...image,
                  status: "error",
                  error: message,
                }
              : image,
          ),
        })),
      );
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
          onSelectConversation={handleSelectConversation}
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
            implicitReferenceCount={implicitReferenceCount}
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
