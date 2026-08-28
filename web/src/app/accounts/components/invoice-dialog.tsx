"use client";

import { useEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  LoaderCircle,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  type Account,
  type InvoiceAccount,
  type InvoiceItem,
} from "@/lib/api";

const DEFAULT_PAGE_SIZE = 20;

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "—";
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

function trustedInvoiceUrl(value: string | null | undefined) {
  try {
    const target = new URL(value || "");
    if (target.protocol === "https:" && target.hostname === "invoice.stripe.com") {
      return target.toString();
    }
  } catch {
    // The server performs the same validation; fail closed if client state was tampered with.
  }
  return "";
}

function resolveInvoiceAccount(account: Account, options: InvoiceAccount[]) {
  const storedAccountId = String(account.account_id || "").trim();
  if (storedAccountId) {
    const exactMatches = options.filter((option) => option.account_id === storedAccountId);
    if (exactMatches.length === 1) return exactMatches[0];
    return null;
  }

  const email = String(account.email || "").trim().toLowerCase();
  if (!email) return null;
  const emailMatches = options.filter((option) => String(option.email || "").trim().toLowerCase() === email);
  if (emailMatches.length === 1) return emailMatches[0];

  const plan = String(account.type || "").trim().toLowerCase();
  const narrowed = emailMatches.filter((option) => String(option.plan || "").trim().toLowerCase() === plan);
  return narrowed.length === 1 ? narrowed[0] : null;
}

