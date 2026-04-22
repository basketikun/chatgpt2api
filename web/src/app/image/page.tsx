"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { ImageComposer } from "@/app/image/components/image-composer";
import { ImageResults, type ImageLightboxItem } from "@/app/image/components/image-results";
import { ImageSidebar } from "@/app/image/components/image-sidebar";
import { ImageLightbox } from "@/components/image-lightbox";
import { editImage, fetchAccounts, generateImage, type Account, type ImageModel } from "@/lib/api";
import {
  clearImageConversations,
  deleteImageConversation,
  getImageConversationStats,
  listImageConversations,
  saveImageConversation,
  type ImageConversation,
  type ImageConversationMode,
  type ImageTurn,
  type ImageTurnStatus,
  type StoredImage,
  type StoredReferenceImage,
} from "@/store/image-conversations";

const ACTIVE_CONVERSATION_STORAGE_KEY = "chatgpt2api:image_active_conversation_id";
const activeConversationQueueIds = new Set<string>();

const imageModelOptions: Array<{ label: string; value: ImageModel }> = [
  { label: "gpt-image-1", value: "gpt-image-1" },
  { label: "gpt-image-2", value: "gpt-image-2" },
];

function buildConversationTitle(prompt: string) {
  const trimmed = prompt.trim();
  if (trimmed.length <= 12) {
    return trimmed;
  }
  return `${trimmed.slice(0, 12)}...`;
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

function createId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("读取参考图失败"));
    reader.readAsDataURL(file);
  });
}

function dataUrlToFile(dataUrl: string, fileName: string, mimeType?: string) {
  const [header, content] = dataUrl.split(",", 2);
  const matchedMimeType = header.match(/data:(.*?);base64/)?.[1];
  const binary = atob(content || "");
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new File([bytes], fileName, { type: mimeType || matchedMimeType || "image/png" });
}

function buildReferenceImageFromResult(image: StoredImage, fileName: string): StoredReferenceImage | null {
  if (!image.b64_json) {
    return null;
  }

  return {
    name: fileName,
    type: "image/png",
    dataUrl: `data:image/png;base64,${image.b64_json}`,
  };
}

function pickFallbackConversationId(conversations: ImageConversation[]) {
  const activeConversation = conversations.find((conversation) =>
    conversation.turns.some((turn) => turn.status === "queued" || turn.status === "generating"),
  );
  return activeConversation?.id ?? conversations[0]?.id ?? null;
}

async function recoverConversationHistory(items: ImageConversation[]) {
  const normalized = items.map((conversation) => {
    let changed = false;

    const turns = conversation.turns.map((turn) => {
      if (turn.status !== "queued" && turn.status !== "generating") {
        return turn;
      }

      const loadingCount = turn.images.filter((image) => image.status === "loading").length;
      if (loadingCount > 0 && turn.status === "generating") {
        changed = true;
        return {
          ...turn,
          status: "queued" as const,
          error: undefined,
        };
      }

      if (loadingCount > 0) {
        return turn;
      }

      const failedCount = turn.images.filter((image) => image.status === "error").length;
      const successCount = turn.images.filter((image) => image.status === "success").length;
      const nextStatus: ImageTurnStatus =
        failedCount > 0 ? "error" : successCount > 0 ? "success" : "queued";
      const nextError = failedCount > 0 ? turn.error || `其中 ${failedCount} 张未成功生成` : undefined;
      if (nextStatus === turn.status && nextError === turn.error) {
        return turn;
      }

      changed = true;
      return {
        ...turn,
        status: nextStatus,
        error: nextError,
      };
    });

    if (!changed) {
      return conversation;
    }

    const lastTurn = turns.length > 0 ? turns[turns.length - 1] : null;
    return {
      ...conversation,
      turns,
      updatedAt: lastTurn?.createdAt || conversation.updatedAt,
    };
  });

  await Promise.all(
    normalized
      .filter((conversation, index) => conversation !== items[index])
      .map((conversation) => saveImageConversation(conversation)),
  );

  return normalized;
}

