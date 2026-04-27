"use client";

import { Copy, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { awesomePromptSections, awesomePromptSummary, type AwesomePromptSection } from "@/data/awesome-prompts";
import { cn } from "@/lib/utils";

const featuredSectionTitle = "海报与插画案例";
const allSectionTitle = "全部分类";

export default function PromptsPage() {
  const [query, setQuery] = useState("");
  const [selectedSection, setSelectedSection] = useState(allSectionTitle);
  const [translatedOnly, setTranslatedOnly] = useState(false);

  const sectionTabs = useMemo(
    () => [
      { title: allSectionTitle, count: awesomePromptSummary.promptCount },
      ...awesomePromptSections.map((section) => ({
        title: section.title,
        count: section.items.length,
      })),
    ],
    [],
  );

  const visibleSections = useMemo(() => {
    const keyword = query.trim().toLowerCase();

    return awesomePromptSections
      .filter((section) => selectedSection === allSectionTitle || section.title === selectedSection)
      .map((section) => ({
        ...section,
        items: section.items.filter((item) => {
          if (translatedOnly && !item.translated) {
            return false;
          }

          if (!keyword) {
            return true;
          }

          return [section.title, item.title, item.originalTitle, item.prompt, item.originalPrompt]
            .join("\n")
            .toLowerCase()
            .includes(keyword);
        }),
      }))
      .filter((section) => section.items.length > 0)
      .sort((a, b) => {
        if (a.title === featuredSectionTitle) {
          return -1;
        }
        if (b.title === featuredSectionTitle) {
          return 1;
        }
        return 0;
      });
  }, [query, selectedSection, translatedOnly]);

  const visiblePromptCount = useMemo(
    () => visibleSections.reduce((count, section) => count + section.items.length, 0),
    [visibleSections],
  );

  const copyPrompt = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success("提示词已复制");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "复制失败");
    }
  };

  return (
    <section className="space-y-5">
      <div className="overflow-hidden rounded-[30px] border border-stone-200/80 bg-white/88 shadow-[0_24px_80px_-48px_rgba(41,37,36,0.45)] backdrop-blur">
        <div className="grid gap-8 px-6 py-7 lg:grid-cols-[minmax(0,1.4fr)_320px] lg:px-8">
          <div className="space-y-4">
            <div className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
              README 提示词全集
            </div>
            <div className="space-y-3">
              <h1 className="text-3xl font-semibold tracking-tight text-stone-950">提示词</h1>
              <p className="max-w-3xl text-sm leading-7 text-stone-600">
                展示
                <a
                  href="https://github.com/EvoLinkAI/awesome-gpt-image-2-prompts/blob/main/README_zh-CN.md"
                  target="_blank"
                  rel="noreferrer"
                  className="mx-1 font-medium text-stone-950 underline decoration-stone-300 underline-offset-4"
                >
                  awesome-gpt-image-2-prompts / README_zh-CN.md
                </a>
                中的全部提示词，并将非简体中文提示词翻译为简体中文。默认优先展示“海报与插画案例”。
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            <SummaryCard label="分类" value={String(awesomePromptSummary.sectionCount)} hint="README 分区" />
            <SummaryCard label="提示词" value={String(awesomePromptSummary.promptCount)} hint="本地静态索引" />
            <SummaryCard label="已翻译" value={String(awesomePromptSummary.translatedCount)} hint="非简中已转简中" />
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3 rounded-[28px] border border-stone-200/80 bg-white/84 px-4 py-4 shadow-[0_20px_64px_-48px_rgba(41,37,36,0.4)] backdrop-blur sm:px-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="relative w-full max-w-xl">
            <Search className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-stone-400" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索标题或提示词内容"
              className="h-12 rounded-full border-stone-200 bg-stone-50/80 pl-11"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setTranslatedOnly((current) => !current)}
              className={cn(
                "rounded-full border px-4 py-2 text-sm font-medium transition",
                translatedOnly
                  ? "border-stone-900 bg-stone-950 text-white"
                  : "border-stone-200 bg-white text-stone-600 hover:border-stone-300 hover:text-stone-900",
              )}
            >
              仅看已翻译
            </button>
            <div className="rounded-full bg-stone-100 px-4 py-2 text-sm font-medium text-stone-600">
              当前 {visiblePromptCount} 条
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {sectionTabs.map((section) => {
            const active = section.title === selectedSection;
            return (
              <button
                key={section.title}
                type="button"
                onClick={() => setSelectedSection(section.title)}
                className={cn(
                  "rounded-full px-4 py-2 text-sm font-medium transition",
                  active ? "bg-stone-950 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200",
                )}
              >
                {section.title}
                <span className={cn("ml-2 text-xs", active ? "text-stone-300" : "text-stone-400")}>{section.count}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-6">
        {visibleSections.length === 0 ? (
          <div className="rounded-[28px] border border-dashed border-stone-300 bg-white/72 px-6 py-16 text-center text-sm text-stone-500">
            没有匹配的提示词，换个关键词试试。
          </div>
        ) : (
          visibleSections.map((section) => <PromptSection key={section.title} section={section} onCopy={copyPrompt} />)
        )}
      </div>
    </section>
  );
}

function SummaryCard({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-[24px] border border-stone-200/80 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(247,244,240,0.94))] px-5 py-4">
      <div className="text-xs font-medium uppercase tracking-[0.18em] text-stone-400">{label}</div>
      <div className="mt-2 text-3xl font-semibold tracking-tight text-stone-950">{value}</div>
      <div className="mt-1 text-sm text-stone-500">{hint}</div>
    </div>
  );
}

