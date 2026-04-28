"use client";

import localforage from "localforage";

import type { ImageModel } from "@/lib/api";

export type ImageConversationMode = "generate" | "edit";

export type StoredReferenceImage = {
  name: string;
  type: string;
  dataUrl: string;
};

export type StoredImage = {
  id: string;
  status?: "loading" | "success" | "error";
  b64_json?: string;
  error?: string;
};

export type ImageConversationStatus = "generating" | "success" | "error";

export type ImageConversationTurn = {
  id: string;
  prompt: string;
  optimizedPrompt?: string;
  promptOptimizer?: string;
  model: ImageModel;
  mode?: ImageConversationMode;
  referenceImages?: StoredReferenceImage[];
  count: number;
  images: StoredImage[];
  createdAt: string;
  status: ImageConversationStatus;
  error?: string;
};

export type ImageConversation = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  turns: ImageConversationTurn[];
};

const imageConversationStorage = localforage.createInstance({
  name: "chatgpt2api",
  storeName: "image_conversations",
});

const IMAGE_CONVERSATIONS_KEY = "items";

function normalizeStoredImage(image: StoredImage): StoredImage {
  if (image.status === "loading" || image.status === "error" || image.status === "success") {
    return image;
  }
  return {
    ...image,
    status: image.b64_json ? "success" : "loading",
  };
}

function normalizeTurn(turn: ImageConversationTurn): ImageConversationTurn {
  return {
    ...turn,
    model: turn.model === "gpt-image-1" ? "gpt-image-1" : "gpt-image-2",
    mode: turn.mode === "edit" ? "edit" : "generate",
    images: (turn.images || []).map(normalizeStoredImage),
  };
}

function buildLegacyTurn(conversation: Record<string, unknown>): ImageConversationTurn {
  const model = conversation.model === "gpt-image-1" ? "gpt-image-1" : "gpt-image-2";
  return normalizeTurn({
    id: String(conversation.id || "legacy-turn"),
    prompt: String(conversation.prompt || ""),
    optimizedPrompt: typeof conversation.optimizedPrompt === "string" ? conversation.optimizedPrompt : undefined,
    promptOptimizer: typeof conversation.promptOptimizer === "string" ? conversation.promptOptimizer : undefined,
    model,
    mode: conversation.mode === "edit" ? "edit" : "generate",
    referenceImages: Array.isArray(conversation.referenceImages)
      ? (conversation.referenceImages as StoredReferenceImage[])
      : [],
    count: Math.max(1, Number(conversation.count) || 1),
    images: Array.isArray(conversation.images) ? (conversation.images as StoredImage[]) : [],
    createdAt: String(conversation.createdAt || new Date(0).toISOString()),
    status: conversation.status === "generating" || conversation.status === "error" ? conversation.status : "success",
    error: typeof conversation.error === "string" ? conversation.error : undefined,
  });
}

function normalizeConversation(conversation: ImageConversation): ImageConversation {
  const rawConversation = conversation as ImageConversation & Record<string, unknown>;
  const normalizedTurns = Array.isArray(rawConversation.turns) && rawConversation.turns.length > 0
    ? rawConversation.turns.map((turn) => normalizeTurn(turn))
    : [buildLegacyTurn(rawConversation)];
  normalizedTurns.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  const createdAt = String(rawConversation.createdAt || normalizedTurns[0]?.createdAt || new Date(0).toISOString());
  const updatedAt = String(
    rawConversation.updatedAt || normalizedTurns[normalizedTurns.length - 1]?.createdAt || createdAt,
  );

  return {
    id: String(rawConversation.id || ""),
    title: String(rawConversation.title || ""),
    createdAt,
    updatedAt,
    turns: normalizedTurns,
  };
}

function getConversationSortTime(conversation: ImageConversation): string {
  return conversation.updatedAt || conversation.createdAt;
}

export async function listImageConversations(): Promise<ImageConversation[]> {
  const items = (await imageConversationStorage.getItem<ImageConversation[]>(IMAGE_CONVERSATIONS_KEY)) || [];
  return items.map(normalizeConversation).sort((a, b) => getConversationSortTime(b).localeCompare(getConversationSortTime(a)));
}

export async function saveImageConversation(conversation: ImageConversation): Promise<void> {
  const items = await listImageConversations();
  const nextItems = [normalizeConversation(conversation), ...items.filter((item) => item.id !== conversation.id)];
  nextItems.sort((a, b) => getConversationSortTime(b).localeCompare(getConversationSortTime(a)));
  await imageConversationStorage.setItem(IMAGE_CONVERSATIONS_KEY, nextItems);
}

export async function deleteImageConversation(id: string): Promise<void> {
  const items = await listImageConversations();
  await imageConversationStorage.setItem(
    IMAGE_CONVERSATIONS_KEY,
    items.filter((item) => item.id !== id),
  );
}

export async function clearImageConversations(): Promise<void> {
  await imageConversationStorage.removeItem(IMAGE_CONVERSATIONS_KEY);
}
