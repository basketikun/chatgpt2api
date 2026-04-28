import { httpRequest } from "@/lib/request";

export type ImageModel = "gpt-image-1" | "gpt-image-2";

export type RuntimeStatus = {
  available_quota: number;
  image_upstream: "openai" | "chatgpt_pool";
};

export type ImagePromptOptimization = {
  prompt: string;
  optimized_prompt: string;
  changed: boolean;
  optimizer: "model" | "fallback" | "none";
  model?: string;
  reason?: string;
  original_length?: number;
  optimized_length?: number;
};

export async function login(authKey: string) {
  const normalizedAuthKey = String(authKey || "").trim();
  return httpRequest<{ ok: boolean }>("/auth/login", {
    method: "POST",
    body: {},
    headers: {
      Authorization: `Bearer ${normalizedAuthKey}`,
    },
    redirectOnUnauthorized: false,
  });
}

export async function fetchRuntimeStatus() {
  return httpRequest<RuntimeStatus>("/api/runtime");
}

export async function optimizeImagePrompt(prompt: string, mode: "generate" | "edit" = "generate") {
  return httpRequest<ImagePromptOptimization>("/api/image-prompts/optimize", {
    method: "POST",
    body: { prompt, mode },
  });
}

export async function generateImage(prompt: string, model: ImageModel = "gpt-image-2", originalPrompt?: string) {
  return httpRequest<{ created: number; data: Array<{ b64_json: string; revised_prompt?: string }> }>(
    "/v1/images/generations",
    {
      method: "POST",
      body: {
        prompt,
        original_prompt: originalPrompt,
        model,
        n: 1,
        response_format: "b64_json",
      },
    },
  );
}

export async function editImage(files: File | File[], prompt: string, model: ImageModel = "gpt-image-2") {
  const formData = new FormData();
  const uploadFiles = Array.isArray(files) ? files : [files];

  uploadFiles.forEach((file) => {
    formData.append("image", file);
  });
  formData.append("prompt", prompt);
  formData.append("model", model);
  formData.append("n", "1");

  return httpRequest<{ created: number; data: Array<{ b64_json: string; revised_prompt?: string }> }>(
    "/v1/images/edits",
    {
      method: "POST",
      body: formData,
    },
  );
}