export default function ImagePage() {
  const didLoadQuotaRef = useRef(false);
  const conversationsRef = useRef<ImageConversation[]>([]);
  const resultsViewportRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [imagePrompt, setImagePrompt] = useState("");
  const [imageCount, setImageCount] = useState("1");
  const [imageMode, setImageMode] = useState<ImageConversationMode>("generate");
  const [imageModel, setImageModel] = useState<ImageModel>("gpt-image-1");
  const [referenceImageFiles, setReferenceImageFiles] = useState<File[]>([]);
  const [referenceImages, setReferenceImages] = useState<StoredReferenceImage[]>([]);
  const [conversations, setConversations] = useState<ImageConversation[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [availableQuota, setAvailableQuota] = useState("加载中...");
  const [lightboxImages, setLightboxImages] = useState<ImageLightboxItem[]>([]);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState(0);

  const parsedCount = useMemo(() => Math.max(1, Math.min(10, Number(imageCount) || 1)), [imageCount]);
  const selectedConversation = useMemo(
    () => conversations.find((item) => item.id === selectedConversationId) ?? null,
    [conversations, selectedConversationId],
  );
  const selectedConversationStats = useMemo(
    () => getImageConversationStats(selectedConversation),
    [selectedConversation],
  );
  const activeTaskCount = useMemo(
    () =>
      conversations.reduce((sum, conversation) => {
        const stats = getImageConversationStats(conversation);
        return sum + stats.queued + stats.running;
      }, 0),
    [conversations],
  );

  useEffect(() => {
    conversationsRef.current = conversations;
  }, [conversations]);

  useEffect(() => {
    let cancelled = false;

    const loadHistory = async () => {
      try {
        const items = await listImageConversations();
        const normalizedItems = await recoverConversationHistory(items);
        if (cancelled) {
          return;
        }

        setConversations(normalizedItems);
        const storedConversationId =
          typeof window !== "undefined" ? window.localStorage.getItem(ACTIVE_CONVERSATION_STORAGE_KEY) : null;
        const nextSelectedConversationId =
          (storedConversationId && normalizedItems.some((conversation) => conversation.id === storedConversationId)
            ? storedConversationId
            : null) ?? pickFallbackConversationId(normalizedItems);
        setSelectedConversationId(nextSelectedConversationId);
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
      setAvailableQuota((prev) => (prev === "加载中..." ? "--" : prev));
    }
  }, []);

  useEffect(() => {
    if (didLoadQuotaRef.current) {
      return;
    }
    didLoadQuotaRef.current = true;

    const handleFocus = () => {
      void loadQuota();
    };

    void loadQuota();
    window.addEventListener("focus", handleFocus);
    return () => {
      window.removeEventListener("focus", handleFocus);
    };
  }, [loadQuota]);

  useEffect(() => {
    if (!selectedConversation) {
      return;
    }

    resultsViewportRef.current?.scrollTo({
      top: resultsViewportRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [selectedConversation?.updatedAt, selectedConversation?.turns.length, selectedConversation]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    if (selectedConversationId) {
      window.localStorage.setItem(ACTIVE_CONVERSATION_STORAGE_KEY, selectedConversationId);
    } else {
      window.localStorage.removeItem(ACTIVE_CONVERSATION_STORAGE_KEY);
    }
  }, [selectedConversationId]);

  useEffect(() => {
    if (selectedConversationId && !conversations.some((conversation) => conversation.id === selectedConversationId)) {
      setSelectedConversationId(pickFallbackConversationId(conversations));
    }
  }, [conversations, selectedConversationId]);

  const persistConversation = async (conversation: ImageConversation) => {
    setConversations((prev) => {
      const next = [conversation, ...prev.filter((item) => item.id !== conversation.id)];
      return next.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
    });
    await saveImageConversation(conversation);
  };

  const updateConversation = useCallback(
    async (conversationId: string, updater: (current: ImageConversation | null) => ImageConversation) => {
      let nextConversation: ImageConversation | null = null;

      setConversations((prev) => {
        const current = prev.find((item) => item.id === conversationId) ?? null;
        nextConversation = updater(current);
        const next = [nextConversation, ...prev.filter((item) => item.id !== conversationId)];
        return next.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
      });

      if (nextConversation) {
        await saveImageConversation(nextConversation);
      }
    },
    [],
  );

  const clearComposerInputs = useCallback(() => {
    setImagePrompt("");
    setImageCount("1");
    setReferenceImageFiles([]);
    setReferenceImages([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  const resetComposer = useCallback(() => {
    setImageMode("generate");
    clearComposerInputs();
  }, [clearComposerInputs]);

  const handleCreateDraft = () => {
    setSelectedConversationId(null);
    resetComposer();
    textareaRef.current?.focus();
  };

  const handleDeleteConversation = async (id: string) => {
    const nextConversations = conversations.filter((item) => item.id !== id);
    setConversations(nextConversations);
    if (selectedConversationId === id) {
      setSelectedConversationId(pickFallbackConversationId(nextConversations));
      resetComposer();
    }

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
      resetComposer();
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
      setImageMode("edit");
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

  const handleContinueEdit = useCallback(
    (conversationId: string, image: StoredImage) => {
      const nextReferenceImage = buildReferenceImageFromResult(
        image,
        `conversation-${conversationId}-${Date.now()}.png`,
      );
      if (!nextReferenceImage) {
        return;
      }

      setSelectedConversationId(conversationId);
      setImageMode("edit");
      setReferenceImages([nextReferenceImage]);
      setReferenceImageFiles([
        dataUrlToFile(nextReferenceImage.dataUrl, nextReferenceImage.name, nextReferenceImage.type),
      ]);
      setImagePrompt("");
      textareaRef.current?.focus();
      toast.success("已把这张结果图设为当前参考图");
    },
    [],
  );

  const openLightbox = useCallback((images: ImageLightboxItem[], index: number) => {
    if (images.length === 0) {
      return;
    }

    setLightboxImages(images);
    setLightboxIndex(Math.max(0, Math.min(index, images.length - 1)));
    setLightboxOpen(true);
  }, []);

  const runConversationQueue = useCallback(
    async (conversationId: string) => {
      if (activeConversationQueueIds.has(conversationId)) {
        return;
      }

      const snapshot = conversationsRef.current.find((conversation) => conversation.id === conversationId);
      const queuedTurn = snapshot?.turns.find((turn) => turn.status === "queued");
      if (!snapshot || !queuedTurn) {
        return;
      }

      activeConversationQueueIds.add(conversationId);
      await updateConversation(conversationId, (current) => {
        const conversation = current ?? snapshot;
        return {
          ...conversation,
          updatedAt: new Date().toISOString(),
          turns: conversation.turns.map((turn) =>
            turn.id === queuedTurn.id
              ? {
                  ...turn,
                  status: "generating",
                  error: undefined,
                }
              : turn,
          ),
        };
      });

      try {
        const referenceFiles = queuedTurn.referenceImages.map((image, index) =>
          dataUrlToFile(image.dataUrl, image.name || `${queuedTurn.id}-${index + 1}.png`, image.type),
        );
        const pendingImages = queuedTurn.images.filter((image) => image.status === "loading");

        if (queuedTurn.mode === "edit" && referenceFiles.length === 0) {
          throw new Error("未找到可用于继续编辑的参考图");
        }

        if (pendingImages.length === 0) {
          const existingFailedCount = queuedTurn.images.filter((image) => image.status === "error").length;
          const existingSuccessCount = queuedTurn.images.filter((image) => image.status === "success").length;
          await updateConversation(conversationId, (current) => {
            const conversation = current ?? snapshot;
            return {
              ...conversation,
              updatedAt: new Date().toISOString(),
              turns: conversation.turns.map((turn) =>
                turn.id === queuedTurn.id
                  ? {
                      ...turn,
                      status: existingFailedCount > 0 ? "error" : existingSuccessCount > 0 ? "success" : "queued",
                      error: existingFailedCount > 0 ? `其中 ${existingFailedCount} 张未成功生成` : undefined,
                    }
                  : turn,
              ),
            };
          });
          return;
        }

        const tasks = pendingImages.map(async (pendingImage) => {
          try {
            const data =
              queuedTurn.mode === "edit"
                ? await editImage(referenceFiles, queuedTurn.prompt, queuedTurn.model)
                : await generateImage(queuedTurn.prompt, queuedTurn.model);
            const first = data.data?.[0];
            if (!first?.b64_json) {
              throw new Error("未返回图片数据");
            }

            const nextImage: StoredImage = {
              id: pendingImage.id,
              status: "success",
              b64_json: first.b64_json,
            };

            await updateConversation(conversationId, (current) => {
              const conversation = current ?? snapshot;
              return {
                ...conversation,
                updatedAt: new Date().toISOString(),
                turns: conversation.turns.map((turn) =>
                  turn.id === queuedTurn.id
                    ? {
                        ...turn,
                        images: turn.images.map((image) => (image.id === nextImage.id ? nextImage : image)),
                      }
                    : turn,
                ),
              };
            });

            return nextImage;
          } catch (error) {
            const message = error instanceof Error ? error.message : "生成失败";
            const failedImage: StoredImage = {
              id: pendingImage.id,
              status: "error",
              error: message,
            };

            await updateConversation(conversationId, (current) => {
              const conversation = current ?? snapshot;
              return {
                ...conversation,
                updatedAt: new Date().toISOString(),
                turns: conversation.turns.map((turn) =>
                  turn.id === queuedTurn.id
                    ? {
                        ...turn,
                        images: turn.images.map((image) => (image.id === failedImage.id ? failedImage : image)),
                      }
                    : turn,
                ),
              };
            });

            throw error;
          }
        });

        const settled = await Promise.allSettled(tasks);
        const resumedSuccessCount = settled.filter(
          (item): item is PromiseFulfilledResult<StoredImage> => item.status === "fulfilled",
        ).length;
        const resumedFailedCount = settled.length - resumedSuccessCount;
        const existingSuccessCount = queuedTurn.images.filter((image) => image.status === "success").length;
        const existingFailedCount = queuedTurn.images.filter((image) => image.status === "error").length;
        const successCount = existingSuccessCount + resumedSuccessCount;
        const failedCount = existingFailedCount + resumedFailedCount;

        await updateConversation(conversationId, (current) => {
          const conversation = current ?? snapshot;
          return {
            ...conversation,
            updatedAt: new Date().toISOString(),
            turns: conversation.turns.map((turn) =>
              turn.id === queuedTurn.id
                ? {
                    ...turn,
                    status: failedCount > 0 ? "error" : "success",
                    error: failedCount > 0 ? `其中 ${failedCount} 张未成功生成` : undefined,
                  }
                : turn,
            ),
          };
        });

        await loadQuota();
      } catch (error) {
        const message = error instanceof Error ? error.message : "生成图片失败";
        await updateConversation(conversationId, (current) => {
          const conversation = current ?? snapshot;
          return {
            ...conversation,
            updatedAt: new Date().toISOString(),
            turns: conversation.turns.map((turn) =>
              turn.id === queuedTurn.id
                ? {
                    ...turn,
                    status: "error",
                    error: message,
                    images: turn.images.map((image) =>
                      image.status === "loading" ? { ...image, status: "error", error: message } : image,
                    ),
                  }
                : turn,
            ),
          };
        });
        toast.error(message);
      } finally {
        activeConversationQueueIds.delete(conversationId);
        for (const conversation of conversationsRef.current) {
          if (
            !activeConversationQueueIds.has(conversation.id) &&
            conversation.turns.some((turn) => turn.status === "queued")
          ) {
            void runConversationQueue(conversation.id);
          }
        }
      }
    },
    [loadQuota, updateConversation],
  );

  useEffect(() => {
    for (const conversation of conversations) {
      if (
        !activeConversationQueueIds.has(conversation.id) &&
        conversation.turns.some((turn) => turn.status === "queued")
      ) {
        void runConversationQueue(conversation.id);
      }
    }
  }, [conversations, runConversationQueue]);

  const handleSubmit = async () => {
    const prompt = imagePrompt.trim();
    if (!prompt) {
      toast.error("请输入提示词");
      return;
    }

    if (imageMode === "edit" && referenceImageFiles.length === 0) {
      toast.error("请先上传参考图");
      return;
    }

    const targetConversation = selectedConversationId
      ? conversationsRef.current.find((conversation) => conversation.id === selectedConversationId) ?? null
      : null;
    const now = new Date().toISOString();
    const conversationId = targetConversation?.id ?? createId();
    const turnId = createId();
    const draftTurn: ImageTurn = {
      id: turnId,
      prompt,
      model: imageModel,
      mode: imageMode,
      referenceImages: imageMode === "edit" ? referenceImages : [],
      count: parsedCount,
      images: Array.from({ length: parsedCount }, (_, index) => ({
        id: `${turnId}-${index}`,
        status: "loading" as const,
      })),
      createdAt: now,
      status: "queued",
    };

    const baseConversation: ImageConversation = targetConversation
      ? {
          ...targetConversation,
          updatedAt: now,
          turns: [...targetConversation.turns, draftTurn],
        }
      : {
          id: conversationId,
          title: buildConversationTitle(prompt),
          createdAt: now,
          updatedAt: now,
          turns: [draftTurn],
        };

    setSelectedConversationId(conversationId);
    clearComposerInputs();

    await persistConversation(baseConversation);
    void runConversationQueue(conversationId);

    const targetStats = getImageConversationStats(baseConversation);
    if (targetStats.running > 0 || targetStats.queued > 1) {
      toast.success("已加入当前对话队列");
    } else if (!targetConversation) {
      toast.success("已创建新对话并开始处理");
    } else {
      toast.success("已发送到当前对话");
    }
  };

  return (
    <>
      <section className="mx-auto grid h-[calc(100vh-5rem)] min-h-0 w-full max-w-[1380px] grid-cols-1 gap-3 px-3 pb-6 lg:grid-cols-[240px_minmax(0,1fr)]">
        <ImageSidebar
          conversations={conversations}
          isLoadingHistory={isLoadingHistory}
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
              onOpenLightbox={openLightbox}
              onContinueEdit={handleContinueEdit}
              formatConversationTime={formatConversationTime}
            />
          </div>

          <ImageComposer
            mode={imageMode}
            prompt={imagePrompt}
            model={imageModel}
            imageCount={imageCount}
            availableQuota={availableQuota}
            activeTaskCount={activeTaskCount}
            selectedConversationTitle={selectedConversation?.title ?? null}
            selectedConversationStats={selectedConversation ? selectedConversationStats : null}
            referenceImages={referenceImages}
            textareaRef={textareaRef}
            fileInputRef={fileInputRef}
            imageModelOptions={imageModelOptions}
            onModeChange={setImageMode}
            onPromptChange={setImagePrompt}
            onModelChange={setImageModel}
            onImageCountChange={setImageCount}
            onSubmit={handleSubmit}
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
