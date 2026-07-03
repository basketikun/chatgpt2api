export type SearchResult = {
  conversation_id: string;
  status: string;
  answer: string;
  sources: Array<{ title?: string; url?: string; snippet?: string; source_type?: string }>;
};

export type ChatMessage = {
  role: "system" | "user" | "assistant";
  content: string | ChatContentPart[];
};

export type ChatContentPart =
  | { type: "text"; text: string }
  | { type: "image_url"; image_url: { url: string } };

export type ChatCompletionResponse = {
  choices?: Array<{ message?: { role?: string; content?: string } }>;
};

export type EditableFileTask = {
  id: string;
  taskId?: string;
  status: "queued" | "running" | "success" | "error" | string;
  kind: "ppt" | "psd" | string;
  created_at?: string;
  updated_at?: string;
  elapsed_seconds?: number;
  polled_at?: number;
  prompt_preview?: string;
  error?: string;
  result?: {
    conversation_id?: string;
    primary_url?: string;
    zip_url?: string;
  };
};

export const pretty = (value: unknown) => JSON.stringify(value, null, 2);
