"use client";

import localforage from "localforage";

import type { ImageModel } from "@/lib/api";

export type ConversationMode = "generate" | "edit";
export type ImageConversationMode = ConversationMode;
export type SourceStrategy = "none" | "latest" | "explicit";

export type StoredImage = {
  id: string;
  status?: "loading" | "success" | "error";
  b64_json?: string;
  error?: string;
};

export type ImageTurnStatus = "queued" | "generating" | "success" | "error";

export type SourceImage = {
  dataUrl: string;
  fileName?: string;
};

export type ImageTurn = {
  id: string;
  prompt: string;
  model: ImageModel;
  count: number;
  mode: ConversationMode;
  sourceStrategy: SourceStrategy;
  images: StoredImage[];
  createdAt: string;
  status: ImageTurnStatus;
  error?: string;
  sourceImage?: SourceImage;
};

export type ImageConversation = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  turns: ImageTurn[];
  accountId?: string;
  upstreamConversationId?: string;
  upstreamParentMessageId?: string;
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

function normalizeTurn(turn: ImageTurn): ImageTurn {
  return {
    ...turn,
    mode: turn.mode === "edit" ? "edit" : "generate",
    sourceStrategy:
      turn.sourceStrategy === "explicit" || turn.sourceStrategy === "latest" ? turn.sourceStrategy : "none",
    images: (turn.images || []).map(normalizeStoredImage),
  };
}

function normalizeConversation(conversation: ImageConversation & Record<string, unknown>): ImageConversation {
  const turns = Array.isArray(conversation.turns)
    ? conversation.turns.map((turn) => normalizeTurn(turn as ImageTurn))
    : [
        normalizeTurn({
          id: String(conversation.id || `${Date.now()}`),
          prompt: String(conversation.prompt || ""),
          model: (conversation.model as ImageModel) || "gpt-image-1",
          count: Number(conversation.count || 1),
          mode: "generate",
          sourceStrategy: "none",
          images: Array.isArray(conversation.images) ? (conversation.images as StoredImage[]) : [],
          createdAt: String(conversation.createdAt || new Date().toISOString()),
          status: (conversation.status as ImageTurnStatus) || "success",
          error: typeof conversation.error === "string" ? conversation.error : undefined,
        }),
      ];

  return {
    id: String(conversation.id || `${Date.now()}`),
    title: String(conversation.title || ""),
    createdAt: String(conversation.createdAt || turns[0]?.createdAt || new Date().toISOString()),
    updatedAt: String(conversation.updatedAt || turns.at(-1)?.createdAt || new Date().toISOString()),
    turns,
    accountId: typeof conversation.accountId === "string" ? conversation.accountId : undefined,
    upstreamConversationId:
      typeof conversation.upstreamConversationId === "string" ? conversation.upstreamConversationId : undefined,
    upstreamParentMessageId:
      typeof conversation.upstreamParentMessageId === "string" ? conversation.upstreamParentMessageId : undefined,
  };
}

export async function listImageConversations(): Promise<ImageConversation[]> {
  const items =
    (await imageConversationStorage.getItem<Array<ImageConversation & Record<string, unknown>>>(IMAGE_CONVERSATIONS_KEY)) || [];
  return items.map(normalizeConversation).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export async function saveImageConversation(conversation: ImageConversation): Promise<void> {
  const items = await listImageConversations();
  const nextItems = [normalizeConversation(conversation), ...items.filter((item) => item.id !== conversation.id)];
  nextItems.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
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
