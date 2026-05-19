"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle, MessageSquarePlus, Send, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { createChatCompletion, type ChatMessage } from "@/lib/api";
import { useAuthGuard } from "@/lib/use-auth-guard";

type Conversation = {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
};

const ACTIVE_CONVERSATION_STORAGE_KEY = "chatgpt2api:chat_active_conversation_id";
const CONVERSATIONS_STORAGE_KEY = "chatgpt2api:chat_conversations";

function createId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function buildConversationTitle(firstMessage: string) {
  const trimmed = firstMessage.trim();
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

function sortConversations(conversations: Conversation[]) {
  return [...conversations].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

async function loadConversations(): Promise<Conversation[]> {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const stored = window.localStorage.getItem(CONVERSATIONS_STORAGE_KEY);
    if (!stored) {
      return [];
    }
    return JSON.parse(stored) as Conversation[];
  } catch {
    return [];
  }
}

async function saveConversations(conversations: Conversation[]) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(CONVERSATIONS_STORAGE_KEY, JSON.stringify(sortConversations(conversations)));
}

async function deleteConversationById(items: Conversation[], id: string): Promise<Conversation[]> {
  const next = items.filter((c) => c.id !== id);
  await saveConversations(next);
  return next;
}

async function clearAllConversations(): Promise<Conversation[]> {
  await saveConversations([]);
  return [];
}

async function renameConversationById(items: Conversation[], id: string, title: string): Promise<Conversation[]> {
  const next = items.map((c) => (c.id === id ? { ...c, title } : c));
  await saveConversations(next);
  return next;
}

async function upsertConversation(items: Conversation[], conversation: Conversation): Promise<Conversation[]> {
  const existingIndex = items.findIndex((c) => c.id === conversation.id);
  let next: Conversation[];
  if (existingIndex >= 0) {
    next = [...items];
    next[existingIndex] = conversation;
  } else {
    next = [conversation, ...items];
  }
  await saveConversations(next);
  return sortConversations(next);
}

