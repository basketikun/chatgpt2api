"use client";

import { useEffect, useRef, useState } from "react";
import { ExternalLink, Globe2, LoaderCircle, Search } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useTranslation } from "react-i18next";

import { httpRequest } from "@/lib/request";
import { cn } from "@/lib/utils";

import type { SearchResult } from "./types";

const normalizeMarkdown = (text: string) =>
  text
    .replace(/\ue200url\ue202([^\ue202\ue201]*)\ue202([^\ue201]*)\ue201/g, "[$1]($2)")
    .replace(/\ue200cite\ue202[^\ue201]*\ue201/g, "")
    .replace(/\ue200[^\ue201]*\ue201/g, "")
    .replace(/\ue200[^\ue201]*$/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

const cleanUrl = (url: string) => url.replace(/[\ue200-\ue202].*$/g, "").trim();

const sourceKind = (url: string) => {
  const host = (() => {
    try {
      return new URL(url).hostname;
    } catch {
      return "";
    }
  })();
  return host.includes("github.com") ? "github" : "web";
};

function MarkdownResult({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ className, ...props }) => <a className={cn("font-medium text-blue-700 underline decoration-blue-300 underline-offset-4 hover:text-blue-900 dark:text-blue-300 dark:decoration-blue-700", className)} target="_blank" rel="noreferrer" {...props} />,
        h1: ({ className, ...props }) => <h1 className={cn("mt-8 mb-4 text-2xl font-semibold tracking-tight text-stone-950 first:mt-0 dark:text-stone-50", className)} {...props} />,
        h2: ({ className, ...props }) => <h2 className={cn("mt-8 mb-4 border-b border-stone-200 pb-2 text-xl font-semibold tracking-tight text-stone-950 first:mt-0 dark:border-white/10 dark:text-stone-50", className)} {...props} />,
        h3: ({ className, ...props }) => <h3 className={cn("mt-6 mb-3 text-lg font-semibold text-stone-900 dark:text-stone-100", className)} {...props} />,
        p: ({ className, ...props }) => <p className={cn("my-4 leading-8 text-stone-800 dark:text-stone-200", className)} {...props} />,
        ul: ({ className, ...props }) => <ul className={cn("my-4 list-disc space-y-2 pl-6 leading-7 text-stone-800 dark:text-stone-200", className)} {...props} />,
        ol: ({ className, ...props }) => <ol className={cn("my-4 list-decimal space-y-2 pl-6 leading-7 text-stone-800 dark:text-stone-200", className)} {...props} />,
        blockquote: ({ className, ...props }) => <blockquote className={cn("my-5 border-l-4 border-stone-300 bg-white/70 py-3 pr-4 pl-5 text-stone-700 dark:border-white/20 dark:bg-white/[0.04] dark:text-stone-300", className)} {...props} />,
        code: ({ className, ...props }) => <code className={cn("rounded bg-stone-100 px-1.5 py-0.5 font-mono text-[0.9em] text-stone-800 dark:bg-white/10 dark:text-stone-100", className)} {...props} />,
        pre: ({ className, ...props }) => <pre className={cn("my-5 overflow-x-auto rounded-xl border border-stone-200 bg-stone-950 p-4 text-sm text-stone-50 dark:border-white/10", className)} {...props} />,
        table: ({ className, ...props }) => <div className="my-5 overflow-x-auto rounded-xl border border-stone-200 dark:border-white/10"><table className={cn("w-full border-collapse text-sm", className)} {...props} /></div>,
        th: ({ className, ...props }) => <th className={cn("border-b border-stone-200 bg-stone-100 px-3 py-2 text-left font-semibold dark:border-white/10 dark:bg-white/10", className)} {...props} />,
        td: ({ className, ...props }) => <td className={cn("border-b border-stone-100 px-3 py-2 align-top dark:border-white/10", className)} {...props} />,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export function SearchPanel() {
  const { t, i18n } = useTranslation("debug");
  const [prompt, setPrompt] = useState(t("searchPanel.defaultPrompt"));
  const isDefaultPromptRef = useRef(true);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [startedAt, setStartedAt] = useState(0);
  const searched = loading || !!result || !!error;

  // The initial language is pinned to the zh fallback until the detected locale
  // is applied after mount (see i18n/config.ts), so recompute the untouched
  // default once the real locale is known instead of freezing it in zh.
  useEffect(() => {
    if (isDefaultPromptRef.current) setPrompt(t("searchPanel.defaultPrompt"));
  }, [i18n.language, t]);

  useEffect(() => {
    if (!loading || !startedAt) return;
    const timer = window.setInterval(() => setElapsedMs(Date.now() - startedAt), 100);
    return () => window.clearInterval(timer);
  }, [loading, startedAt]);

  const runSearch = async () => {
    const value = prompt.trim();
    if (!value || loading) return;
    const start = Date.now();
    setStartedAt(start);
    setElapsedMs(0);
    setLoading(true);
    setError("");
    setResult(null);
    try {
      setResult(await httpRequest<SearchResult>("/v1/search", { method: "POST", body: { prompt: value } }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setElapsedMs(Date.now() - start);
      setLoading(false);
    }
  };

  return (
    <section className={cn("mx-auto flex min-h-[calc(100vh-142px)] w-full max-w-6xl flex-col px-4 transition-all", searched ? "py-5" : "justify-center")}>
      <div className={cn("mx-auto w-full max-w-3xl", searched && "sticky top-3 z-10")}>
        {!searched ? (
          <p className="mb-5 text-center text-sm text-stone-500 dark:text-stone-400">{t("searchPanel.intro")}</p>
        ) : null}
        <form
          className={cn("mx-auto flex w-full items-center gap-3 rounded-full border border-stone-200 bg-white/95 backdrop-blur transition-all dark:border-white/10 dark:bg-stone-950/90", searched ? "px-4 py-2" : "px-5 py-3")}
          onSubmit={(event) => {
            event.preventDefault();
            void runSearch();
          }}
        >
          <img src="/openai.svg" alt="" aria-hidden="true" className="size-5 shrink-0 opacity-80 dark:invert" />
          <input
            value={prompt}
            onChange={(event) => { isDefaultPromptRef.current = false; setPrompt(event.target.value); }}
            placeholder={t("searchPanel.placeholder")}
            className={cn("min-w-0 flex-1 bg-transparent text-[15px] text-stone-900 outline-none placeholder:text-stone-400 dark:text-stone-100 dark:placeholder:text-stone-500", searched ? "h-8" : "h-10")}
          />
          <button type="submit" disabled={loading || !prompt.trim()} className="inline-flex size-8 shrink-0 items-center justify-center rounded-full text-stone-800 transition hover:bg-stone-100 disabled:cursor-not-allowed disabled:text-stone-300 dark:text-stone-100 dark:hover:bg-white/10 dark:disabled:text-stone-600">
            {loading ? <LoaderCircle className="size-4 animate-spin" /> : <Search className="size-4" />}
          </button>
        </form>
      </div>

      {searched ? <div className="mx-auto w-full max-w-6xl flex-1 pt-6">
        {loading ? (
          <div className="mx-auto flex max-w-3xl items-center gap-3 rounded-2xl border border-stone-200 bg-white/75 px-4 py-3 text-sm text-stone-600 dark:border-white/10 dark:bg-white/[0.03] dark:text-stone-300">
            <LoaderCircle className="size-4 animate-spin" />
            {t("searchPanel.searching")} {(elapsedMs / 1000).toFixed(1)}s
          </div>
        ) : null}

        {error ? <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/25 dark:text-rose-300">{error}</div> : null}

        {result ? (
          <article className="grid gap-8 pb-12 lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="min-w-0">
              <div className="mb-5 flex flex-wrap items-center gap-2 text-xs text-stone-500 dark:text-stone-400">
                <span className="rounded-full border border-stone-200 bg-white px-3 py-1 dark:border-white/10 dark:bg-white/[0.03]">{result.status || "done"}</span>
                <span className="rounded-full border border-stone-200 bg-white px-3 py-1 dark:border-white/10 dark:bg-white/[0.03]">{(elapsedMs / 1000).toFixed(2)}s</span>
                <span className="rounded-full border border-stone-200 bg-white px-3 py-1 dark:border-white/10 dark:bg-white/[0.03]">{result.sources?.length || 0} sources</span>
              </div>
              <div className="text-[15px]">
                <MarkdownResult content={normalizeMarkdown(result.answer || "")} />
              </div>
            </div>
            {result.sources?.length ? (
              <aside className="lg:sticky lg:top-24 lg:self-start">
                <div className="mb-3 text-sm font-semibold text-stone-900 dark:text-stone-100">{t("searchPanel.sourcesTitle")}</div>
                <div className="divide-y divide-stone-200 dark:divide-white/10">
                  {result.sources.map((source, index) => {
                    const url = cleanUrl(source.url || "");
                    const kind = sourceKind(url);
                    return (
                      <a key={`${url || index}`} href={url} target="_blank" rel="noreferrer" className="flex gap-3 py-3 text-xs transition hover:text-stone-950 dark:hover:text-stone-50">
                        <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center text-stone-600 dark:text-stone-300">
                          {kind === "github" ? <img src="/github.svg" alt="" aria-hidden="true" className="size-3.5 dark:invert" /> : <Globe2 className="size-3.5" />}
                        </span>
                        <span className="min-w-0">
                          <span className="line-clamp-2 font-medium leading-5 text-stone-800 dark:text-stone-200">{source.title || url || "source"}</span>
                          <span className="mt-1 flex items-center gap-1 truncate text-stone-500 dark:text-stone-400">
                            <ExternalLink className="size-3 shrink-0" />
                            {url}
                          </span>
                        </span>
                      </a>
                    );
                  })}
                </div>
              </aside>
            ) : null}
          </article>
        ) : null}
      </div> : null}
    </section>
  );
}
