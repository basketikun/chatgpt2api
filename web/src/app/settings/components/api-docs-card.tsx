"use client";

import { useEffect, useState } from "react";
import { ChevronDown, FileArchive, FileText, KeyRound, ListChecks, type LucideIcon } from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { Card, CardContent } from "@/components/ui/card";
import webConfig from "@/constants/common-env";
import { getStoredAuthSession } from "@/store/auth";

type ParamRow = [string, string, string];

type ApiDoc = {
  title: string;
  method: string;
  path: string;
  icon: LucideIcon;
  input: ParamRow[];
  output: ParamRow[];
  example: (baseUrl: string, key: string) => string;
};

function buildDocs(t: TFunction): ApiDoc[] {
  return [
    {
      title: t("apiDocs.docs.models.title"),
      method: "GET",
      path: "/v1/models",
      icon: ListChecks,
      input: [
        ["Authorization", "header", t("apiDocs.docs.models.input.authorization")],
      ],
      output: [
        ["data", "array", t("apiDocs.docs.models.output.data")],
      ],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/models \\
  -H "Authorization: Bearer ${key}"`,
    },
    {
      title: t("apiDocs.docs.chatCompletions.title"),
      method: "POST",
      path: "/v1/chat/completions",
      icon: FileText,
      input: [
        ["model", "string", t("apiDocs.docs.chatCompletions.input.model")],
        ["messages", "array", t("apiDocs.docs.chatCompletions.input.messages")],
        ["stream", "boolean", t("apiDocs.docs.chatCompletions.input.stream")],
        ["n", "number", t("apiDocs.docs.chatCompletions.input.n")],
      ],
      output: [
        ["id", "string", t("apiDocs.docs.chatCompletions.output.id")],
        ["choices", "array", t("apiDocs.docs.chatCompletions.output.choices")],
        ["usage", "object", t("apiDocs.docs.chatCompletions.output.usage")],
      ],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{"model":"gpt-5-mini","messages":[{"role":"user","content":"${t("apiDocs.docs.chatCompletions.examplePrompt")}"}]}'`,
    },
    {
      title: "Responses",
      method: "POST",
      path: "/v1/responses",
      icon: FileText,
      input: [
        ["model", "string", t("apiDocs.docs.responses.input.model")],
        ["input", "string | array | object", t("apiDocs.docs.responses.input.input")],
        ["tools", "array", t("apiDocs.docs.responses.input.tools")],
        ["stream", "boolean", t("apiDocs.docs.responses.input.stream")],
      ],
      output: [
        ["id", "string", t("apiDocs.docs.responses.output.id")],
        ["output", "array", t("apiDocs.docs.responses.output.output")],
        ["status", "string", t("apiDocs.docs.responses.output.status")],
      ],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/responses \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{"model":"gpt-5-mini","input":"${t("apiDocs.docs.responses.examplePrompt")}"}'`,
    },
    {
      title: t("apiDocs.docs.search.title"),
      method: "POST",
      path: "/v1/search",
      icon: ListChecks,
      input: [
        ["prompt", "string", t("apiDocs.docs.search.input.prompt")],
      ],
      output: [
        ["answer", "string", t("apiDocs.docs.search.output.answer")],
        ["sources", "array", t("apiDocs.docs.search.output.sources")],
        ["_account_email", "string", t("apiDocs.docs.search.output.accountEmail")],
      ],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/search \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{"prompt":"${t("apiDocs.docs.search.examplePrompt")}"}'`,
    },
    {
      title: t("apiDocs.docs.imageGenerations.title"),
      method: "POST",
      path: "/v1/images/generations",
      icon: FileArchive,
      input: [
        ["prompt", "string", t("apiDocs.docs.imageGenerations.input.prompt")],
        ["model", "string", t("apiDocs.docs.imageGenerations.input.model")],
        ["n", "number", t("apiDocs.docs.imageGenerations.input.n")],
        ["size", "string", t("apiDocs.docs.imageGenerations.input.size")],
        ["quality", "string", t("apiDocs.docs.imageGenerations.input.quality")],
        ["response_format", "string", t("apiDocs.docs.imageGenerations.input.responseFormat")],
      ],
      output: [
        ["data", "array", t("apiDocs.docs.imageGenerations.output.data")],
        ["data[].b64_json", "string", t("apiDocs.docs.imageGenerations.output.dataB64Json")],
        ["data[].url", "string", t("apiDocs.docs.imageGenerations.output.dataUrl")],
      ],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/images/generations \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{"model":"gpt-image-2","prompt":"${t("apiDocs.docs.imageGenerations.examplePrompt")}","n":1}'`,
    },
    {
      title: t("apiDocs.docs.imageEdits.title"),
      method: "POST",
      path: "/v1/images/edits",
      icon: FileArchive,
      input: [
        ["image", "file | file[] | URL", t("apiDocs.docs.imageEdits.input.image")],
        ["prompt", "string", t("apiDocs.docs.imageEdits.input.prompt")],
        ["model", "string", t("apiDocs.docs.imageEdits.input.model")],
        ["n", "number", t("apiDocs.docs.imageEdits.input.n")],
        ["size", "string", t("apiDocs.docs.imageEdits.input.size")],
        ["quality", "string", t("apiDocs.docs.imageEdits.input.quality")],
      ],
      output: [
        ["data", "array", t("apiDocs.docs.imageEdits.output.data")],
        ["data[].b64_json", "string", t("apiDocs.docs.imageEdits.output.dataB64Json")],
        ["data[].url", "string", t("apiDocs.docs.imageEdits.output.dataUrl")],
      ],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/images/edits \\
  -H "Authorization: Bearer ${key}" \\
  -F "model=gpt-image-2" \\
  -F "prompt=${t("apiDocs.docs.imageEdits.examplePrompt")}" \\
  -F "image=@./input.png"`,
    },
    {
      title: t("apiDocs.docs.pptTask.title"),
      method: "POST",
      path: "/v1/ppt/generations",
      icon: FileText,
      input: [
        ["prompt", "string", t("apiDocs.docs.pptTask.input.prompt")],
        ["base64_images", "string[]", t("apiDocs.docs.pptTask.input.base64Images")],
        ["client_task_id", "string", t("apiDocs.docs.pptTask.input.clientTaskId")],
      ],
      output: [
        ["id / taskId", "string", t("apiDocs.docs.pptTask.output.idOrTaskId")],
        ["status", "queued | running | success | error", t("apiDocs.docs.pptTask.output.status")],
        ["kind", "ppt", t("apiDocs.docs.pptTask.output.kind")],
        ["created_at / updated_at", "string", t("apiDocs.docs.pptTask.output.createdUpdatedAt")],
      ],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/ppt/generations \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{"prompt":"${t("apiDocs.docs.pptTask.examplePrompt")}","base64_images":[]}'`,
    },
    {
      title: t("apiDocs.docs.psdTask.title"),
      method: "POST",
      path: "/v1/psd/generations",
      icon: FileArchive,
      input: [
        ["prompt", "string", t("apiDocs.docs.psdTask.input.prompt")],
        ["base64_images", "string[]", t("apiDocs.docs.psdTask.input.base64Images")],
        ["client_task_id", "string", t("apiDocs.docs.psdTask.input.clientTaskId")],
      ],
      output: [
        ["id / taskId", "string", t("apiDocs.docs.psdTask.output.idOrTaskId")],
        ["status", "queued | running | success | error", t("apiDocs.docs.psdTask.output.status")],
        ["kind", "psd", t("apiDocs.docs.psdTask.output.kind")],
        ["error", "string", t("apiDocs.docs.psdTask.output.error")],
      ],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/psd/generations \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{"prompt":"${t("apiDocs.docs.psdTask.examplePrompt")}","base64_images":["data:image/png;base64,..."]}'`,
    },
    {
      title: t("apiDocs.docs.taskStatus.title"),
      method: "GET",
      path: "/v1/editable-file-tasks?ids={taskId1,taskId2}",
      icon: ListChecks,
      input: [
        ["ids", "string", t("apiDocs.docs.taskStatus.input.ids")],
      ],
      output: [
        ["items", "array", t("apiDocs.docs.taskStatus.output.items")],
        ["missing_ids", "string[]", t("apiDocs.docs.taskStatus.output.missingIds")],
        ["result.primary_url", "string", t("apiDocs.docs.taskStatus.output.resultPrimaryUrl")],
        ["result.zip_url", "string", t("apiDocs.docs.taskStatus.output.resultZipUrl")],
      ],
      example: (baseUrl: string, key: string) => `curl "${baseUrl}/editable-file-tasks?ids=<task_id>" \\
  -H "Authorization: Bearer ${key}"`,
    },
    {
      title: t("apiDocs.docs.fileDownload.title"),
      method: "GET",
      path: "/files/{file_path}",
      icon: FileArchive,
      input: [
        ["file_path", "string", t("apiDocs.docs.fileDownload.input.filePath")],
      ],
      output: [
        ["binary", "file", t("apiDocs.docs.fileDownload.output.binary")],
      ],
      example: (baseUrl: string, _key: string) => `curl ${baseUrl.replace(/\/v1$/, "")}/files/<file_path> -o result.zip`,
    },
  ];
}