function PromptSection({
  section,
  onCopy,
}: {
  section: AwesomePromptSection;
  onCopy: (value: string) => void | Promise<void>;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between px-1">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-stone-950">{section.title}</h2>
          <p className="mt-1 text-sm text-stone-500">{section.items.length} 条提示词</p>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {section.items.map((item) => (
          <article
            key={`${section.title}-${item.caseNumber}-${item.title}`}
            className="overflow-hidden rounded-[28px] border border-stone-200/80 bg-white/88 shadow-[0_20px_64px_-52px_rgba(41,37,36,0.35)] backdrop-blur"
          >
            <div className="space-y-4 px-5 py-5 sm:px-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="space-y-2">
                  <div className="inline-flex items-center gap-2 rounded-full bg-stone-100 px-3 py-1 text-xs font-medium text-stone-500">
                    Case {item.caseNumber}
                    {item.translated ? (
                      <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] text-emerald-700">已翻译</span>
                    ) : (
                      <span className="rounded-full bg-stone-200 px-2 py-0.5 text-[11px] text-stone-600">原始简中</span>
                    )}
                  </div>
                  <h3 className="max-w-3xl text-lg font-semibold leading-7 text-stone-950">{item.title}</h3>
                </div>

                <Button
                  type="button"
                  variant="outline"
                  className="h-10 rounded-full border-stone-200 bg-white px-4 text-stone-700 shadow-none"
                  onClick={() => void onCopy(item.prompt)}
                >
                  <Copy className="size-4" />
                  复制提示词
                </Button>
              </div>

              <div className="rounded-[24px] border border-stone-200 bg-stone-50/80 p-4">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-stone-400">简体中文提示词</div>
                <pre className="whitespace-pre-wrap break-words text-sm leading-7 text-stone-700">{item.prompt}</pre>
              </div>

              {item.translated ? (
                <details className="rounded-[22px] border border-dashed border-stone-200 bg-white px-4 py-3">
                  <summary className="cursor-pointer list-none text-sm font-medium text-stone-600">
                    查看原始非简中提示词
                  </summary>
                  <pre className="mt-3 whitespace-pre-wrap break-words text-sm leading-7 text-stone-500">
                    {item.originalPrompt}
                  </pre>
                </details>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