export default function ChatPage() {
  const { isAdmin } = useAuthGuard();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  const selectedConversation = conversations.find((c) => c.id === selectedConversationId) ?? null;

  useEffect(() => {
    let cancelled = false;
    const loadHistory = async () => {
      try {
        const items = await loadConversations();
        if (cancelled) return;
        setConversations(items);
        const storedId = typeof window !== "undefined" ? window.localStorage.getItem(ACTIVE_CONVERSATION_STORAGE_KEY) : null;
        const nextId = (storedId && items.some((c) => c.id === storedId) ? storedId : null) ?? items[0]?.id ?? null;
        setSelectedConversationId(nextId);
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

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (selectedConversationId) {
      window.localStorage.setItem(ACTIVE_CONVERSATION_STORAGE_KEY, selectedConversationId);
    } else {
      window.localStorage.removeItem(ACTIVE_CONVERSATION_STORAGE_KEY);
    }
  }, [selectedConversationId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [selectedConversation?.messages.length]);

  const handleCreateNew = useCallback(() => {
    const newConversation: Conversation = {
      id: createId(),
      title: "新对话",
      messages: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    setConversations((prev) => sortConversations([newConversation, ...prev]));
    setSelectedConversationId(newConversation.id);
    setInput("");
    textareaRef.current?.focus();
  }, []);

  const handleDeleteConversation = useCallback(async (id: string) => {
    try {
      const next = await deleteConversationById(conversations, id);
      setConversations(next);
      if (selectedConversationId === id) {
        setSelectedConversationId(next[0]?.id ?? null);
      }
      toast.success("已删除对话");
    } catch {
      toast.error("删除对话失败");
    }
  }, [conversations, selectedConversationId]);

  const handleClearHistory = useCallback(async () => {
    try {
      const next = await clearAllConversations();
      setConversations(next);
      setSelectedConversationId(null);
      toast.success("已清空历史记录");
    } catch {
      toast.error("清空历史失败");
    }
  }, []);

  const handleRenameConversation = useCallback(async (id: string, title: string) => {
    try {
      const next = await renameConversationById(conversations, id, title);
      setConversations(next);
      setEditingId(null);
      setEditingTitle("");
      toast.success("已重命名");
    } catch {
      toast.error("重命名失败");
    }
  }, [conversations]);

  const handleSubmit = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading || !selectedConversationId) return;

    const userMessage: ChatMessage = { role: "user", content: trimmed };
    const updatedConversation = conversations.find((c) => c.id === selectedConversationId);
    if (!updatedConversation) return;

    const isFirstMessage = updatedConversation.messages.length === 0;
    const newConversation: Conversation = {
      ...updatedConversation,
      title: isFirstMessage ? buildConversationTitle(trimmed) : updatedConversation.title,
      messages: [...updatedConversation.messages, userMessage],
      updatedAt: new Date().toISOString(),
    };

    setConversations((prev) => prev.map((c) => (c.id === selectedConversationId ? newConversation : c)));
    setInput("");
    setIsLoading(true);

    try {
      const allMessages: ChatMessage[] = [...newConversation.messages, userMessage];
      const response = await createChatCompletion(allMessages);
      const assistantMessage: ChatMessage = {
        role: "assistant",
        content: response.choices[0]?.message?.content ?? "抱歉，未能生成回复。",
      };

      const finalConversation: Conversation = {
        ...newConversation,
        messages: [...newConversation.messages, assistantMessage],
        updatedAt: new Date().toISOString(),
      };

      setConversations((prev) => {
        const sorted = upsertConversation(prev.filter((c) => c.id !== finalConversation.id), finalConversation);
        return sorted;
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "生成回复失败";
      toast.error(message);
      const errorConversation: Conversation = {
        ...newConversation,
        messages: [
          ...newConversation.messages,
          { role: "assistant", content: `错误：${message}` },
        ],
        updatedAt: new Date().toISOString(),
      };
      setConversations((prev) => prev.map((c) => (c.id === selectedConversationId ? errorConversation : c)));
    } finally {
      setIsLoading(false);
      setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    }
  }, [input, isLoading, selectedConversationId, conversations]);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        void handleSubmit();
      }
    },
    [handleSubmit]
  );

  const startRename = useCallback((conversation: Conversation, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(conversation.id);
    setEditingTitle(conversation.title);
  }, []);

  const commitRename = useCallback(() => {
    const trimmed = editingTitle.trim();
    if (editingId && trimmed) {
      void handleRenameConversation(editingId, trimmed);
    } else {
      setEditingId(null);
      setEditingTitle("");
    }
  }, [editingId, editingTitle, handleRenameConversation]);

  const cancelRename = useCallback(() => {
    setEditingId(null);
    setEditingTitle("");
  }, []);

  return (
    <div className="flex h-screen flex-col">
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="w-64 border-r border-stone-200 bg-stone-50 p-3 flex flex-col">
          <div className="mb-3 flex gap-2">
            <Button className="flex-1 rounded-xl bg-stone-950 text-white hover:bg-stone-800" onClick={handleCreateNew}>
              <MessageSquarePlus className="size-4" />
              <span className="hidden sm:inline">新建对话</span>
            </Button>
            <Button
              variant="outline"
              className="rounded-xl border-stone-200 bg-white/85 px-3 text-stone-600 hover:bg-white"
              onClick={handleClearHistory}
              disabled={conversations.length === 0}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto space-y-1">
            {isLoadingHistory ? (
              <div className="flex items-center gap-2 px-2 py-3 text-sm text-stone-500">
                <LoaderCircle className="size-4 animate-spin" />
                正在读取会话记录
              </div>
            ) : conversations.length === 0 ? (
              <div className="px-2 py-3 text-sm leading-6 text-stone-500">还没有对话记录。</div>
            ) : (
              conversations.map((conversation) => {
                const active = conversation.id === selectedConversationId;
                return (
                  <div
                    key={conversation.id}
                    className={`group relative w-full border-l-2 text-left transition px-3 py-2 ${
                      active
                        ? "border-stone-900 bg-black/[0.035] text-stone-950"
                        : "border-transparent text-stone-700 hover:border-stone-300 hover:bg-white/40"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => setSelectedConversationId(conversation.id)}
                      className="block w-full pr-8 text-left"
                    >
                      <div className="truncate font-semibold text-sm">
                        {editingId === conversation.id ? (
                          <input
                            value={editingTitle}
                            onChange={(e) => setEditingTitle(e.target.value)}
                            onBlur={commitRename}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") commitRename();
                              if (e.key === "Escape") cancelRename();
                            }}
                            onClick={(e) => e.stopPropagation()}
                            className="w-full truncate rounded border border-stone-300 bg-white px-1 py-0.5 text-sm outline-none focus:border-stone-500"
                          />
                        ) : (
                          <span className="truncate">{conversation.title}</span>
                        )}
                      </div>
                      <div className={`mt-1 text-xs ${active ? "text-stone-500" : "text-stone-400"}`}>
                        {conversation.messages.length} 条 · {formatConversationTime(conversation.updatedAt)}
                      </div>
                    </button>
                    <div className="absolute top-2 right-1.5 flex items-center gap-0.5 opacity-100 transition sm:opacity-0 sm:group-hover:opacity-100">
                      <button
                        type="button"
                        onClick={(e) => startRename(conversation, e)}
                        className="inline-flex size-7 items-center justify-center rounded-md text-stone-400 hover:bg-stone-100 hover:text-stone-600"
                        aria-label="重命名会话"
                      >
                        ✏️
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDeleteConversation(conversation.id)}
                        className="inline-flex size-7 items-center justify-center rounded-md text-stone-400 hover:bg-stone-100 hover:text-rose-500"
                        aria-label="删除会话"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </aside>

        {/* Main Chat Area */}
        <main className="flex-1 flex flex-col bg-white">
          {selectedConversation ? (
            <>
              <div className="flex-1 overflow-y-auto p-4 sm:p-6">
                <div className="mx-auto max-w-3xl space-y-4">
                  {selectedConversation.messages.length === 0 ? (
                    <div className="flex h-64 items-center justify-center text-center">
                      <div>
                        <h1 className="text-2xl font-semibold tracking-tight text-stone-950 sm:text-3xl">
                          开始对话吧
                        </h1>
                        <p className="mx-auto mt-3 max-w-md text-sm text-stone-500">
                          输入你的问题，AI 助手会为你解答。
                        </p>
                      </div>
                    </div>
                  ) : (
                    selectedConversation.messages.map((message, index) => (
                      <div
                        key={index}
                        className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                      >
                        <div
                          className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                            message.role === "user"
                              ? "bg-stone-950 text-white"
                              : "bg-stone-100 text-stone-900"
                          }`}
                        >
                          <div className="text-sm whitespace-pre-wrap">{message.content}</div>
                        </div>
                      </div>
                    ))
                  )}
                  {isLoading && (
                    <div className="flex justify-start">
                      <div className="max-w-[80%] rounded-2xl bg-stone-100 px-4 py-3 text-stone-900">
                        <div className="flex items-center gap-2">
                          <LoaderCircle className="size-4 animate-spin" />
                          <span className="text-sm">思考中...</span>
                        </div>
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>
              </div>

              {/* Input Area */}
              <div className="border-t border-stone-200 p-4">
                <div className="mx-auto max-w-3xl">
                  <div className="relative flex items-end gap-2">
                    <Textarea
                      ref={textareaRef}
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="输入消息... (Shift+Enter 换行)"
                      rows={1}
                      className="min-h-[52px] max-h-[200px] resize-none rounded-2xl border border-stone-200 bg-white px-4 py-3 pr-14 text-sm shadow-sm focus:border-stone-400 focus:ring-0"
                      style={{ height: "auto", minHeight: "52px" }}
                    />
                    <button
                      type="button"
                      onClick={() => void handleSubmit()}
                      disabled={!input.trim() || isLoading}
                      className="absolute right-2 bottom-2 inline-flex size-9 items-center justify-center rounded-full bg-stone-950 text-white transition hover:bg-stone-800 disabled:cursor-not-allowed disabled:bg-stone-300"
                      aria-label="发送消息"
                    >
                      <Send className="size-4" />
                    </button>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <h1 className="text-2xl font-semibold tracking-tight text-stone-950 sm:text-3xl">
                  选择一个对话或创建新对话
                </h1>
                <p className="mx-auto mt-3 max-w-md text-sm text-stone-500">
                  左侧列表显示你的历史对话，点击"新建对话"开始新的交流。
                </p>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