const usableModels = ["gpt-image-2", "codex-gpt-image-2", "auto", "gpt-5", "gpt-5-1", "gpt-5-2", "gpt-5-3", "gpt-5-3-mini", "gpt-5-mini"];

function ParamTable({ rows, t }: { rows: ParamRow[]; t: TFunction }) {
  return (
    <div className="overflow-hidden rounded-lg border border-stone-200">
      <table className="w-full text-left text-xs">
        <thead className="bg-stone-50 text-stone-500">
          <tr>
            <th className="px-3 py-2 font-medium">{t("apiDocs.table.param")}</th>
            <th className="px-3 py-2 font-medium">{t("apiDocs.table.type")}</th>
            <th className="px-3 py-2 font-medium">{t("apiDocs.table.description")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-stone-100 bg-white">
          {rows.map(([name, type, desc]) => (
            <tr key={name}>
              <td className="px-3 py-2 font-mono text-stone-800">{name}</td>
              <td className="px-3 py-2 font-mono text-stone-500">{type}</td>
              <td className="px-3 py-2 text-stone-600">{desc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ApiDocsCard() {
  const { t } = useTranslation("settings");
  const docs = buildDocs(t);
  const [authKey, setAuthKey] = useState("");
  const serviceBaseUrl = webConfig.apiUrl.replace(/\/$/, "") || (typeof window !== "undefined" ? window.location.origin : "");
  const openAIBaseUrl = `${serviceBaseUrl}/v1`;
  const displayKey = authKey || t("apiDocs.info.noKeyPlaceholder");

  useEffect(() => {
    let active = true;
    void getStoredAuthSession().then((session) => {
      if (active) setAuthKey(session?.key || "");
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-5 p-6">
        <div>
          <div className="flex items-center gap-2 text-base font-semibold text-stone-900">
            <KeyRound className="size-5 text-stone-500" />
            {t("apiDocs.header.title")}
          </div>
          <p className="mt-1 text-xs leading-6 text-stone-500">
            {t("apiDocs.header.description")}
          </p>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1 rounded-xl border border-stone-200 bg-white px-3 py-2">
            <div className="text-xs text-stone-500">{t("apiDocs.info.serviceUrl")}</div>
            <div className="break-all font-mono text-xs text-stone-800">{serviceBaseUrl}</div>
          </div>
          <div className="space-y-1 rounded-xl border border-stone-200 bg-white px-3 py-2">
            <div className="text-xs text-stone-500">{t("apiDocs.info.openaiBaseUrl")}</div>
            <div className="break-all font-mono text-xs text-stone-800">{openAIBaseUrl}</div>
          </div>
          <div className="space-y-1 rounded-xl border border-stone-200 bg-white px-3 py-2">
            <div className="text-xs text-stone-500">API Key</div>
            <div className="break-all font-mono text-xs text-stone-800">{displayKey}</div>
          </div>
          <div className="space-y-1 rounded-xl border border-stone-200 bg-white px-3 py-2">
            <div className="text-xs text-stone-500">{t("apiDocs.info.requestHeader")}</div>
            <div className="break-all font-mono text-xs text-stone-800">Authorization: Bearer {displayKey}</div>
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-xs font-medium text-stone-600">{t("apiDocs.models.label")}</div>
          <div className="flex flex-wrap gap-2">
            {usableModels.map((model) => (
              <span key={model} className="rounded-md border border-stone-200 bg-white px-2 py-1 font-mono text-xs text-stone-700">{model}</span>
            ))}
          </div>
        </div>

        <div className="space-y-3">
          {docs.map((item) => {
            const Icon = item.icon;
            return (
              <details key={item.path} className="group rounded-xl border border-stone-200 bg-white px-4 py-3">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
                  <span className="flex min-w-0 items-center gap-3">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-stone-100 text-stone-600">
                      <Icon className="size-4" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-stone-900">{item.title}</span>
                      <span className="mt-1 block truncate font-mono text-xs text-stone-500">{item.method} {item.path}</span>
                    </span>
                  </span>
                  <ChevronDown className="size-4 shrink-0 text-stone-400 transition group-open:rotate-180" />
                </summary>

                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  <div className="space-y-2">
                    <h3 className="text-xs font-semibold text-stone-700">{t("apiDocs.sections.input")}</h3>
                    <ParamTable rows={item.input} t={t} />
                  </div>
                  <div className="space-y-2">
                    <h3 className="text-xs font-semibold text-stone-700">{t("apiDocs.sections.output")}</h3>
                    <ParamTable rows={item.output} t={t} />
                  </div>
                  <div className="space-y-2 lg:col-span-2">
                    <h3 className="text-xs font-semibold text-stone-700">{t("apiDocs.sections.example")}</h3>
                    <pre className="overflow-auto whitespace-pre-wrap break-all rounded-xl bg-stone-950 px-3 py-3 text-xs leading-5 text-stone-100">{item.example(openAIBaseUrl, displayKey)}</pre>
                  </div>
                </div>
              </details>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
