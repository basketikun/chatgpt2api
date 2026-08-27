"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  LoaderCircle,
  ReceiptText,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  fetchInvoiceAccounts,
  fetchInvoices,
  type InvoiceAccount,
  type InvoiceItem,
} from "@/lib/api";
import { useAuthGuard } from "@/lib/use-auth-guard";

const DEFAULT_PAGE_SIZE = 20;

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value || "—";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatAmount(amount: number, currency: string) {
  const normalizedCurrency = currency.toUpperCase();
  try {
    const formatter = new Intl.NumberFormat("zh-CN", {
      style: "currency",
      currency: normalizedCurrency,
    });
    const digits = formatter.resolvedOptions().maximumFractionDigits ?? 2;
    return formatter.format(amount / 10 ** digits);
  } catch {
    return `${normalizedCurrency} ${amount}`;
  }
}

function statusVariant(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "paid") return "success" as const;
  if (normalized === "open" || normalized === "draft") return "warning" as const;
  if (normalized === "void" || normalized === "uncollectible") return "danger" as const;
  return "secondary" as const;
}

function accountLabel(account: InvoiceAccount) {
  const identity = account.email || account.account_id;
  return account.plan ? `${identity} · ${account.plan}` : identity;
}

function trustedInvoiceUrl(value: string | null | undefined) {
  try {
    const target = new URL(value || "");
    if (target.protocol === "https:" && target.hostname === "invoice.stripe.com") {
      return target.toString();
    }
  } catch {
    // The server also validates this; keep the UI fail-closed if data is stale or tampered with.
  }
  return "";
}