type InvoiceDialogProps = {
  account: Account | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function InvoiceDialog({ account, open, onOpenChange }: InvoiceDialogProps) {
  const requestIdRef = useRef(0);
  const [invoiceAccount, setInvoiceAccount] = useState<InvoiceAccount | null>(null);
  const [items, setItems] = useState<InvoiceItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<string[]>([""]);
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [isResolvingAccount, setIsResolvingAccount] = useState(false);
  const [isLoadingInvoices, setIsLoadingInvoices] = useState(false);
  const [identityError, setIdentityError] = useState("");

  const currentCursor = cursorHistory[pageIndex] || "";

  const loadInvoices = async (accountId: string, cursor: string, limit: number) => {
    const requestId = ++requestIdRef.current;
    setIsLoadingInvoices(true);
    setIdentityError("");
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
      if (requestId === requestIdRef.current) setIsLoadingInvoices(false);
    }
  };

  useEffect(() => {
    let active = true;
    const resolve = async () => {
      await Promise.resolve();
      if (!active) return;
      requestIdRef.current += 1;
      setInvoiceAccount(null);
      setItems([]);
      setNextCursor(null);
      setCursorHistory([""]);
      setPageIndex(0);
      setPageSize(DEFAULT_PAGE_SIZE);
      setIdentityError("");
      setIsLoadingInvoices(false);

      if (!open || !account) {
        setIsResolvingAccount(false);
        return;
      }

      setIsResolvingAccount(true);
      try {
        const payload = await fetchInvoiceAccounts();
        if (!active) return;
        const resolved = resolveInvoiceAccount(account, payload.items);
        if (!resolved) {
          setIdentityError("该账号没有唯一可用的账单身份，无法读取发票。");
          return;
        }
        setInvoiceAccount(resolved);
        void loadInvoices(resolved.account_id, "", DEFAULT_PAGE_SIZE);
      } catch (error) {
        if (active) {
          setIdentityError(error instanceof Error ? error.message : "解析账单账号失败");
        }
      } finally {
        if (active) setIsResolvingAccount(false);
      }
    };
    void resolve();

    return () => {
      active = false;
      requestIdRef.current += 1;
    };
  }, [account, open]);

  const changePageSize = (value: string) => {
    if (!invoiceAccount) return;
    const nextPageSize = Number(value);
    setPageSize(nextPageSize);
    setCursorHistory([""]);
    setPageIndex(0);
    setItems([]);
    setNextCursor(null);
    void loadInvoices(invoiceAccount.account_id, "", nextPageSize);
  };

  const goNext = () => {
    if (!invoiceAccount || !nextCursor || isLoadingInvoices) return;
    const nextIndex = pageIndex + 1;
    setCursorHistory((current) => [...current.slice(0, nextIndex), nextCursor]);
    setPageIndex(nextIndex);
    void loadInvoices(invoiceAccount.account_id, nextCursor, pageSize);
  };

  const goPrevious = () => {
    if (!invoiceAccount || pageIndex === 0 || isLoadingInvoices) return;
    const previousIndex = pageIndex - 1;
    const previousCursor = cursorHistory[previousIndex] || "";
    setPageIndex(previousIndex);
    void loadInvoices(invoiceAccount.account_id, previousCursor, pageSize);
  };

  const reload = () => {
    if (invoiceAccount) void loadInvoices(invoiceAccount.account_id, currentCursor, pageSize);
  };

  const renderInvoiceAction = (invoice: InvoiceItem) => {
    const invoiceUrl = trustedInvoiceUrl(invoice.invoice_url);
    return invoiceUrl ? (
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
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[92vh] w-[calc(100vw-1.5rem)] max-w-5xl flex-col overflow-hidden rounded-2xl p-0">
        <DialogHeader className="border-b border-stone-100 px-5 py-5 pr-12 text-left dark:border-white/10 sm:px-6">
          <DialogTitle>历史发票</DialogTitle>
          <DialogDescription>
            {invoiceAccount
              ? `${invoiceAccount.email || account?.email || invoiceAccount.account_id}${invoiceAccount.plan ? ` · ${invoiceAccount.plan}` : ""}`
              : account?.email || "正在解析当前账号的账单身份…"}
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex flex-col gap-3 border-b border-stone-100 px-5 py-3 dark:border-white/10 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <div className="text-sm text-stone-500">
              {invoiceAccount ? `第 ${pageIndex + 1} 页 · 当前 ${items.length} 张` : "发票仅显示当前号池账号"}
            </div>
            <div className="flex items-center gap-2">
              <Select value={String(pageSize)} onValueChange={changePageSize} disabled={!invoiceAccount}>
                <SelectTrigger className="h-9 w-32 rounded-xl">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="10">每页 10 张</SelectItem>
                  <SelectItem value="20">每页 20 张</SelectItem>
                  <SelectItem value="50">每页 50 张</SelectItem>
                </SelectContent>
              </Select>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="rounded-xl"
                disabled={!invoiceAccount || isLoadingInvoices}
                onClick={reload}
              >
                <RefreshCw className={`mr-2 size-4 ${isLoadingInvoices ? "animate-spin" : ""}`} />
                刷新
              </Button>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 sm:px-6">
            {isResolvingAccount || isLoadingInvoices ? (
              <div className="flex min-h-64 flex-col items-center justify-center text-sm text-stone-500">
                <LoaderCircle className="mb-3 size-5 animate-spin" />
                {isResolvingAccount ? "正在解析账单账号…" : "正在加载发票…"}
              </div>
            ) : identityError ? (
              <div className="flex min-h-64 flex-col items-center justify-center px-4 text-center">
                <FileText className="mb-3 size-8 text-stone-300 dark:text-stone-600" />
                <div className="font-medium text-stone-700 dark:text-stone-200">无法读取该账号的发票</div>
                <div className="mt-1 max-w-md text-sm text-stone-400">{identityError}</div>
              </div>
            ) : items.length === 0 ? (
              <div className="flex min-h-64 flex-col items-center justify-center px-4 text-center">
                <FileText className="mb-3 size-8 text-stone-300 dark:text-stone-600" />
                <div className="font-medium text-stone-700 dark:text-stone-200">这一页没有发票</div>
              </div>
            ) : (
              <>
                <div className="space-y-3 sm:hidden">
                  {items.map((invoice) => (
                    <div key={invoice.id} className="rounded-2xl border border-stone-100 p-4 dark:border-white/10">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="font-semibold">{formatAmount(invoice.amount, invoice.currency)}</div>
                          <div className="mt-1 text-xs text-stone-400">{formatDate(invoice.created_at)}</div>
                        </div>
                        <Badge variant={statusVariant(invoice.status)}>{invoice.status}</Badge>
                      </div>
                      <div className="mt-3 text-sm text-stone-600 dark:text-stone-300">
                        {invoice.product.plan || "—"}
                      </div>
                      <div className="mt-4">{renderInvoiceAction(invoice)}</div>
                    </div>
                  ))}
                </div>

                <div className="hidden overflow-hidden rounded-2xl border border-stone-100 dark:border-white/10 sm:block">
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
                        {items.map((invoice) => (
                          <TableRow key={invoice.id} className="dark:border-white/10 dark:hover:bg-white/5">
                            <TableCell className="whitespace-nowrap text-stone-600 dark:text-stone-300">
                              {formatDate(invoice.created_at)}
                            </TableCell>
                            <TableCell className="whitespace-nowrap font-semibold">
                              {formatAmount(invoice.amount, invoice.currency)}
                            </TableCell>
                            <TableCell>
                              <div className="font-medium">{invoice.product.plan || "—"}</div>
                              <div className="text-xs text-stone-400">{invoice.product.type || "subscription"}</div>
                            </TableCell>
                            <TableCell>
                              <Badge variant={statusVariant(invoice.status)}>{invoice.status}</Badge>
                            </TableCell>
                            <TableCell className="text-right">{renderInvoiceAction(invoice)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              </>
            )}
          </div>

          <div className="flex items-center justify-between gap-3 border-t border-stone-100 px-5 py-4 dark:border-white/10 sm:px-6">
            <Button
              type="button"
              size="sm"
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
              size="sm"
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
      </DialogContent>
    </Dialog>
  );
}
