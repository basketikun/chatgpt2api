import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const README_URL =
  "https://raw.githubusercontent.com/EvoLinkAI/awesome-gpt-image-2-prompts/main/README_zh-CN.md";

const OUTPUT_PATH = path.resolve("src/data/awesome-prompts.ts");
const CACHE_PATH = path.resolve("tmp/awesome-prompts-README_zh-CN.md");

function normalizeWhitespace(value) {
  return value.replace(/\r\n/g, "\n").trim();
}

function shouldTranslate(prompt) {
  const chineseMatches = prompt.match(/[\u4e00-\u9fff]/g) ?? [];
  const japaneseMatches = prompt.match(/[\u3040-\u30ff]/g) ?? [];
  const latinMatches = prompt.match(/[A-Za-z]/g) ?? [];
  if (japaneseMatches.length > 0) {
    return true;
  }
  if (chineseMatches.length === 0 && latinMatches.length > 0) {
    return true;
  }
  return latinMatches.length > chineseMatches.length * 1.2;
}

function shouldTranslateTitle(title) {
  return shouldTranslate(title);
}

async function translateToSimplifiedChinese(text) {
  const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t&q=${encodeURIComponent(
    text,
  )}`;

  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const response = await fetch(url, {
      headers: {
        "user-agent": "Mozilla/5.0",
      },
    });

    if (response.ok) {
      const payload = await response.json();
      return (payload?.[0] ?? []).map((part) => part?.[0] ?? "").join("").trim();
    }

    if (attempt === 3) {
      throw new Error(`translation failed: ${response.status} ${response.statusText}`);
    }

    await new Promise((resolve) => setTimeout(resolve, attempt * 800));
  }

  return text;
}

function parseReadme(markdown) {
  const sections = [];
  const sectionRegex = /^##\s+(.+)$/gm;
  const matches = [...markdown.matchAll(sectionRegex)];

  for (let index = 0; index < matches.length; index += 1) {
    const sectionTitle = matches[index][1].trim();
    if (
      [
        "简介",
        "最新动态",
        "📑 Menu",
        "Star History",
      ].includes(sectionTitle)
    ) {
      continue;
    }

    const sectionStart = matches[index].index + matches[index][0].length;
    const sectionEnd = index + 1 < matches.length ? matches[index + 1].index : markdown.length;
    const sectionBody = markdown.slice(sectionStart, sectionEnd);
    const items = [];

    const caseRegex =
      /### Case (\d+): \[(.*?)\]\((.*?)\) \(by \[(.*?)\]\((.*?)\)\)([\s\S]*?)(?=\n### Case \d+:|\n##\s+|$)/g;

    for (const match of sectionBody.matchAll(caseRegex)) {
      const [, caseNumber, title, sourceUrl, author, authorUrl, body] = match;
      const promptMatch = body.match(/提示词[\s\S]*?```(?:\w+)?\n([\s\S]*?)\n```/);
      if (!promptMatch) {
        continue;
      }

      const originalPrompt = normalizeWhitespace(promptMatch[1]);
      items.push({
        caseNumber: Number(caseNumber),
        title: normalizeWhitespace(title),
        sourceUrl: normalizeWhitespace(sourceUrl),
        author: normalizeWhitespace(author),
        authorUrl: normalizeWhitespace(authorUrl),
        originalPrompt,
      });
    }

    if (items.length > 0) {
      sections.push({
        title: sectionTitle,
        items,
      });
    }
  }

  return sections;
}

function escapeTemplateLiteral(value) {
  return value.replace(/\\/g, "\\\\").replace(/`/g, "\\`").replace(/\$\{/g, "\\${");
}

async function main() {
  let markdown = "";

  try {
    const response = await fetch(README_URL, {
      headers: {
        "user-agent": "Mozilla/5.0",
      },
    });
    if (!response.ok) {
      throw new Error(`failed to fetch README: ${response.status} ${response.statusText}`);
    }
    markdown = await response.text();
  } catch (error) {
    markdown = await readFile(CACHE_PATH, "utf8");
    console.warn(`fetch README failed, fallback to cache: ${error instanceof Error ? error.message : String(error)}`);
  }

  const sections = parseReadme(markdown);

  for (const section of sections) {
    for (const item of section.items) {
      item.originalTitle = item.title;
      if (shouldTranslateTitle(item.originalTitle)) {
        item.title = await translateToSimplifiedChinese(item.originalTitle);
      }

      const translated = shouldTranslate(item.originalPrompt);
      item.prompt = translated ? await translateToSimplifiedChinese(item.originalPrompt) : item.originalPrompt;
      item.translated = translated;
    }
  }

  const output = `export type AwesomePromptItem = {
  caseNumber: number;
  title: string;
  originalTitle: string;
  sourceUrl: string;
  author: string;
  authorUrl: string;
  originalPrompt: string;
  prompt: string;
  translated: boolean;
};

export type AwesomePromptSection = {
  title: string;
  items: AwesomePromptItem[];
};

export const awesomePromptSections: AwesomePromptSection[] = ${JSON.stringify(sections, null, 2)};

export const awesomePromptSummary = {
  sectionCount: awesomePromptSections.length,
  promptCount: awesomePromptSections.reduce((count, section) => count + section.items.length, 0),
  translatedCount: awesomePromptSections.reduce(
    (count, section) => count + section.items.filter((item) => item.translated).length,
    0,
  ),
  sourceReadmeUrl: \`${escapeTemplateLiteral(README_URL)}\`,
};
`;

  await mkdir(path.dirname(OUTPUT_PATH), { recursive: true });
  await writeFile(OUTPUT_PATH, output, "utf8");
  console.log(`synced ${sections.length} sections to ${OUTPUT_PATH}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
