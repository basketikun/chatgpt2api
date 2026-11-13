"use client";

import { useMemo, useState } from "react";
import { LoaderCircle, Plus } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { addProxyPoolEntries, type ProxyCoreApplyResult, type ProxyPoolPayload } from "@/lib/api";
import { isShareLinkLine, MANUAL_SUBSCRIPTION_NAME } from "@/lib/proxy-pool";

type AddResult = {
  added: number;
  skipped: number;
  assigned: number;
  errors: Array<{ url: string; error: string }>;
  keptOnlyFailed: boolean;
  /** 这次提交里有分享链接：失败项的 url 是节点名称，节点已经保存在「手动添加的节点」里 */
  hasShareLinks: boolean;
  coreApply: ProxyCoreApplyResult | null;
};

const formatExamples = [
  { format: "scheme://user:pass@host:port", example: "socks5://user:pass@1.2.3.4:1080" },
  { format: "host:port", example: "1.2.3.4:8080" },
  { format: "host:port:user:pass", example: "1.2.3.4:8080:user:pass" },
];

const shareLinkSchemes = "vmess:// vless:// trojan:// ss:// ssr:// hysteria2:// hy2:// tuic:// socks://";

/** 一行一个；去掉空行、# 注释行和重复行。只去掉行首尾空白，分享链接和 Base64 内容（含 + / =）原样保留 */
export function parseProxyLines(text: string) {
  const seen = new Set<string>();
  const urls: string[] = [];
  for (const line of text.split(/\r?\n/)) {
    const value = line.trim();
    if (!value || value.startsWith("#") || seen.has(value)) {
      continue;
    }
    seen.add(value);
    urls.push(value);
  }
  return urls;
}

type ProxyAddDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  poolEnabled: boolean;
  onAdded: (data: ProxyPoolPayload) => void;
};