function InvoicesPageContent() {
  const requestIdRef = useRef(0);
  const [accounts, setAccounts] = useState<InvoiceAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [items, setItems] = useState<InvoiceItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<string[]>([""]);
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [isLoadingAccounts, setIsLoadingAccounts] = useState(true);
  const [isLoadingInvoices, setIsLoadingInvoices] = useState(false);

  const selectedAccount = useMemo(
    () => accounts.find((account) => account.account_id === selectedAccountId) || null,
    [accounts, selectedAccountId],
  );
  const currentCursor = cursorHistory[pageIndex] || "";

  const loadInvoices = async (accountId: string, cursor: string, limit: number) => {
    const requestId = ++requestIdRef.current;
    setIsLoadingInvoices(true);
    try {
      const payload = await fetchInvoices(accountId, limit, cursor);
      if (requestId !== requestIdRef.current) return;
      setItems(payload.items);
      setNextCursor(payload.next_cursor || null);
    } catch (error) {
      if (requestId !== requestIdRef.current) return;
      setItems([]);
      setNextCursor(null);
      toast.error(error instanceof Error ? error.message : "加载发票失败");
    } finally {
      if (requestId === requestIdRef.current) {
        setIsLoadingInvoices(false);
      }
    }
  };

  useEffect(() => {
    let active = true;
    const load = async () => {
      setIsLoadingAccounts(true);
      try {
        const payload = await fetchInvoiceAccounts();
        if (!active) return;
        setAccounts(payload.items);
        const initialAccountId = payload.items[0]?.account_id || "";
        setSelectedAccountId(initialAccountId);
        if (initialAccountId) {
          void loadInvoices(initialAccountId, "", DEFAULT_PAGE_SIZE);
        }
      } catch (error) {
        if (active) {
          toast.error(error instanceof Error ? error.message : "加载账单账号失败");
        }
      } finally {
        if (active) setIsLoadingAccounts(false);
      }
    };
    void load();
    return () => {
      active = false;
      requestIdRef.current += 1;
    };
  }, []);

  const selectAccount = (accountId: string) => {
    setSelectedAccountId(accountId);
    setCursorHistory([""]);
    setPageIndex(0);
    setItems([]);
    setNextCursor(null);
    if (accountId) {
      void loadInvoices(accountId, "", pageSize);
    }
  };

  const changePageSize = (value: string) => {
    const nextPageSize = Number(value);
    setPageSize(nextPageSize);
    setCursorHistory([""]);
    setPageIndex(0);
    setItems([]);
    setNextCursor(null);
    if (selectedAccountId) {
      void loadInvoices(selectedAccountId, "", nextPageSize);
    }
  };

  const goNext = () => {
    if (!selectedAccountId || !nextCursor || isLoadingInvoices) return;
    const nextIndex = pageIndex + 1;
    setCursorHistory((current) => [...current.slice(0, nextIndex), nextCursor]);
    setPageIndex(nextIndex);
    void loadInvoices(selectedAccountId, nextCursor, pageSize);
  };

  const goPrevious = () => {
    if (!selectedAccountId || pageIndex === 0 || isLoadingInvoices) return;
    const previousIndex = pageIndex - 1;
    const previousCursor = cursorHistory[previousIndex] || "";
    setPageIndex(previousIndex);
    void loadInvoices(selectedAccountId, previousCursor, pageSize);
  };

  const reload = () => {
    if (selectedAccountId) {
      void loadInvoices(selectedAccountId, currentCursor, pageSize);
    }
  };

  return (
    <div className="flex flex-1 flex-col gap-4 pb-8">
      <section className="flex flex-col gap-4 rounded-3xl border border-white/70 bg-white/80 p-5 shadow-[0_20px_60px_-28px_rgba(25,33,61,0.18)] backdrop-blur dark:border-white/10 dark:bg-stone-950/70 sm:flex-row sm:items-end sm:justify-between sm:p-7">
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium text-stone-500 dark:text-stone-400">
            <ReceiptText className="size-4" />
            ChatGPT 账单
          </div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">发票中心</h1>
          <p className="max-w-2xl text-sm leading-6 text-stone-500 dark:text-stone-400">
            查看账号的全部历史发票。发票链接来自当前列表响应，只在浏览器中使用，不会持久化或写入服务端日志。
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          className="rounded-xl"
          disabled={!selectedAccountId || isLoadingInvoices}
          onClick={reload}
        >
          <RefreshCw className={`mr-2 size-4 ${isLoadingInvoices ? "animate-spin" : ""}`} />
          刷新
        </Button>
      </section>

      <Card className="border-white/70 bg-white/90 dark:border-white/10 dark:bg-stone-950/80">
        <CardHeader className="gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="space-y-1.5">
            <CardTitle>历史发票</CardTitle>
            <CardDescription>
              {selectedAccount ? accountLabel(selectedAccount) : "请选择一个有账单身份的账号"}
            </CardDescription>
          </div>
          <div className="grid gap-3 sm:grid-cols-[minmax(260px,1fr)_120px]">
            <Select
              value={selectedAccountId}
              onValueChange={selectAccount}
              disabled={isLoadingAccounts || accounts.length === 0}
            >
              <SelectTrigger className="rounded-xl">
                <SelectValue placeholder={isLoadingAccounts ? "加载账号中…" : "选择账号"} />
              </SelectTrigger>
              <SelectContent>
                {accounts.map((account) => (
                  <SelectItem key={account.account_id} value={account.account_id}>
                    {accountLabel(account)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={String(pageSize)} onValueChange={changePageSize}>
              <SelectTrigger className="rounded-xl">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="10">每页 10 张</SelectItem>
                <SelectItem value="20">每页 20 张</SelectItem>
                <SelectItem value="50">每页 50 张</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-hidden rounded-2xl border border-stone-100 dark:border-white/10">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent dark:border-white/10">
                    <TableHead>日期</TableHead>
                    <TableHead>金额</TableHead>
                    <TableHead>方案</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isLoadingInvoices ? (
                    <TableRow className="hover:bg-transparent dark:border-white/10">
                      <TableCell colSpan={5} className="h-40 text-center text-stone-500">
                        <LoaderCircle className="mx-auto mb-3 size-5 animate-spin" />
                        正在加载发票…
                      </TableCell>
                    </TableRow>
                  ) : items.length === 0 ? (
                    <TableRow className="hover:bg-transparent dark:border-white/10">
                      <TableCell colSpan={5} className="h-48 text-center">
                        <FileText className="mx-auto mb-3 size-8 text-stone-300 dark:text-stone-600" />
                        <div className="font-medium text-stone-700 dark:text-stone-200">
                          {accounts.length === 0 ? "没有可读取账单的账号" : "这一页没有发票"}
                        </div>
                        <div className="mt-1 text-sm text-stone-400">
                          账号身份缺失或重复时会安全地从列表中排除。
                        </div>
                      </TableCell>
                    </TableRow>
                  ) : (
                    items.map((invoice) => {
                      const invoiceUrl = trustedInvoiceUrl(invoice.invoice_url);
                      return (
                        <TableRow key={invoice.id} className="dark:border-white/10 dark:hover:bg-white/5">
                          <TableCell className="whitespace-nowrap text-stone-600 dark:text-stone-300">
                            {formatDate(invoice.created_at)}
                          </TableCell>
                          <TableCell className="whitespace-nowrap font-semibold">
                            {formatAmount(invoice.amount, invoice.currency)}
                          </TableCell>
                          <TableCell>
                            <div className="font-medium">{invoice.product.plan || "—"}</div>
                            <div className="text-xs text-stone-400">
                              {invoice.product.type || "subscription"}
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge variant={statusVariant(invoice.status)}>{invoice.status}</Badge>
                          </TableCell>
                          <TableCell className="text-right">
                            {invoiceUrl ? (
                              <Button asChild size="sm" variant="outline" className="rounded-xl">
                                <a href={invoiceUrl} target="_blank" rel="noopener noreferrer">
                                  <ExternalLink className="mr-2 size-4" />
                                  打开发票
                                </a>
                              </Button>
                            ) : (
                              <Button type="button" size="sm" variant="outline" className="rounded-xl" disabled>
                                <ExternalLink className="mr-2 size-4" />
                                无可用链接
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </Table>
            </div>
          </div>

          <div className="mt-4 flex items-center justify-between gap-3">
            <div className="text-sm text-stone-400">第 {pageIndex + 1} 页 · 当前 {items.length} 张</div>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                className="rounded-xl"
                disabled={pageIndex === 0 || isLoadingInvoices}
                onClick={goPrevious}
              >
                <ChevronLeft className="mr-1 size-4" />
                上一页
              </Button>
              <Button
                type="button"
                variant="outline"
                className="rounded-xl"
                disabled={!nextCursor || isLoadingInvoices}
                onClick={goNext}
              >
                下一页
                <ChevronRight className="ml-1 size-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function InvoicesPage() {
  const { isCheckingAuth, session } = useAuthGuard(["admin"]);
  if (isCheckingAuth || !session || session.role !== "admin") {
    return <div className="min-h-[60vh]" />;
  }
  return <InvoicesPageContent />;
}
