"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Clock3,
  LoaderCircle,
  Maximize2,
  MessageSquarePlus,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  editImageWithContext,
  fetchAccounts,
  generateImageWithContext,
  type ImageConversationContext,
  type ImageModel,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  clearImageConversations,
  deleteImageConversation,
  listImageConversations,
  saveImageConversation,
  type ImageConversation,
  type ImageTurn,
  type ImageTurnStatus,
  type SourceImage,
  type SourceStrategy,
  type StoredImage,
} from "@/store/image-conversations";

const imageModelOptions: Array<{ label: string; value: ImageModel }> = [
  { label: "gpt-image-1", value: "gpt-image-1" },
  { label: "gpt-image-2", value: "gpt-image-2" },
];

type ComposerReference =
  | { type: "none" }
  | { type: "latest" }
  | { type: "explicit"; sourceImage: SourceImage };

type PreviewState = {
  images: string[];
  index: number;
  title: string;
};

const activeConversationQueueIds = new Set<string>();
const ACTIVE_CONVERSATION_STORAGE_KEY = "chatgpt2api:image_active_conversation_id";

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

function isUnlimitedImageQuotaAccount(account: { type?: string | null }) {
  return account.type === "Pro" || account.type === "ProLite";
}

function formatAvailableQuota(
  accounts: Array<{ quota: number; status: string; type?: string | null; imageQuotaUnknown?: boolean }>,
) {
  const availableAccounts = accounts.filter((account) => account.status !== "禁用");
  if (availableAccounts.some(isUnlimitedImageQuotaAccount)) {
    return "∞";
  }
  if (availableAccounts.some((account) => account.imageQuotaUnknown)) {
    return "未知";
  }
  return String(availableAccounts.reduce((sum, account) => sum + Math.max(0, account.quota), 0));
}

function createId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function dataUrlToFile(dataUrl: string, fileName: string) {
  const [header, content] = dataUrl.split(",", 2);
  const mimeMatch = header.match(/data:(.*?);base64/);
  const mimeType = mimeMatch?.[1] || "image/png";
  const binary = atob(content || "");
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new File([bytes], fileName, { type: mimeType });
}

function fileToDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("读取图片失败"));
    reader.readAsDataURL(file);
  });
}

function buildSourceImageFromResult(b64Json: string, fileName: string): SourceImage {
  return {
    dataUrl: `data:image/png;base64,${b64Json}`,
    fileName,
  };
}

function getSourceImageFromStoredImage(image: StoredImage, fileName: string) {
  if (!image.b64_json) {
    return null;
  }
  return buildSourceImageFromResult(image.b64_json, fileName);
}

function getLatestSuccessfulSourceFromConversation(conversation: ImageConversation | null) {
  if (!conversation) {
    return null;
  }
  for (let turnIndex = conversation.turns.length - 1; turnIndex >= 0; turnIndex -= 1) {
    const turn = conversation.turns[turnIndex];
    for (let imageIndex = turn.images.length - 1; imageIndex >= 0; imageIndex -= 1) {
      const image = turn.images[imageIndex];
      const sourceImage = getSourceImageFromStoredImage(
        image,
        `conversation-${conversation.id}-turn-${turn.id}-image-${imageIndex + 1}.png`,
      );
      if (sourceImage) {
        return sourceImage;
      }
    }
  }
  return null;
}

function getConversationStats(conversation: ImageConversation | null) {
  if (!conversation) {
    return { queued: 0, running: 0 };
  }
  return conversation.turns.reduce(
    (acc, turn) => {
      if (turn.status === "queued") {
        acc.queued += 1;
      } else if (turn.status === "generating") {
        acc.running += 1;
      }
      return acc;
    },
    { queued: 0, running: 0 },
  );
}

function getTurnStatusLabel(status: ImageTurnStatus) {
  if (status === "queued") return "排队中";
  if (status === "generating") return "处理中";
  if (status === "success") return "已完成";
  return "失败";
}