export function ProxyAddDialog({ open, onOpenChange, poolEnabled, onAdded }: ProxyAddDialogProps) {
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<AddResult | null>(null);

  const urls = useMemo(() => parseProxyLines(text), [text]);
  const shareLineCount = useMemo(() => urls.filter(isShareLinkLine).length, [urls]);
  // 后端只在添加单个普通代理时使用名称；分享链接用节点自己的名称
  const nameDisabled = urls.length > 1 || shareLineCount > 0;

  const reset = () => {
    setText("");
    setName("");
    setResult(null);
  };

  const handleOpenChange = (next: boolean) => {
    if (isSubmitting) {
      return;
    }
    if (!next) {
      reset();
    }
    onOpenChange(next);
  };

  const handleSubmit = async () => {
    if (urls.length === 0) {
      toast.error("请至少填写一个代理");
      return;
    }
    setIsSubmitting(true);
    try {
      const data = await addProxyPoolEntries(urls, nameDisabled ? undefined : name.trim() || undefined);
      onAdded(data);
      const errors = Array.isArray(data.errors) ? data.errors : [];
      const coreApply = data.core_apply ?? null;
      const coreFailed = coreApply?.ok === false;
      const summary: AddResult = {
        added: data.added ?? 0,
        skipped: data.skipped ?? 0,
        assigned: data.assigned ?? 0,
        errors,
        keptOnlyFailed: false,
        hasShareLinks: shareLineCount > 0,
        coreApply,
      };
      const assignedText = summary.assigned > 0 ? `，已为 ${summary.assigned} 个未绑定账号分配代理` : "";
      const addedText = `新增 ${summary.added} 个代理${summary.skipped > 0 ? `，跳过 ${summary.skipped} 个重复` : ""}${assignedText}`;
      if (errors.length === 0 && !coreFailed) {
        toast.success(addedText);
        reset();
        onOpenChange(false);
        return;
      }
      if (errors.length === 0) {
        // 全部入池了，只是内核配置没生效：清空输入，留下结果和警告
        setText("");
        setResult(summary);
        toast.warning(`${addedText}，但 mihomo 内核配置没有生效`);
        return;
      }
      // 有失败的行：只把失败的行留在输入框里方便修改后重试。
      // 后端回传的地址和输入对不上（例如被规范化）时保留原文，重复提交时成功的行会被当作重复跳过
      const failed = new Set(errors.map((item) => item.url));
      const remaining = urls.filter((url) => failed.has(url));
      const keptOnlyFailed = remaining.length === errors.length;
      setResult({ ...summary, keptOnlyFailed });
      if (keptOnlyFailed) {
        setText(remaining.join("\n"));
      }
      if (summary.hasShareLinks) {
        toast.warning(`${summary.added > 0 ? `${addedText}；` : ""}${errors.length} 项没有导入，原因见对话框`);
      } else {
        toast.error(`${errors.length} 个代理添加失败，请检查格式后重试`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "添加代理失败");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="w-[min(92vw,640px)]">
        <DialogHeader className="gap-2">
          <DialogTitle>批量添加代理</DialogTitle>
          <DialogDescription className="text-sm leading-6">
            一行一个代理，重复的地址会自动跳过；用户名或密码不同视为不同的代理。也可以粘贴分享链接，或把整段 Base64 订阅内容作为一行粘贴。
            {poolEnabled ? "代理池已开启，添加后会把未绑定的账号分配到新代理，已绑定的账号保持不变。" : null}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid gap-1.5 rounded-xl border border-border bg-field/50 px-3.5 py-2.5 text-xs">
            {formatExamples.map((entry) => (
              <div key={entry.format} className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
                <code className="font-mono text-foreground/80">{entry.format}</code>
                <span className="font-mono text-muted-foreground">例 {entry.example}</span>
              </div>
            ))}
            <div className="mt-1 space-y-0.5 border-t border-border pt-2">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
                <span className="text-foreground/80">分享链接</span>
                <code className="font-mono break-all text-muted-foreground">{shareLinkSchemes}</code>
              </div>
              <div className="text-foreground/80">整段 Base64 订阅内容（粘贴为一行）</div>
              <p className="leading-5 text-muted-foreground">
                分享链接需要启用 mihomo 内核；内核未启用时节点会先保存到「{MANUAL_SUBSCRIPTION_NAME}」，启用后可在「订阅」页的节点列表里补导入。
              </p>
            </div>
          </div>

          <Field>
            <div className="flex items-center justify-between gap-2">
              <FieldLabel htmlFor="proxy-pool-add-urls">代理列表</FieldLabel>
              <span className="text-xs text-muted-foreground tabular-nums">
                已识别 {urls.length} 行{shareLineCount > 0 ? `，其中分享链接 / 订阅内容 ${shareLineCount} 行` : ""}
              </span>
            </div>
            <Textarea
              id="proxy-pool-add-urls"
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder={formatExamples.map((entry) => entry.example).join("\n")}
              spellCheck={false}
              autoComplete="off"
              className="min-h-48 resize-y font-mono text-xs leading-5"
              disabled={isSubmitting}
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="proxy-pool-add-name">名称（可选）</FieldLabel>
            <Input
              id="proxy-pool-add-name"
              value={nameDisabled ? "" : name}
              onChange={(event) => setName(event.target.value)}
              placeholder={
                urls.length > 1
                  ? "批量添加时不设置名称，添加后可在列表里单独编辑"
                  : nameDisabled
                    ? "分享链接使用节点自己的名称"
                    : "例如：美国住宅 01"
              }
              disabled={isSubmitting || nameDisabled}
            />
          </Field>

          {result ? (
            <div className="space-y-2 rounded-xl border border-border bg-field/50 px-3.5 py-3 text-xs">
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-foreground/80">
                <span>
                  新增 <span className="font-semibold text-success tabular-nums">{result.added}</span>
                </span>
                <span>
                  跳过 <span className="font-semibold tabular-nums">{result.skipped}</span>
                </span>
                <span>
                  失败 <span className="font-semibold text-destructive tabular-nums">{result.errors.length}</span>
                </span>
                {result.assigned > 0 ? (
                  <span>
                    分配账号 <span className="font-semibold tabular-nums">{result.assigned}</span>
                  </span>
                ) : null}
              </div>
              {result.errors.length > 0 ? (
                <ul className="max-h-36 space-y-1 overflow-y-auto">
                  {result.errors.map((item, index) => (
                    <li key={`${item.url}-${index}`} className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
                      <code className="shrink-0 font-mono break-all text-foreground/80 sm:max-w-[55%]">{item.url}</code>
                      <span className="break-all text-destructive">{item.error}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
              {result.coreApply?.ok === false ? (
                <p className="rounded-lg bg-warning/12 px-2.5 py-1.5 leading-5 break-all text-warning">
                  节点已加入代理池，但 mihomo 内核配置没有生效：{result.coreApply.error || "未知错误"}。确认 proxy-core 已启动后，在「订阅」页的「mihomo 内核」里点「重新应用」。
                </p>
              ) : null}
              {result.errors.length > 0 && result.hasShareLinks ? (
                <p className="leading-5 text-muted-foreground">
                  分享链接的失败项按节点名称列出；因为未启用内核而没导入的节点已保存在「{MANUAL_SUBSCRIPTION_NAME}」，启用 mihomo 内核后在「订阅」页对它点「选择节点」补导入，不用重新粘贴。
                </p>
              ) : null}
              {result.errors.length > 0 ? (
                <p className="text-muted-foreground">
                  {result.keptOnlyFailed
                    ? "成功的行已移除，失败的行保留在上方输入框，修改后可再次提交。"
                    : "修改失败的行后可再次提交，已添加的代理会被当作重复自动跳过。"}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={() => handleOpenChange(false)} disabled={isSubmitting}>
            {result ? "关闭" : "取消"}
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={isSubmitting || urls.length === 0}>
            {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : <Plus className="size-4" />}
            {/* 一行 Base64 订阅内容可能展开成很多节点，这时不显示行数 */}
            {shareLineCount > 0 ? "添加" : `添加 ${urls.length > 0 ? urls.length : ""} 个`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
