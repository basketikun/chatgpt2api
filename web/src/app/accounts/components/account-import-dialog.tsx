"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type ChangeEvent } from "react";
import {
  ArrowLeft,
  Copy,
  ExternalLink,
  FileJson,
  FileText,
  Files,
  KeyRound,
  LoaderCircle,
  LogIn,
  ServerCog,
  Upload,
} from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  createAccounts,
  finishOAuthLogin,
  startOAuthLogin,
  type Account,
  type AccountImportPayload,
  type OAuthLoginStartResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type ImportMethod = "menu" | "token" | "session" | "codex-auth" | "account-json" | "oauth";

type AccountImportDialogProps = {
  disabled?: boolean;
  onImported: (items: Account[]) => void;
};

type PendingAccountJsonImport = {
  tokens: string[];
  accounts: AccountImportPayload[];
  parsedAccountCount: number;
  errorCount: number;
};

const sessionUrl = "https://chatgpt.com/api/auth/session";

function splitTokens(value: string) {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function getSessionAccessToken(value: unknown) {
  const token = (value as { accessToken?: unknown })?.accessToken;
  return typeof token === "string" ? token.trim() : "";
}

function getAccountJsonAccount(value: unknown): AccountImportPayload | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const raw = value as Record<string, unknown>;
  const tokenValue = raw.access_token ?? raw.accessToken;
  const token = typeof tokenValue === "string" ? tokenValue.trim() : "";
  if (!token) {
    return null;
  }

  const payload: AccountImportPayload = {
    ...raw,
    access_token: token,
    source_type: "codex",
  };
  delete payload.accessToken;
  if (payload.type === "codex") {
    payload.export_type = "codex";
    delete payload.type;
  }
  return payload;
}

function getAccountJsonAccounts(value: unknown): AccountImportPayload[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => getAccountJsonAccount(item))
      .filter((item): item is AccountImportPayload => Boolean(item));
  }

  const singleAccount = getAccountJsonAccount(value);
  if (singleAccount) {
    return [singleAccount];
  }

  if (value && typeof value === "object") {
    const raw = value as Record<string, unknown>;
    const nested = raw.accounts ?? raw.items;
    if (Array.isArray(nested)) {
      return nested
        .map((item) => getAccountJsonAccount(item))
        .filter((item): item is AccountImportPayload => Boolean(item));
    }
  }

  return [];
}

function getCodexAuthAccount(value: unknown): AccountImportPayload | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const raw = value as Record<string, unknown>;
  const tokenValue = raw.access_token ?? raw.accessToken;
  const token = typeof tokenValue === "string" ? tokenValue.trim() : "";
  if (!token) {
    return null;
  }

  const payload: AccountImportPayload = {
    ...raw,
    access_token: token,
    export_type: "codex",
    source_type: "codex",
  };
  delete payload.accessToken;
  if (payload.type === "codex") {
    delete payload.type;
  }
  return payload;
}

function readFileAsText(t: TFunction, file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => reject(reader.error ?? new Error(t("importDialog.toasts.readFileFailed", { name: file.name })));
    reader.readAsText(file);
  });
}

function MethodCard({
  title,
  description,
  icon: Icon,
  onClick,
}: {
  title: string;
  description: string;
  icon: typeof KeyRound;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-2xl border border-stone-200 bg-white p-0 text-left transition hover:border-stone-300 hover:bg-stone-50"
    >
      <Card className="rounded-2xl border-0 bg-transparent shadow-none">
        <CardContent className="flex items-start gap-4 p-4">
          <div className="rounded-xl bg-stone-100 p-3 text-stone-700">
            <Icon className="size-5" />
          </div>
          <div className="space-y-1">
            <div className="text-sm font-semibold text-stone-900">{title}</div>
            <div className="text-sm leading-6 text-stone-500">{description}</div>
          </div>
        </CardContent>
      </Card>
    </button>
  );
}

