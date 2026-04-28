"use client";

import { LoaderCircle, MessageSquarePlus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ImageConversation } from "@/store/image-conversations";

type ImageSidebarProps = {
  conversations: ImageConversation[];
  isLoadingHistory: boolean;
  generatingIds: Set<string>;
  selectedConversationId: string | null;
  onCreateDraft: () => void;
  onClearHistory: () => void | Promise<void>;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void | Promise<void>;
  formatConversationTime: (value: string) => string;
};

export function ImageSidebar({
  conversations,
  isLoadingHistory,
  generatingIds,
  selectedConversationId,
  onCreateDraft,
  onClearHistory,
  onSelectConversation,
  onDeleteConversation,
  formatConversationTime,
}: ImageSidebarProps) {
  return (
    <aside className="min-h-0 border-r border-stone-200/70 pr-3">
      <div className="flex h-full min-h-0 flex-col gap-3 py-2">
        <div className="flex items-center gap-2">
          <Button className="h-10 flex-1 rounded-xl bg-stone-950 text-white hover:bg-stone-800" onClick={onCreateDraft}>
            <MessageSquarePlus className="size-4" />
            新建对话
          </Button>
          <Button
            variant="outline"
            className="h-10 rounded-xl border-stone-200 bg-white/85 px-3 text-stone-600 hover:bg-white"
            onClick={() => void onClearHistory()}
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
            <div className="px-2 py-3 text-sm leading-6 text-stone-500">还没有图片记录，输入提示词后会在这里显示。</div>
          ) : (
            conversations.map((conversation) => {
              const active = conversation.id === selectedConversationId;
              const generating = generatingIds.has(conversation.id);
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
                    onClick={() => onSelectConversation(conversation.id)}
                    className="block w-full pr-8 text-left"
                  >
                    <div className="flex items-center gap-1.5 truncate text-sm font-semibold">
                      {generating && <LoaderCircle className="size-3.5 shrink-0 animate-spin text-stone-400" />}
                      <span className="truncate">{conversation.title}</span>
                    </div>
                    <div className={cn("mt-1 text-xs", active ? "text-stone-500" : "text-stone-400")}>
                      {formatConversationTime(conversation.updatedAt || conversation.createdAt)}
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => void onDeleteConversation(conversation.id)}
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
  );
}
