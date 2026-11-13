"use client";

import { useEffect, useMemo, useState } from "react";
import { Copy, Download } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import webConfig from "@/constants/common-env";
import { fetchSettingsConfig } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { getStoredAuthSession } from "@/store/auth";

export function SkillPanel() {
  const { t, locale } = useI18n();
  const [browserBaseUrl, setBrowserBaseUrl] = useState("");
  const [configuredBaseUrl, setConfiguredBaseUrl] = useState("");
  const [authKey, setAuthKey] = useState("");

  useEffect(() => {
    setBrowserBaseUrl(window.location.origin);
    void fetchSettingsConfig().then((data) => setConfiguredBaseUrl(String(data.config.base_url || "").replace(/\/$/, ""))).catch(() => undefined);
    void getStoredAuthSession().then((session) => setAuthKey(session?.key || ""));
  }, []);

  const apiBaseUrl = configuredBaseUrl || webConfig.apiUrl.replace(/\/$/, "") || browserBaseUrl;

  const skillZh = useMemo(() => `---
name: chatgpt2api-search
description: 当用户需要联网搜索、查询最新信息、核实事实或需要来源链接时，调用本地 chatgpt2api 搜索接口。
---

# ChatGPT2API 搜索

当用户要求联网搜索、查询最新信息、核实资料、查新闻、查价格、查文档更新或需要来源链接时，使用这个 skill。

## 接口

POST ${apiBaseUrl}/v1/search

Headers:

Authorization: Bearer ${authKey}
Content-Type: application/json

Body:

{
  "prompt": "<用户要搜索的问题>"
}

## 返回处理

- 使用接口返回的 \`answer\` 作为主要回答。
- 如果有 \`sources\`，在回答里附上来源链接。
- 如果接口报错，简要说明错误并询问是否重试。`, [apiBaseUrl, authKey]);

  const skillEn = useMemo(() => `---
name: chatgpt2api-search
description: Use when current web search is needed through this chatgpt2api server. Call the configured HTTP search endpoint with a prompt and return the answer with source URLs.
---

# ChatGPT2API Search

Use this skill when the user asks for current web search, online lookup, recent information, or source-backed answers. It calls the local chatgpt2api search endpoint and returns an answer with source links.

## When to use

- The user asks to search the web, look something up, verify current information, or find the latest status.
- The answer needs source URLs, recent details, prices, releases, docs, laws, schedules, or news.
- Do not use it for purely local codebase questions unless the user explicitly asks for web search.

## Request

POST ${apiBaseUrl}/v1/search

Headers:

Authorization: Bearer ${authKey}
Content-Type: application/json

JSON body:

{
  "prompt": "<search question>"
}

## Response handling

- Use \`answer\` as the main response.
- Include source URLs from \`sources\` when available.
- If the endpoint returns an error, summarize the error and ask the user whether to retry.
- Keep the final answer concise unless the user asks for detail.`, [apiBaseUrl, authKey]);

  const zhPrompt = useMemo(() => `请帮我在本机安装一个用于联网搜索的 skill。

要求：
1. 请按你当前环境的 skill 安装规范，把它安装成本地 skill。
2. skill 名称为：chatgpt2api-search
3. 文件名为：SKILL.md
4. 如果你无法确定本地 skills 目录在哪里，先告诉我需要放到哪个目录，不要猜路径。
5. 只创建或更新这个 skill 文件，不要修改其他无关文件。
6. SKILL.md 请写入下面的完整内容。

SKILL.md 内容：

\`\`\`markdown
${skillZh}
\`\`\``, [skillZh]);

  const enPrompt = useMemo(() => `Please install a local web-search skill on this machine.

Requirements:
1. Install this as a local skill according to the skill installation rules of your current environment.
2. Skill name: chatgpt2api-search
3. File name: SKILL.md
4. If you cannot determine the local skills directory, tell me which directory is required before writing files.
5. Only create or update this skill file. Do not modify unrelated files.
6. Write the full content below into SKILL.md.

SKILL.md content:

\`\`\`markdown
${skillEn}
\`\`\``, [skillEn]);

  const faPrompt = useMemo(() => `لطفاً این اسکیل (skill) جستجوی وب را به صورت محلی بر روی سیستم نصب کنید.

الزامات:
1. بر اساس قوانین محیط جاری، آن را به عنوان یک skill محلی نصب نمایید.
2. نام اسکیل: chatgpt2api-search
3. نام فایل: SKILL.md
4. در صورت عدم اطمینان از محل پوشه skills، پیش از ذخیره محل آن را سوال کنید.
5. تنها این فایل را ایجاد یا به‌روزرسانی کنید و فایل‌های دیگر را تغییر ندهید.
6. محتوای کامل زیر را در فایل SKILL.md قرار دهید:

\`\`\`markdown
${skillEn}
\`\`\``, [skillEn]);

  const arPrompt = useMemo(() => `يرجى تثبيت أداة البحث في الويب (skill) محلياً على هذا الجهاز.

المتطلبات:
1. تثبيت الأداة وفقاً لمعايير البيئة الحالية كـ local skill.
2. اسم الأداة: chatgpt2api-search
3. اسم الملف: SKILL.md
4. إذا تعذر تحديد مسار مجلد skills، أخبرني بالمطلوب مسبقاً.
5. قم بإنشاء أو تحديث هذا الملف فقط دون تعديل أي ملفات أخرى.
6. اكتب المحتوى الكامل أدناه في ملف SKILL.md:

\`\`\`markdown
${skillEn}
\`\`\``, [skillEn]);

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(t.skillPanel.copied);
    } catch {
      toast.error(t.skillPanel.copyFailed);
    }
  };

  const downloadSkill = (text: string) => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "SKILL.md";
    link.click();
    URL.revokeObjectURL(url);
  };

  const versions = useMemo(() => {
    if (locale === "fa") {
      return [
        { title: "دستورالعمل نصب (فارسی)", desc: "این متن را کپی کرده و به دستیار هوش مصنوعی ارسال کنید تا اسکیل را نصب کند.", prompt: faPrompt, skill: skillEn },
        { title: "English Install Prompt", desc: "Copy and send this to Codex, Claude or Agent to install locally.", prompt: enPrompt, skill: skillEn },
      ];
    }
    if (locale === "ar") {
      return [
        { title: "أمر التثبيت (العربية)", desc: "انسخ هذا النص وأرسله إلى المساعد لتثبيت الأداة محلياً.", prompt: arPrompt, skill: skillEn },
        { title: "English Install Prompt", desc: "Copy and send this to Codex, Claude or Agent to install locally.", prompt: enPrompt, skill: skillEn },
      ];
    }
    if (locale === "zh") {
      return [
        { title: "中文安装指令", desc: "复制后直接发给 Codex 或 Claude，让它安装到本地。", prompt: zhPrompt, skill: skillZh },
        { title: "English install prompt", desc: "Copy and send this to Codex or Claude to install locally.", prompt: enPrompt, skill: skillEn },
      ];
    }
    return [
      { title: "English Install Prompt", desc: "Copy and send this to Codex, Claude or Agent to install locally.", prompt: enPrompt, skill: skillEn },
      { title: "中文安装指令", desc: "复制后直接发给 Codex 或 Claude，让它安装到本地。", prompt: zhPrompt, skill: skillZh },
    ];
  }, [locale, faPrompt, arPrompt, zhPrompt, enPrompt, skillEn, skillZh]);

  return (
    <section className="grid items-stretch gap-4 lg:grid-cols-2">
      {versions.map((item) => (
        <div key={item.title} className="flex flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm dark:border-white/10 dark:bg-white/[0.04]">
          <div className="flex items-center justify-between gap-3 border-b border-slate-200/70 bg-slate-50/80 p-4 dark:border-white/10 dark:bg-white/[0.03]">
            <div>
              <h2 className="font-medium text-slate-900 dark:text-slate-100">{item.title}</h2>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{item.desc}</p>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" className="cursor-pointer" onClick={() => downloadSkill(item.skill)}>
                <Download className="size-4" />
                {t.skillPanel.downloadBtn}
              </Button>
              <Button size="sm" className="cursor-pointer" onClick={() => void copyText(item.prompt)}>
                <Copy className="size-4" />
                {t.skillPanel.copyPromptBtn}
              </Button>
            </div>
          </div>
          <pre className="flex-1 whitespace-pre-wrap p-4 font-mono text-sm leading-6" dir="ltr">
            {item.prompt}
          </pre>
        </div>
      ))}
    </section>
  );
}