function getSuccessfulTurnImageUrls(turn: ImageTurn) {
  return turn.images
    .filter((image) => image.status === "success" && image.b64_json)
    .map((image) => `data:image/png;base64,${image.b64_json}`);
}

function getConversationUpstreamContext(conversation: ImageConversation | null): ImageConversationContext | undefined {
  if (!conversation) {
    return undefined;
  }
  const accountId = conversation.accountId || undefined;
  const upstreamConversationId = conversation.upstreamConversationId || undefined;
  const upstreamParentMessageId = conversation.upstreamParentMessageId || undefined;
  if (!accountId && !upstreamConversationId && !upstreamParentMessageId) {
    return undefined;
  }
  return {
    accountId,
    upstreamConversationId,
    upstreamParentMessageId,
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
      const nextStatus: ImageTurnStatus = failedCount > 0 ? "error" : successCount > 0 ? "success" : "queued";
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
    return changed ? { ...conversation, turns, updatedAt: turns.at(-1)?.createdAt || conversation.updatedAt } : conversation;
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
  const dragDepthRef = useRef(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const resultsViewportRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const conversationsRef = useRef<ImageConversation[]>([]);
  const [imagePrompt, setImagePrompt] = useState("");
  const [imageCount, setImageCount] = useState("1");
  const [imageModel, setImageModel] = useState<ImageModel>("gpt-image-2");
  const [composerReference, setComposerReference] = useState<ComposerReference>({ type: "none" });
  const [isDraggingImage, setIsDraggingImage] = useState(false);
  const [conversations, setConversations] = useState<ImageConversation[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [availableQuota, setAvailableQuota] = useState("加载中");
  const [previewState, setPreviewState] = useState<PreviewState | null>(null);

  const parsedCount = useMemo(() => Math.max(1, Math.min(10, Number(imageCount) || 1)), [imageCount]);
  const selectedConversation = useMemo(
    () => conversations.find((item) => item.id === selectedConversationId) ?? null,
    [conversations, selectedConversationId],
  );
  const selectedConversationStats = useMemo(
    () => getConversationStats(selectedConversation),
    [selectedConversation],
  );
  const resolvedComposerSource = useMemo(() => {
    if (composerReference.type === "explicit") {
      return composerReference.sourceImage;
    }
    if (composerReference.type === "latest") {
      return getLatestSuccessfulSourceFromConversation(selectedConversation);
    }
    return null;
  }, [composerReference, selectedConversation]);
  const composerModeLabel = composerReference.type === "none" ? "文生图" : "连续编辑";

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
        if (nextSelectedConversationId) {
          const nextSelectedConversation =
            normalizedItems.find((conversation) => conversation.id === nextSelectedConversationId) ?? null;
          setComposerReference(nextSelectedConversation ? { type: "latest" } : { type: "none" });
        } else {
          setComposerReference({ type: "none" });
        }
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
    if (selectedConversationId && !conversations.some((conversation) => conversation.id === selectedConversationId)) {
      const fallbackConversationId = pickFallbackConversationId(conversations);
      setSelectedConversationId(fallbackConversationId);
      setComposerReference(fallbackConversationId ? { type: "latest" } : { type: "none" });
    }
  }, [conversations, selectedConversationId]);

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

  const handleCreateDraft = () => {
    setSelectedConversationId(null);
    setComposerReference({ type: "none" });
    setImagePrompt("");
    textareaRef.current?.focus();
  };

  const handleSelectConversation = (conversationId: string) => {
    const conversation = conversationsRef.current.find((item) => item.id === conversationId) ?? null;
    setSelectedConversationId(conversationId);
    setComposerReference(getLatestSuccessfulSourceFromConversation(conversation) ? { type: "latest" } : { type: "none" });
  };

  const handleDeleteConversation = async (id: string) => {
    const nextConversations = conversations.filter((item) => item.id !== id);
    setConversations(nextConversations);
    if (selectedConversationId === id) {
      setSelectedConversationId(null);
      setComposerReference({ type: "none" });
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
      setComposerReference({ type: "none" });
      setImagePrompt("");
      toast.success("已清空历史记录");
    } catch (error) {
      const message = error instanceof Error ? error.message : "清空历史记录失败";
      toast.error(message);
    }
  };

  const handlePickSourceFile = async (file: File) => {
    if (!file.type.startsWith("image/")) {
      toast.error("只能上传图片文件");
      return;
    }
    const dataUrl = await fileToDataUrl(file);
    setComposerReference({
      type: "explicit",
      sourceImage: {
        dataUrl,
        fileName: file.name,
      },
    });
    toast.success("已载入参考图，后续发送会自动按连续编辑处理");
  };

  const handleContinueEdit = (conversationId: string, image: StoredImage) => {
    const sourceImage = getSourceImageFromStoredImage(image, `conversation-${conversationId}.png`);
    if (!sourceImage) {
      return;
    }
    setSelectedConversationId(conversationId);
    setComposerReference({ type: "explicit", sourceImage });
    setImagePrompt("");
    textareaRef.current?.focus();
    toast.success("已把这张图设为当前参考图");
  };

  const openPreview = (images: string[], index: number, title: string) => {
    if (images.length === 0) {
      return;
    }
    setPreviewState({ images, index, title });
  };

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

      const resolvedSource =
        queuedTurn.sourceStrategy === "explicit"
          ? queuedTurn.sourceImage ?? null
          : queuedTurn.sourceStrategy === "latest"
            ? getLatestSuccessfulSourceFromConversation(snapshot)
            : null;
      if (queuedTurn.sourceStrategy !== "none" && !resolvedSource) {
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
                    error: "未找到可继续编辑的最新图片，已停止本轮排队请求",
                    images: turn.images.map((image) =>
                      image.status === "loading"
                        ? { ...image, status: "error", error: "未找到上一轮生成出的可编辑图片" }
                        : image,
                    ),
                  }
                : turn,
            ),
          };
        });
        toast.error("未找到可继续编辑的最新图片，当前排队请求已停止");
        return;
      }

      const executionMode = queuedTurn.sourceStrategy === "none" ? "generate" : "edit";

      if (activeConversationQueueIds.has(conversationId)) {
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
                  mode: executionMode,
                  sourceImage: resolvedSource ?? undefined,
                  status: "generating",
                  error: undefined,
                }
              : turn,
          ),
        };
      });

      try {
        const sourceFile = resolvedSource
          ? dataUrlToFile(resolvedSource.dataUrl, resolvedSource.fileName || `${queuedTurn.id}.png`)
          : null;

        const pendingImages = queuedTurn.images.filter((image) => image.status === "loading");
        const initialUpstreamContext = getConversationUpstreamContext(snapshot);
        const shouldPersistUpstreamContext = pendingImages.length === 1;
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
        if (initialUpstreamContext?.upstreamConversationId && pendingImages.length > 1) {
          throw new Error("同一个上游连续对话暂只支持每轮生成 1 张图片");
        }

        const tasks = pendingImages.map(async (pendingImage) => {
          try {
            const currentConversation = conversationsRef.current.find((conversation) => conversation.id === conversationId) ?? snapshot;
            const requestContext = getConversationUpstreamContext(currentConversation);
            const data =
              executionMode === "edit" && sourceFile
                ? await editImageWithContext(sourceFile, queuedTurn.prompt, queuedTurn.model, requestContext)
                : await generateImageWithContext(queuedTurn.prompt, queuedTurn.model, requestContext);
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
                accountId: shouldPersistUpstreamContext ? data.account_id || conversation.accountId : conversation.accountId,
                upstreamConversationId: shouldPersistUpstreamContext
                  ? data.upstream_conversation_id || conversation.upstreamConversationId
                  : conversation.upstreamConversationId,
                upstreamParentMessageId: shouldPersistUpstreamContext
                  ? data.upstream_parent_message_id || conversation.upstreamParentMessageId
                  : conversation.upstreamParentMessageId,
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

        if (selectedConversationId === conversationId) {
          setComposerReference({ type: "latest" });
        }

        if (successCount === 0) {
          const firstError = settled.find((item) => item.status === "rejected");
          throw new Error(firstError?.status === "rejected" ? String(firstError.reason) : "生成图片失败");
        }

        if (failedCount > 0) {
          toast.error(`会话已完成 ${successCount} 张，另有 ${failedCount} 张未生成成功`);
        }
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
    [loadQuota, selectedConversationId, updateConversation],
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

    const targetConversation = selectedConversationId
      ? conversationsRef.current.find((conversation) => conversation.id === selectedConversationId) ?? null
      : null;
    if ((targetConversation?.upstreamConversationId || composerReference.type !== "none") && parsedCount > 1) {
      toast.error("连续对话暂只支持每轮 1 张图片");
      return;
    }
    const latestConversationSource = getLatestSuccessfulSourceFromConversation(targetConversation);

    let sourceStrategy: SourceStrategy = "none";
    let turnSourceImage: SourceImage | undefined;
    if (composerReference.type === "explicit") {
      sourceStrategy = "explicit";
      turnSourceImage = composerReference.sourceImage;
    } else if (composerReference.type === "latest") {
      sourceStrategy = "latest";
      turnSourceImage = latestConversationSource ?? undefined;
    }

    const now = new Date().toISOString();
    const conversationId = targetConversation?.id ?? createId();
    const turnId = createId();
    const draftTurn: ImageTurn = {
      id: turnId,
      prompt,
      model: imageModel,
      count: parsedCount,
      mode: sourceStrategy === "none" ? "generate" : "edit",
      sourceStrategy,
      sourceImage: turnSourceImage,
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
          accountId: undefined,
          upstreamConversationId: undefined,
          upstreamParentMessageId: undefined,
        };

    setSelectedConversationId(conversationId);
    setImagePrompt("");
    setComposerReference({ type: "latest" });

    await persistConversation(baseConversation);
    void runConversationQueue(conversationId);

    const targetStats = getConversationStats(baseConversation);
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
        <aside className="min-h-0 border-r border-stone-200/70 pr-3">
          <div className="flex h-full min-h-0 flex-col gap-3 py-2">
            <div className="flex items-center gap-2">
              <Button
                className="h-10 flex-1 rounded-xl bg-stone-950 text-white hover:bg-stone-800"
                onClick={handleCreateDraft}
              >
                <MessageSquarePlus className="size-4" />
                新建对话
              </Button>
              <Button
                variant="outline"
                className="h-10 rounded-xl border-stone-200 bg-white/85 px-3 text-stone-600 hover:bg-white"
                onClick={() => void handleClearHistory()}
                disabled={conversations.length === 0}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>

            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
              {isLoadingHistory ? (
                <div className="flex items-center gap-2 px-2 py-3 text-sm text-stone-500">
                  <LoaderCircle className="size-4 animate-spin" />
                  正在读取会话记录
                </div>
              ) : conversations.length === 0 ? (
                <div className="px-2 py-3 text-sm leading-6 text-stone-500">
                  还没有图片记录。拖图即可开始连续编辑；不拖图时，默认按文生图发送。
                </div>
              ) : (
                conversations.map((conversation) => {
                  const active = conversation.id === selectedConversationId;
                  const stats = getConversationStats(conversation);
                  return (
                    <div
                      key={conversation.id}
                      className={cn(
                        "group relative w-full border-l-2 px-3 py-3 text-left transition",
                        active
                          ? "border-stone-900 bg-black/[0.03] text-stone-950"
                          : "border-transparent text-stone-700 hover:border-stone-300 hover:bg-white/40",
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => handleSelectConversation(conversation.id)}
                        className="block w-full pr-8 text-left"
                      >
                        <div className="truncate text-sm font-semibold">{conversation.title}</div>
                        <div className={cn("mt-1 text-xs", active ? "text-stone-500" : "text-stone-400")}>
                          {conversation.turns.length} 轮 · {formatConversationTime(conversation.updatedAt)}
                        </div>
                        {stats.running > 0 || stats.queued > 0 ? (
                          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
                            {stats.running > 0 ? (
                              <span className="rounded-full bg-blue-50 px-2 py-1 text-blue-600">处理中 {stats.running}</span>
                            ) : null}
                            {stats.queued > 0 ? (
                              <span className="rounded-full bg-amber-50 px-2 py-1 text-amber-700">排队 {stats.queued}</span>
                            ) : null}
                          </div>
                        ) : null}
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDeleteConversation(conversation.id)}
                        className="absolute top-3 right-2 inline-flex size-7 items-center justify-center rounded-md text-stone-400 opacity-0 transition hover:bg-stone-100 hover:text-rose-500 group-hover:opacity-100"
                        aria-label="删除会话"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </aside>

        <div className="flex min-h-0 flex-col gap-4">
          <div ref={resultsViewportRef} className="hide-scrollbar min-h-0 flex-1 overflow-y-auto px-2 py-3 sm:px-4 sm:py-4">
            {!selectedConversation ? (
              <div className="flex h-full min-h-[420px] items-center justify-center text-center">
                <div className="w-full max-w-4xl">
                  <h1
                    className="text-3xl font-semibold tracking-tight text-stone-950 md:text-5xl"
                    style={{
                      fontFamily: '"Palatino Linotype","Book Antiqua","URW Palladio L","Times New Roman",serif',
                    }}
                  >
                    Turn images into a thread
                  </h1>
                  <p
                    className="mt-4 text-[15px] italic tracking-[0.01em] text-stone-500"
                    style={{
                      fontFamily: '"Palatino Linotype","Book Antiqua","URW Palladio L","Times New Roman",serif',
                    }}
                  >
                    同一对话会自动沿着上一张图继续追图；拖入新图时，会无感切换到基于该图编辑。
                  </p>
                </div>
              </div>
            ) : (
              <div className="mx-auto flex w-full max-w-[980px] flex-col gap-8">
                {selectedConversation.turns.map((turn, turnIndex) => {
                  const successfulTurnImages = getSuccessfulTurnImageUrls(turn);
                  return (
                    <div key={turn.id} className="flex flex-col gap-4">
                      <div className="flex justify-end">
                        <div className="max-w-[82%] rounded-[28px] bg-stone-950 px-5 py-4 text-[15px] leading-7 text-white shadow-sm">
                          <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-white/70">
                            <span className="rounded-full bg-white/10 px-2.5 py-1">第 {turnIndex + 1} 轮</span>
                            <span className="rounded-full bg-white/10 px-2.5 py-1">
                              {turn.mode === "edit" ? "连续编辑" : "文生图"}
                            </span>
                            <span className="rounded-full bg-white/10 px-2.5 py-1">{turn.model}</span>
                            <span className="rounded-full bg-white/10 px-2.5 py-1">
                              {getTurnStatusLabel(turn.status)}
                            </span>
                            <span className="rounded-full bg-white/10 px-2.5 py-1">
                              {formatConversationTime(turn.createdAt)}
                            </span>
                          </div>
                          <div>{turn.prompt}</div>
                        </div>
                      </div>

                      <div className="flex justify-start">
                        <div className="w-full rounded-[28px] border border-stone-200/80 bg-white/85 p-4 shadow-[0_14px_40px_rgba(28,25,23,0.05)]">
                          {turn.sourceImage ? (
                            <div className="mb-5 rounded-[22px] border border-stone-200/80 bg-stone-50/80 p-3">
                              <div className="mb-3 flex items-center gap-2 text-xs font-medium text-stone-500">
                                <Upload className="size-4" />
                                本轮参考图
                              </div>
                              <button
                                type="button"
                                onClick={() => openPreview([turn.sourceImage!.dataUrl], 0, "本轮参考图")}
                                className="group relative overflow-hidden rounded-[18px]"
                              >
                                <Image
                                  src={turn.sourceImage.dataUrl}
                                  alt="Source reference"
                                  width={768}
                                  height={768}
                                  unoptimized
                                  className="block h-auto max-h-[360px] w-auto max-w-full transition group-hover:scale-[1.01]"
                                />
                                <span className="absolute top-3 right-3 inline-flex items-center gap-1 rounded-full bg-black/60 px-2.5 py-1 text-xs text-white">
                                  <Maximize2 className="size-3.5" />
                                  放大
                                </span>
                              </button>
                            </div>
                          ) : null}

                          <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-stone-500">
                            <span className="rounded-full bg-stone-100 px-3 py-1">{turn.count} 张</span>
                            <span className="rounded-full bg-stone-100 px-3 py-1">{getTurnStatusLabel(turn.status)}</span>
                            {turn.status === "queued" ? (
                              <span className="rounded-full bg-amber-50 px-3 py-1 text-amber-700">等待当前对话前序任务完成</span>
                            ) : null}
                          </div>

                          <div className="columns-1 gap-4 space-y-4 sm:columns-2 xl:columns-3">
                            {turn.images.map((image, index) => (
                              <div key={image.id} className="break-inside-avoid overflow-hidden rounded-[22px] border border-stone-200/80 bg-stone-50/60">
                                {image.status === "success" && image.b64_json ? (
                                  <>
                                    <button
                                      type="button"
                                      onClick={() => openPreview(successfulTurnImages, successfulTurnImages.indexOf(`data:image/png;base64,${image.b64_json}`), `第 ${turnIndex + 1} 轮结果`)}
                                      className="group relative block w-full"
                                    >
                                      <Image
                                        src={`data:image/png;base64,${image.b64_json}`}
                                        alt={`Generated result ${index + 1}`}
                                        width={1024}
                                        height={1024}
                                        unoptimized
                                        className="block h-auto w-full transition group-hover:scale-[1.01]"
                                      />
                                      <span className="absolute top-3 right-3 inline-flex items-center gap-1 rounded-full bg-black/60 px-2.5 py-1 text-xs text-white">
                                        <Maximize2 className="size-3.5" />
                                        放大
                                      </span>
                                    </button>
                                    <div className="flex items-center justify-between gap-2 px-3 py-3">
                                      <div className="text-xs text-stone-500">结果 {index + 1}</div>
                                      <Button
                                        variant="outline"
                                        size="sm"
                                        className="rounded-full border-stone-200 bg-white text-stone-700 hover:bg-stone-50"
                                        onClick={() => handleContinueEdit(selectedConversation.id, image)}
                                      >
                                        <Sparkles className="size-4" />
                                        继续编辑
                                      </Button>
                                    </div>
                                  </>
                                ) : image.status === "error" ? (
                                  <div className="flex min-h-[320px] items-center justify-center bg-rose-50 px-6 py-8 text-center text-sm leading-6 text-rose-600">
                                    {image.error || "生成失败"}
                                  </div>
                                ) : turn.status === "queued" ? (
                                  <div className="flex min-h-[320px] flex-col items-center justify-center gap-3 bg-stone-100/80 px-6 py-8 text-center text-stone-500">
                                    <div className="rounded-full bg-white p-3 shadow-sm">
                                      <Clock3 className="size-5" />
                                    </div>
                                    <p className="text-sm">已进入当前对话队列...</p>
                                  </div>
                                ) : (
                                  <div className="flex min-h-[320px] flex-col items-center justify-center gap-3 bg-stone-100/80 px-6 py-8 text-center text-stone-500">
                                    <div className="rounded-full bg-white p-3 shadow-sm">
                                      <LoaderCircle className="size-5 animate-spin" />
                                    </div>
                                    <p className="text-sm">正在处理图片...</p>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>

                          {turn.status === "error" && turn.error ? (
                            <div className="mt-4 border-l-2 border-amber-300 bg-amber-50/70 px-4 py-3 text-sm leading-6 text-amber-700">
                              {turn.error}
                            </div>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="shrink-0 flex justify-center">
            <div
              className={cn(
                "overflow-hidden rounded-[32px] border bg-white shadow-[0_18px_48px_rgba(28,25,23,0.08)] transition",
                isDraggingImage ? "border-stone-950" : "border-stone-200/80",
              )}
              style={{ width: "min(980px, 100%)" }}
            >
              <div
                className="relative cursor-text"
                onClick={() => textareaRef.current?.focus()}
                onDragEnter={(event) => {
                  event.preventDefault();
                  dragDepthRef.current += 1;
                  setIsDraggingImage(true);
                }}
                onDragOver={(event) => {
                  event.preventDefault();
                  setIsDraggingImage(true);
                }}
                onDragLeave={(event) => {
                  event.preventDefault();
                  dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
                  if (dragDepthRef.current === 0) {
                    setIsDraggingImage(false);
                  }
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  dragDepthRef.current = 0;
                  setIsDraggingImage(false);
                  const file = event.dataTransfer.files?.[0];
                  if (file) {
                    void handlePickSourceFile(file);
                  }
                }}
              >
                {isDraggingImage ? (
                  <div className="pointer-events-none absolute inset-3 z-10 flex items-center justify-center rounded-[28px] border border-dashed border-stone-950 bg-stone-100/95 text-sm font-medium text-stone-900">
                    松开鼠标，把图片作为当前参考图继续编辑
                  </div>
                ) : null}

                {resolvedComposerSource ? (
                  <div className="flex items-center gap-3 px-5 pt-5">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        openPreview([resolvedComposerSource.dataUrl], 0, "当前参考图");
                      }}
                      className="group relative overflow-hidden rounded-[18px] border border-stone-200 bg-stone-50"
                    >
                      <Image
                        src={resolvedComposerSource.dataUrl}
                        alt="Current source"
                        width={120}
                        height={120}
                        unoptimized
                        className="block h-[92px] w-[92px] object-cover transition group-hover:scale-[1.02]"
                      />
                    </button>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-stone-900">{composerModeLabel}</div>
                    </div>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setComposerReference({ type: "none" });
                      }}
                      className="inline-flex size-9 items-center justify-center rounded-full bg-stone-100 text-stone-500 transition hover:bg-stone-200 hover:text-stone-900"
                      aria-label="清除参考图"
                    >
                      <X className="size-4" />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center justify-end gap-3 px-5 pt-5">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        fileInputRef.current?.click();
                      }}
                      className="inline-flex items-center gap-2 rounded-full border border-stone-200 bg-stone-50 px-4 py-2 text-sm font-medium text-stone-700 transition hover:bg-stone-100"
                    >
                      <Upload className="size-4" />
                      上传图片
                    </button>
                  </div>
                )}

                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) {
                      void handlePickSourceFile(file);
                      event.target.value = "";
                    }
                  }}
                />

                <Textarea
                  ref={textareaRef}
                  value={imagePrompt}
                  onChange={(event) => setImagePrompt(event.target.value)}
                  placeholder={
                    resolvedComposerSource
                      ? "继续描述你希望怎样修改当前图片"
                      : "输入你想要生成的画面，或直接把图片拖进来继续编辑"
                  }
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void handleSubmit();
                    }
                  }}
                  className="min-h-[148px] resize-none rounded-[32px] border-0 bg-transparent px-6 pt-6 pb-20 text-[15px] leading-7 text-stone-900 shadow-none placeholder:text-stone-400 focus-visible:ring-0"
                />

                <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-white via-white/95 to-transparent px-4 pb-4 pt-10 sm:px-6">
                  <div className="flex flex-wrap items-center gap-3">
                    <div className="rounded-full bg-stone-100 px-3 py-2 text-xs font-medium text-stone-600">
                      剩余额度 {availableQuota}
                    </div>
                    <Select value={imageModel} onValueChange={(value) => setImageModel(value as ImageModel)}>
                      <SelectTrigger className="h-10 w-[164px] rounded-full border-stone-200 bg-white text-sm font-medium text-stone-700 shadow-none focus-visible:ring-0">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {imageModelOptions.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>

                    <div className="flex items-center gap-2 rounded-full border border-stone-200 bg-white px-3 py-1">
                      <span className="text-sm font-medium text-stone-700">张数</span>
                      <Input
                        type="number"
                        min="1"
                        max="10"
                        step="1"
                        value={imageCount}
                        onChange={(event) => setImageCount(event.target.value)}
                        className="h-8 w-[64px] border-0 bg-transparent px-0 text-center text-sm font-medium text-stone-700 shadow-none focus-visible:ring-0"
                      />
                    </div>

                    {selectedConversation ? (
                      <div className="rounded-full bg-stone-100 px-3 py-2 text-xs font-medium text-stone-600">
                        当前对话：{selectedConversation.title}
                        {selectedConversationStats.running > 0 ? ` · 处理中 ${selectedConversationStats.running}` : ""}
                        {selectedConversationStats.queued > 0 ? ` · 排队 ${selectedConversationStats.queued}` : ""}
                      </div>
                    ) : (
                      <div className="rounded-full bg-stone-100 px-3 py-2 text-xs font-medium text-stone-600">
                        当前对话：发送后自动创建
                      </div>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => void handleSubmit()}
                    disabled={!imagePrompt.trim()}
                    className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-stone-950 text-white transition hover:bg-stone-800 disabled:cursor-not-allowed disabled:bg-stone-300"
                    aria-label="发送图片请求"
                  >
                    <ArrowUp className="size-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {previewState ? (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/82 p-4">
          <button
            type="button"
            className="absolute top-4 right-4 inline-flex size-11 items-center justify-center rounded-full bg-white/12 text-white transition hover:bg-white/20"
            onClick={() => setPreviewState(null)}
            aria-label="关闭预览"
          >
            <X className="size-5" />
          </button>
          {previewState.images.length > 1 ? (
            <>
              <button
                type="button"
                className="absolute left-4 inline-flex size-11 items-center justify-center rounded-full bg-white/12 text-white transition hover:bg-white/20"
                onClick={() =>
                  setPreviewState((current) =>
                    current
                      ? {
                          ...current,
                          index: current.index === 0 ? current.images.length - 1 : current.index - 1,
                        }
                      : current,
                  )
                }
                aria-label="上一张"
              >
                <ArrowLeft className="size-5" />
              </button>
              <button
                type="button"
                className="absolute right-4 inline-flex size-11 items-center justify-center rounded-full bg-white/12 text-white transition hover:bg-white/20"
                onClick={() =>
                  setPreviewState((current) =>
                    current
                      ? {
                          ...current,
                          index: current.index === current.images.length - 1 ? 0 : current.index + 1,
                        }
                      : current,
                  )
                }
                aria-label="下一张"
              >
                <ArrowRight className="size-5" />
              </button>
            </>
          ) : null}
          <div className="max-h-full max-w-[min(92vw,1400px)]">
            <div className="mb-3 text-center text-sm text-white/72">
              {previewState.title}
              {previewState.images.length > 1 ? ` · ${previewState.index + 1}/${previewState.images.length}` : ""}
            </div>
            <Image
              src={previewState.images[previewState.index]}
              alt="Preview"
              width={1600}
              height={1600}
              unoptimized
              className="max-h-[84vh] w-auto rounded-[20px] object-contain"
            />
          </div>
        </div>
      ) : null}
    </>
  );
}