export function AccountImportDialog({ disabled, onImported }: AccountImportDialogProps) {
  const { t } = useTranslation("accounts");
  const { t: tCommon } = useTranslation("common");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [method, setMethod] = useState<ImportMethod>("menu");
  const [tokenInput, setTokenInput] = useState("");
  const [sessionInput, setSessionInput] = useState("");
  const [codexAuthInput, setCodexAuthInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [pendingAccountJsonImport, setPendingAccountJsonImport] = useState<PendingAccountJsonImport | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [oauthEmailHint, setOauthEmailHint] = useState("");
  const [oauthSession, setOauthSession] = useState<OAuthLoginStartResponse | null>(null);
  const [oauthCallbackInput, setOauthCallbackInput] = useState("");
  const [oauthStarting, setOauthStarting] = useState(false);

  const txtInputRef = useRef<HTMLInputElement | null>(null);
  const accountJsonInputRef = useRef<HTMLInputElement | null>(null);

  const resetState = () => {
    setMethod("menu");
    setTokenInput("");
    setSessionInput("");
    setCodexAuthInput("");
    setPendingAccountJsonImport(null);
    setConfirmOpen(false);
    setOauthEmailHint("");
    setOauthSession(null);
    setOauthCallbackInput("");
    setOauthStarting(false);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) {
      resetState();
    }
  };

  const submitTokens = async (tokens: string[], successText?: string, accountPayloads: AccountImportPayload[] = []) => {
    const normalizedTokens = tokens.map((item) => item.trim()).filter(Boolean);

    if (normalizedTokens.length === 0) {
      toast.error(t("importDialog.toasts.provideTokenRequired"));
      return;
    }

    setIsSubmitting(true);
    try {
      const data = await createAccounts(normalizedTokens, accountPayloads);
      onImported(data.items);
      setOpen(false);
      resetState();

      const prefix = successText ?? t("importDialog.toasts.importCompleteDefault");
      if ((data.errors?.length ?? 0) > 0) {
        const firstError = data.errors?.[0]?.error;
        toast.error(
          t("importDialog.toasts.resultWithErrors", {
            prefix,
            added: data.added ?? 0,
            refreshed: data.refreshed ?? 0,
            failed: data.errors?.length ?? 0,
          }) + (firstError ? t("toasts.firstErrorSuffix", { error: firstError }) : ""),
        );
      } else {
        toast.success(
          t("importDialog.toasts.resultSuccess", { prefix, added: data.added ?? 0, count: data.skipped ?? 0 }),
        );
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : t("importDialog.toasts.importFailed");
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleImportTokenText = async () => {
    await submitTokens(splitTokens(tokenInput), t("importDialog.toasts.tokenImportComplete"));
  };

  const handleStartOAuth = async () => {
    setOauthStarting(true);
    try {
      const data = await startOAuthLogin(oauthEmailHint.trim());
      setOauthSession(data);
      setOauthCallbackInput("");
      if (typeof window !== "undefined") {
        window.open(data.authorize_url, "_blank", "noopener,noreferrer");
      }
      toast.success(t("importDialog.toasts.oauthOpened"));
    } catch (error) {
      const message = error instanceof Error ? error.message : t("importDialog.toasts.oauthStartFailed");
      toast.error(message);
    } finally {
      setOauthStarting(false);
    }
  };

  const handleFinishOAuth = async () => {
    if (!oauthSession) {
      toast.error(t("importDialog.toasts.oauthSessionMissing"));
      return;
    }
    const trimmed = oauthCallbackInput.trim();
    if (!trimmed) {
      toast.error(t("importDialog.toasts.pasteCallbackRequired"));
      return;
    }

    setIsSubmitting(true);
    try {
      const data = await finishOAuthLogin(oauthSession.session_id, trimmed);
      onImported(data.items);
      setOpen(false);
      resetState();

      const prefix = t("importDialog.toasts.oauthLoginComplete");
      if ((data.errors?.length ?? 0) > 0) {
        const firstError = data.errors?.[0]?.error;
        toast.error(
          t("importDialog.toasts.resultWithErrors", {
            prefix,
            added: data.added ?? 0,
            refreshed: data.refreshed ?? 0,
            failed: data.errors?.length ?? 0,
          }) + (firstError ? t("toasts.firstErrorSuffix", { error: firstError }) : ""),
        );
      } else {
        toast.success(
          t("importDialog.toasts.resultSuccess", { prefix, added: data.added ?? 0, count: data.skipped ?? 0 }),
        );
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : t("importDialog.toasts.oauthExchangeFailed");
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCopyAuthorizeUrl = async () => {
    if (!oauthSession) {
      return;
    }
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(oauthSession.authorize_url);
        toast.success(t("importDialog.toasts.authUrlCopied"));
      } else {
        toast.error(t("importDialog.toasts.copyUnsupported"));
      }
    } catch {
      toast.error(t("importDialog.toasts.copyFailed"));
    }
  };

  const handleTxtSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) {
      return;
    }

    try {
      const content = await readFileAsText(t, file);
      const tokens = splitTokens(content);

      if (tokens.length === 0) {
        toast.error(t("importDialog.toasts.txtNoTokens"));
        return;
      }

      setTokenInput((prev) => {
        const next = [...splitTokens(prev), ...tokens];
        return next.join("\n");
      });
      toast.success(t("importDialog.toasts.txtReadSuccess", { name: file.name, count: tokens.length }));
    } catch (error) {
      const message = error instanceof Error ? error.message : t("importDialog.toasts.readTxtFailed");
      toast.error(message);
    }
  };

  const handleImportSessionJson = async () => {
    if (!sessionInput.trim()) {
      toast.error(t("importDialog.toasts.sessionRequired"));
      return;
    }

    try {
      const payload = JSON.parse(sessionInput) as unknown;
      const token = getSessionAccessToken(payload);

      if (!token) {
        toast.error(t("importDialog.toasts.sessionNoToken"));
        return;
      }

      await submitTokens([token], t("importDialog.toasts.sessionImportComplete"));
    } catch (error) {
      const message = error instanceof Error ? error.message : t("importDialog.toasts.sessionParseFailed");
      toast.error(message);
    }
  };

  const handleImportCodexAuthJson = async () => {
    if (!codexAuthInput.trim()) {
      toast.error(t("importDialog.toasts.codexAuthRequired"));
      return;
    }

    try {
      const payload = JSON.parse(codexAuthInput) as unknown;
      const account = getCodexAuthAccount(payload);

      if (!account) {
        toast.error(t("importDialog.toasts.codexAuthNoToken"));
        return;
      }

      await submitTokens([account.access_token], t("importDialog.toasts.codexImportComplete"), [account]);
    } catch (error) {
      const message = error instanceof Error ? error.message : t("importDialog.toasts.codexAuthParseFailed");
      toast.error(message);
    }
  };

  const handleAccountJsonSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";

    if (files.length === 0) {
      return;
    }

    try {
      const results = await Promise.all(
        files.map(async (file) => {
          const raw = await readFileAsText(t, file);
          const parsed = JSON.parse(raw) as unknown;
          const accounts = getAccountJsonAccounts(parsed);
          return {
            accounts,
          };
        }),
      );

      const accounts = results.flatMap((item) => item.accounts);
      const tokens = accounts.map((item) => item.access_token);
      const parsedAccountCount = accounts.length;
      const errorCount = results.filter((item) => item.accounts.length === 0).length;

      if (parsedAccountCount === 0) {
        toast.error(t("importDialog.toasts.accountJsonNoTokens"));
        return;
      }

      setPendingAccountJsonImport({
        tokens,
        accounts,
        parsedAccountCount,
        errorCount,
      });
      setConfirmOpen(true);
    } catch (error) {
      const message = error instanceof Error ? error.message : t("importDialog.toasts.accountJsonReadFailed");
      toast.error(message);
    }
  };

  const renderMethodBody = () => {
    if (method === "token") {
      const tokenCount = splitTokens(tokenInput).length;

      return (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setMethod("menu")}
              className="inline-flex items-center gap-1 text-sm text-stone-500 transition hover:text-stone-800"
            >
              <ArrowLeft className="size-4" />
              {t("importDialog.back")}
            </button>
            <span className="text-xs text-stone-400">{t("importDialog.token.recognizedCount", { count: tokenCount })}</span>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-stone-700">{t("importDialog.token.listLabel")}</label>
            <Textarea
              placeholder={t("importDialog.token.placeholder")}
              value={tokenInput}
              onChange={(event) => setTokenInput(event.target.value)}
              className="min-h-56 resize-none rounded-xl border-stone-200"
            />
          </div>
          <div className="rounded-2xl border border-dashed border-stone-200 bg-stone-50 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="space-y-1">
                <div className="text-sm font-medium text-stone-800">{t("importDialog.token.fromTxtTitle")}</div>
                <div className="text-sm leading-6 text-stone-500">{t("importDialog.token.fromTxtHint")}</div>
              </div>
              <Button
                type="button"
                variant="outline"
                className="rounded-xl border-stone-200 bg-white"
                onClick={() => txtInputRef.current?.click()}
                disabled={isSubmitting}
              >
                <FileText className="size-4" />
                {t("importDialog.token.chooseTxtButton")}
              </Button>
            </div>
          </div>
          <input
            ref={txtInputRef}
            type="file"
            accept=".txt,text/plain"
            className="hidden"
            onChange={(event) => void handleTxtSelected(event)}
          />
        </div>
      );
    }

    if (method === "session") {
      return (
        <div className="space-y-4">
          <button
            type="button"
            onClick={() => setMethod("menu")}
            className="inline-flex items-center gap-1 text-sm text-stone-500 transition hover:text-stone-800"
          >
            <ArrowLeft className="size-4" />
            {t("importDialog.back")}
          </button>
          <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4 text-sm leading-6 text-stone-600">
            {t("importDialog.session.openPrefix")}
            {" "}
            <a
              href={sessionUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 font-medium text-stone-900 underline underline-offset-4"
            >
              {sessionUrl}
              <ExternalLink className="size-3.5" />
            </a>
            {t("importDialog.session.instructionSuffix")}
          </div>
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
            <div className="font-medium">{t("importDialog.session.riskTitle")}</div>
            <div>
              {t("importDialog.session.riskBody")}
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-stone-700">{t("importDialog.session.jsonLabel")}</label>
            <Textarea
              placeholder={t("importDialog.session.placeholder")}
              value={sessionInput}
              onChange={(event) => setSessionInput(event.target.value)}
              className="min-h-56 resize-none rounded-xl border-stone-200 font-mono text-xs"
            />
          </div>
        </div>
      );
    }

    if (method === "oauth") {
      return (
        <div className="space-y-4">
          <button
            type="button"
            onClick={() => setMethod("menu")}
            className="inline-flex items-center gap-1 text-sm text-stone-500 transition hover:text-stone-800"
          >
            <ArrowLeft className="size-4" />
            {t("importDialog.back")}
          </button>
          <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4 text-sm leading-6 text-stone-600 space-y-2">
            <div className="font-medium text-stone-800">{t("importDialog.oauth.stepsTitle")}</div>
            <ol className="list-decimal pl-5 space-y-1">
              <li>{t("importDialog.oauth.step1")}</li>
              <li>{t("importDialog.oauth.step2")}</li>
              <li>{t("importDialog.oauth.step3Prefix")}<code className="rounded bg-stone-200 px-1">platform.openai.com/auth/callback?code=...</code>{t("importDialog.oauth.step3Suffix")}</li>
              <li>{t("importDialog.oauth.step4")}</li>
            </ol>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-stone-700">{t("importDialog.oauth.emailLabel")}</label>
            <input
              type="email"
              placeholder="you@example.com"
              value={oauthEmailHint}
              onChange={(event) => setOauthEmailHint(event.target.value)}
              disabled={Boolean(oauthSession) || oauthStarting}
              className="w-full rounded-xl border border-stone-200 bg-white px-3 py-2 text-sm outline-none focus:border-stone-400"
            />
          </div>
          {!oauthSession ? (
            <Button
              type="button"
              className="h-10 rounded-xl bg-stone-950 text-white hover:bg-stone-800"
              onClick={() => void handleStartOAuth()}
              disabled={oauthStarting}
            >
              {oauthStarting ? <LoaderCircle className="size-4 animate-spin" /> : <ExternalLink className="size-4" />}
              {t("importDialog.oauth.openAuthButton")}
            </Button>
          ) : (
            <div className="space-y-3">
              <div className="rounded-2xl border border-stone-200 bg-white p-3 text-xs leading-6 text-stone-600 break-all font-mono">
                {oauthSession.authorize_url}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  className="rounded-xl border-stone-200 bg-white"
                  onClick={() => void handleCopyAuthorizeUrl()}
                >
                  <Copy className="size-4" />
                  {t("importDialog.oauth.copyAuthUrlButton")}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="rounded-xl border-stone-200 bg-white"
                  onClick={() => window.open(oauthSession.authorize_url, "_blank", "noopener,noreferrer")}
                >
                  <ExternalLink className="size-4" />
                  {t("importDialog.oauth.reopenButton")}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="rounded-xl border-stone-200 bg-white"
                  onClick={() => {
                    setOauthSession(null);
                    setOauthCallbackInput("");
                  }}
                >
                  {t("importDialog.oauth.regenerateButton")}
                </Button>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-stone-700">{t("importDialog.oauth.pasteCallbackLabel")}</label>
                <Textarea
                  placeholder={"https://platform.openai.com/auth/callback?code=...&state=..."}
                  value={oauthCallbackInput}
                  onChange={(event) => setOauthCallbackInput(event.target.value)}
                  className="min-h-24 resize-none rounded-xl border-stone-200 font-mono text-xs"
                />
              </div>
            </div>
          )}
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
            <div className="font-medium">{t("importDialog.oauth.noteTitle")}</div>
            <div>
              {t("importDialog.oauth.noteBody")}
            </div>
          </div>
        </div>
      );
    }

    if (method === "account-json") {
      return (
        <div className="space-y-4">
          <button
            type="button"
            onClick={() => setMethod("menu")}
            className="inline-flex items-center gap-1 text-sm text-stone-500 transition hover:text-stone-800"
          >
            <ArrowLeft className="size-4" />
            {t("importDialog.back")}
          </button>
          <div className="rounded-2xl border border-dashed border-stone-200 bg-stone-50 p-5">
            <div className="space-y-2">
              <div className="text-sm font-medium text-stone-800">{t("importDialog.accountJson.chooseTitle")}</div>
              <div className="text-sm leading-6 text-stone-500">
                {t("importDialog.accountJson.hint")}
              </div>
            </div>
            <Button
              type="button"
              className="mt-4 rounded-xl bg-stone-950 text-white hover:bg-stone-800"
              onClick={() => accountJsonInputRef.current?.click()}
              disabled={isSubmitting}
            >
              <Files className="size-4" />
              {t("importDialog.accountJson.chooseButton")}
            </Button>
          </div>
          <input
            ref={accountJsonInputRef}
            type="file"
            accept=".json,application/json"
            multiple
            className="hidden"
            onChange={(event) => void handleAccountJsonSelected(event)}
          />
          {pendingAccountJsonImport ? (
            <div className="rounded-2xl border border-stone-200 bg-white p-4 text-sm leading-6 text-stone-600">
              {t("importDialog.accountJson.lastRead", { count: pendingAccountJsonImport.parsedAccountCount })}
              {pendingAccountJsonImport.errorCount > 0
                ? t("importDialog.accountJson.extraFailedSuffix", { count: pendingAccountJsonImport.errorCount })
                : ""}
              {t("importDialog.accountJson.periodSuffix")}
            </div>
          ) : null}
        </div>
      );
    }

    if (method === "codex-auth") {
      return (
        <div className="space-y-4">
          <button
            type="button"
            onClick={() => setMethod("menu")}
            className="inline-flex items-center gap-1 text-sm text-stone-500 transition hover:text-stone-800"
          >
            <ArrowLeft className="size-4" />
            {t("importDialog.back")}
          </button>
          <div className="space-y-2">
            <label className="text-sm font-medium text-stone-700">{t("importDialog.codexAuth.label")}</label>
            <Textarea
              placeholder={t("importDialog.codexAuth.placeholder")}
              value={codexAuthInput}
              onChange={(event) => setCodexAuthInput(event.target.value)}
              className="min-h-64 resize-none rounded-xl border-stone-200 font-mono text-xs"
            />
          </div>
        </div>
      );
    }

    return (
      <div className="space-y-3">
        <MethodCard
          title={t("importDialog.menu.oauth.title")}
          description={t("importDialog.menu.oauth.description")}
          icon={LogIn}
          onClick={() => setMethod("oauth")}
        />
        <MethodCard
          title={t("importDialog.title.token")}
          description={t("importDialog.menu.token.description")}
          icon={KeyRound}
          onClick={() => setMethod("token")}
        />
        <MethodCard
          title={t("importDialog.title.session")}
          description={t("importDialog.menu.session.description")}
          icon={FileJson}
          onClick={() => setMethod("session")}
        />
        <MethodCard
          title={t("importDialog.title.codexAuth")}
          description={t("importDialog.menu.codexAuth.description")}
          icon={FileJson}
          onClick={() => setMethod("codex-auth")}
        />
        <MethodCard
          title={t("importDialog.menu.accountJson.title")}
          description={t("importDialog.menu.accountJson.description")}
          icon={Files}
          onClick={() => setMethod("account-json")}
        />
        <MethodCard
          title={t("importDialog.menu.cpaImport.title")}
          description={t("importDialog.menu.cpaImport.description")}
          icon={Files}
          onClick={() => {
            setOpen(false);
            resetState();
            router.push("/settings");
          }}
        />
        <MethodCard
          title={t("importDialog.menu.sub2apiImport.title")}
          description={t("importDialog.menu.sub2apiImport.description")}
          icon={ServerCog}
          onClick={() => {
            setOpen(false);
            resetState();
            router.push("/settings");
          }}
        />
      </div>
    );
  };

  const footerDisabled = disabled || isSubmitting;

  return (
    <>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <Button
          className="h-10 rounded-xl bg-stone-950 px-4 text-white hover:bg-stone-800"
          onClick={() => setOpen(true)}
          disabled={disabled}
        >
          <Upload className="size-4" />
          {t("importDialog.triggerButton")}
        </Button>
        <DialogContent showCloseButton={false} className="rounded-2xl p-6">
          <DialogHeader className="gap-2">
            <DialogTitle>
              {method === "menu"
                ? t("importDialog.title.menu")
                : method === "token"
                  ? t("importDialog.title.token")
                  : method === "session"
                    ? t("importDialog.title.session")
                    : method === "codex-auth"
                      ? t("importDialog.title.codexAuth")
                    : method === "oauth"
                      ? t("importDialog.title.oauthDialog")
                      : t("importDialog.title.accountJsonDialog")}
            </DialogTitle>
            <DialogDescription className="text-sm leading-6">
              {method === "menu"
                ? t("importDialog.description.menu")
                : method === "token"
                  ? t("importDialog.description.token")
                  : method === "session"
                    ? t("importDialog.description.session")
                    : method === "codex-auth"
                      ? t("importDialog.description.codexAuth")
                    : method === "oauth"
                      ? t("importDialog.description.oauth")
                      : t("importDialog.description.accountJson")}
            </DialogDescription>
          </DialogHeader>

          {renderMethodBody()}

          <DialogFooter className="pt-2">
            <Button
              variant="secondary"
              className="h-10 rounded-xl bg-stone-100 px-5 text-stone-700 hover:bg-stone-200"
              onClick={() => setOpen(false)}
              disabled={footerDisabled}
            >
              {tCommon("canvasDialog.cancel")}
            </Button>
            {method === "token" ? (
              <Button
                className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
                onClick={() => void handleImportTokenText()}
                disabled={footerDisabled}
              >
                {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
                {t("importDialog.footer.importTokenButton")}
              </Button>
            ) : null}
            {method === "session" ? (
              <Button
                className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
                onClick={() => void handleImportSessionJson()}
                disabled={footerDisabled}
              >
                {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
                {t("importDialog.footer.importJsonButton")}
              </Button>
            ) : null}
            {method === "codex-auth" ? (
              <Button
                className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
                onClick={() => void handleImportCodexAuthJson()}
                disabled={footerDisabled}
              >
                {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
                {t("importDialog.footer.importJsonButton")}
              </Button>
            ) : null}
            {method === "oauth" ? (
              <Button
                className={cn(
                  "h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800",
                  !oauthSession ? "hidden" : "",
                )}
                onClick={() => void handleFinishOAuth()}
                disabled={footerDisabled || !oauthSession || !oauthCallbackInput.trim()}
              >
                {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
                {t("importDialog.footer.finishImportButton")}
              </Button>
            ) : null}
            {method === "account-json" ? (
              <Button
                className={cn(
                  "h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800",
                  !pendingAccountJsonImport ? "hidden" : "",
                )}
                onClick={() => setConfirmOpen(true)}
                disabled={footerDisabled || !pendingAccountJsonImport}
              >
                {t("importDialog.footer.viewConfirmButton")}
              </Button>
            ) : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="rounded-2xl p-6">
          <DialogHeader className="gap-2">
            <DialogTitle>{t("importDialog.accountJson.confirmTitle")}</DialogTitle>
            <DialogDescription className="text-sm leading-6">
              {pendingAccountJsonImport
                ? t("importDialog.accountJson.confirmReady", { count: pendingAccountJsonImport.parsedAccountCount })
                : t("importDialog.accountJson.confirmEmpty")}
              {pendingAccountJsonImport?.errorCount
                ? t("importDialog.accountJson.extraFailedSuffixPeriod", { count: pendingAccountJsonImport.errorCount })
                : t("importDialog.accountJson.periodSuffix")}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="pt-2">
            <Button
              variant="secondary"
              className="h-10 rounded-xl bg-stone-100 px-5 text-stone-700 hover:bg-stone-200"
              onClick={() => setConfirmOpen(false)}
              disabled={isSubmitting}
            >
              {t("importDialog.accountJson.backButton")}
            </Button>
            <Button
              className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
              onClick={() =>
                void submitTokens(
                  pendingAccountJsonImport?.tokens ?? [],
                  t("importDialog.toasts.accountJsonImportComplete"),
                  pendingAccountJsonImport?.accounts ?? [],
                )
              }
              disabled={isSubmitting || !pendingAccountJsonImport}
            >
              {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
              {t("importDialog.accountJson.confirmButton")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
