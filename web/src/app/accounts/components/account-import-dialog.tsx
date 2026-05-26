"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ChangeEvent } from "react";
import {
  ArrowLeft,
  ExternalLink,
  FileJson,
  FileText,
  Files,
  KeyRound,
  LoaderCircle,
  ServerCog,
  Upload,
} from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { request } from "@/lib/request";
import { createAccounts, createOAuthAccounts, type Account } from "@/lib/api";
import { cn } from "@/lib/utils";

type ImportMethod =
  | "menu"
  | "token"
  | "session"
  | "cpa"
  | "oauth"
  | "oauth_flow"
  | "antigravity_flow"
  | "multi_tap"
  | "multi_auth";

type AccountImportDialogProps = {
  disabled?: boolean;
  onImported: (items: Account[]) => void;
};

type PendingCpaImport = {
  tokens: string[];
  parsedFileCount: number;
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

function getCpaAccessToken(value: unknown) {
  const token = (value as { access_token?: unknown })?.access_token;
  return typeof token === "string" ? token.trim() : "";
}

function readFileAsText(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => reject(reader.error ?? new Error(`Đọc tệp thất bại: ${file.name}`));
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
      className="w-full rounded-2xl border border-stone-200 bg-white p-0 text-left transition hover:border-stone-300 hover:bg-stone-800"
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
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [method, setMethod] = useState<ImportMethod>("menu");
  const [tokenInput, setTokenInput] = useState("");
  const [sessionInput, setSessionInput] = useState("");
  const [oauthRedirectUrl, setOauthRedirectUrl] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [pendingCpaImport, setPendingCpaImport] = useState<PendingCpaImport | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  // Multi-onboard state (shared between multi_tap and multi_auth)
  const [multiDraft, setMultiDraft] = useState({ email: "", password: "", code: "" });
  const [multiRunning, setMultiRunning] = useState(false);
  const [multiStage, setMultiStage] = useState<string>("");
  const [multiNeedCode, setMultiNeedCode] = useState(false);
  const [multiResults, setMultiResults] = useState<Record<string, any>>({});
  const [csCfg, setCsCfg] = useState<{ url: string; apiKey: string }>({
    url: "http://172.16.10.38:8010",
    apiKey: "AnhNhi@0610",
  });
  const multiPollRef = useRef<number | null>(null);

  // Pick up the captcha-solver URL + API key from providers.flow (the
  // existing onboard cards already store them there). Falls back to
  // the deployment default if Settings hasn't been initialized yet.
  useEffect(() => {
    void (async () => {
      try {
        const data = await request.get("/api/settings");
        const flow = ((data.data as any)?.config?.providers || {}).flow || {};
        if (flow.captcha_solver_url || flow.captcha_solver_api_key) {
          setCsCfg({
            url: flow.captcha_solver_url || "http://172.16.10.38:8010",
            apiKey: flow.captcha_solver_api_key || "AnhNhi@0610",
          });
        }
      } catch {/* keep defaults */}
    })();
    return () => {
      if (multiPollRef.current) window.clearInterval(multiPollRef.current);
    };
  }, []);

  const txtInputRef = useRef<HTMLInputElement | null>(null);
  const cpaInputRef = useRef<HTMLInputElement | null>(null);

  const resetState = () => {
    setMethod("menu");
    setTokenInput("");
    setSessionInput("");
    setPendingCpaImport(null);
    setConfirmOpen(false);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) {
      resetState();
    }
  };

  const submitTokens = async (tokens: string[], successText?: string) => {
    const normalizedTokens = tokens.map((item) => item.trim()).filter(Boolean);

    if (normalizedTokens.length === 0) {
      toast.error("Vui lòng cung cấp ít nhất một Token khả dụng");
      return;
    }

    setIsSubmitting(true);
    try {
      const data = await createAccounts(normalizedTokens);
      onImported(data.items);
      setOpen(false);
      resetState();

      if ((data.errors?.length ?? 0) > 0) {
        const firstError = data.errors?.[0]?.error;
        toast.error(
          `${successText ?? "Nhập hoàn tất"}, Thêm mới ${data.added ?? 0} mục, Đã làm mới ${data.refreshed ?? 0} mục, Thất bại ${data.errors?.length ?? 0} mục${firstError ? `, Lỗi đầu tiên: ${firstError}` : ""}`,
        );
      } else {
        toast.success(
          `${successText ?? "Nhập hoàn tất"}, Thêm mới ${data.added ?? 0} mục, Bỏ qua ${data.skipped ?? 0} mục trùng lặp, Đã tự động làm mới thông tin tài khoản`,
        );
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Nhập tài khoản thất bại";
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleImportTokenText = async () => {
    await submitTokens(splitTokens(tokenInput), "Nhập Access Token hoàn tất");
  };

  const handleTxtSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) {
      return;
    }

    try {
      const content = await readFileAsText(file);
      const tokens = splitTokens(content);

      if (tokens.length === 0) {
        toast.error("Không tìm thấy Token hợp lệ trong tệp TXT");
        return;
      }

      setTokenInput((prev) => {
        const next = [...splitTokens(prev), ...tokens];
        return next.join("\n");
      });
      toast.success(`Đã đọc ${tokens.length} Token từ ${file.name}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Đọc tệp TXT thất bại";
      toast.error(message);
    }
  };

  const handleImportSessionJson = async () => {
    if (!sessionInput.trim()) {
      toast.error("Vui lòng dán Session JSON đầy đủ");
      return;
    }

    try {
      const payload = JSON.parse(sessionInput) as unknown;
      const token = getSessionAccessToken(payload);

      if (!token) {
        toast.error("Không trích xuất được accessToken từ Session JSON");
        return;
      }

      await submitTokens([token], "Nhập Session JSON hoàn tất");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Phân tích Session JSON thất bại";
      toast.error(message);
    }
  };

  const handleImportOAuth = async () => {
    const oauthTokens = splitTokens(tokenInput);
    if (oauthTokens.length === 0) {
      toast.error("Vui lòng nhập ít nhất một OAuth Token");
      return;
    }

    setIsSubmitting(true);
    try {
      const data = await createOAuthAccounts(oauthTokens, "codex");
      onImported(data.items);
      setOpen(false);
      resetState();
      toast.success(`Đã thêm ${data.added ?? 0} tài khoản Codex OAuth, bỏ qua ${data.skipped ?? 0} trùng lặp`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Nhập OAuth thất bại";
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCpaSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";

    if (files.length === 0) {
      return;
    }

    try {
      const results = await Promise.all(
        files.map(async (file) => {
          const raw = await readFileAsText(file);
          const parsed = JSON.parse(raw) as unknown;
          const token = getCpaAccessToken(parsed);
          return {
            token,
          };
        }),
      );

      const tokens = results.map((item) => item.token).filter((item): item is string => Boolean(item));
      const parsedFileCount = tokens.length;
      const errorCount = results.length - parsedFileCount;

      if (parsedFileCount === 0) {
        toast.error("Không tìm thấy access_token hợp lệ trong các tệp CPA JSON này");
        return;
      }

      setPendingCpaImport({
        tokens,
        parsedFileCount,
        errorCount,
      });
      setConfirmOpen(true);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Đọc tệp CPA JSON thất bại";
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
              Quay lại
            </button>
            <span className="text-xs text-stone-500">Đã nhận diện {tokenCount} Token</span>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-stone-700">Danh sách Access Token</label>
            <Textarea
              placeholder="Mỗi dòng một Access Token..."
              value={tokenInput}
              onChange={(event) => setTokenInput(event.target.value)}
              className="min-h-56 resize-none rounded-xl border-stone-200"
            />
          </div>
          <div className="rounded-2xl border border-dashed border-stone-200 bg-stone-100 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="space-y-1">
                <div className="text-sm font-medium text-stone-800">Nhập từ tệp TXT</div>
                <div className="text-sm leading-6 text-stone-500">Hỗ trợ tệp `.txt`, nội dung tệp mỗi dòng một Token.</div>
              </div>
              <Button
                type="button"
                variant="outline"
                className="rounded-xl border-stone-200 bg-white"
                onClick={() => txtInputRef.current?.click()}
                disabled={isSubmitting}
              >
                <FileText className="size-4" />
                Chọn TXT
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

    if (method === "oauth") {
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
              Quay lại
            </button>
            <span className="text-xs text-stone-500">Đã nhận diện {tokenCount} Token OAuth</span>
          </div>
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
            <div className="font-medium">Token OAuth từ 9router</div>
            <div>
              Dán Codex OAuth token từ backup 9router. Các token này gọi thẳng OpenAI API (api.openai.com) — không giới hạn 24KB, không cần browser impersonation.
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-stone-700">OAuth Token (Codex)</label>
            <Textarea
              placeholder="Mỗi dòng một OAuth Token (JWT: eyJ...)..."
              value={tokenInput}
              onChange={(event) => setTokenInput(event.target.value)}
              className="min-h-56 resize-none rounded-xl border-stone-200 font-mono text-xs"
            />
          </div>
          <div className="rounded-2xl border border-dashed border-stone-200 bg-stone-100 p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="space-y-1">
                <div className="text-sm font-medium text-stone-800">Nhập từ tệp TXT</div>
                <div className="text-sm leading-6 text-stone-500">Hỗ trợ tệp `.txt`, mỗi dòng một Token.</div>
              </div>
              <Button
                type="button"
                variant="outline"
                className="rounded-xl border-stone-200 bg-white"
                onClick={() => txtInputRef.current?.click()}
                disabled={isSubmitting}
              >
                <FileText className="size-4" />
                Chọn TXT
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
            Quay lại
          </button>
          <div className="rounded-2xl border border-stone-200 bg-stone-100 p-4 text-sm leading-6 text-stone-600">
            Mở
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
            , sao chép toàn bộ JSON trả về từ trang web, hệ thống sẽ tự động trích xuất `accessToken` để nhập.
          </div>
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
            <div className="font-medium">Cảnh báo rủi ro</div>
            <div>
              Đừng sử dụng tài khoản chính, hãy cố gắng sử dụng tài khoản phụ để nhập nhằm tránh rủi ro bị khóa tài khoản. Dự án này không chịu trách nhiệm cho bất kỳ rủi ro khóa tài khoản nào.
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium text-stone-700">Session JSON</label>
            <Textarea
              placeholder='Dán toàn bộ JSON, ví dụ đối tượng chứa "accessToken"...'
              value={sessionInput}
              onChange={(event) => setSessionInput(event.target.value)}
              className="min-h-56 resize-none rounded-xl border-stone-200 font-mono text-xs"
            />
          </div>
        </div>
      );
    }

    if (method === "cpa") {
      return (
        <div className="space-y-4">
          <button
            type="button"
            onClick={() => setMethod("menu")}
            className="inline-flex items-center gap-1 text-sm text-stone-500 transition hover:text-stone-800"
          >
            <ArrowLeft className="size-4" />
            Quay lại
          </button>
          <div className="rounded-2xl border border-dashed border-stone-200 bg-stone-100 p-5">
            <div className="space-y-2">
              <div className="text-sm font-medium text-stone-800">Chọn nhiều tệp CPA JSON từ máy tính</div>
              <div className="text-sm leading-6 text-stone-500">
                Mỗi tệp phải là một đối tượng JSON. Hệ thống sẽ tự động trích xuất `access_token` hoặc `accessToken` từ đối tượng.
              </div>
            </div>
            <Button
              type="button"
              className="mt-4 rounded-xl bg-stone-900 text-white hover:bg-stone-800"
              onClick={() => cpaInputRef.current?.click()}
              disabled={isSubmitting}
            >
              <Files className="size-4" />
              Chọn nhiều tệp JSON
            </Button>
          </div>
          <input
            ref={cpaInputRef}
            type="file"
            accept=".json,application/json"
            multiple
            className="hidden"
            onChange={(event) => void handleCpaSelected(event)}
          />
          {pendingCpaImport ? (
            <div className="rounded-2xl border border-stone-200 bg-white p-4 text-sm leading-6 text-stone-600">
              Lần đọc gần nhất tìm thấy {pendingCpaImport.parsedFileCount} Token
              {pendingCpaImport.errorCount > 0 ? `，ngoài ra có ${pendingCpaImport.errorCount} tệp không trích xuất thành công` : ""}。
            </div>
          ) : null}
        </div>
      );
    }

    if (method === "oauth_flow") {
      return (
        <div className="space-y-4">
          <button type="button" onClick={() => setMethod("menu")}
            className="inline-flex items-center gap-1 text-sm text-stone-500 transition hover:text-stone-800">
            <ArrowLeft className="size-4" /> Quay lại
          </button>

          <div className="rounded-2xl border border-stone-200 bg-stone-100 p-4">
            <div className="mb-2 text-sm font-medium">Bước 1: Đăng nhập OpenAI</div>
            <p className="text-sm text-stone-600 mb-3">Nhấn nút để mở trang đăng nhập OpenAI. Sau khi đăng nhập, trình duyệt sẽ chuyển hướng đến localhost (có thể báo lỗi "không thể kết nối").</p>
            <Button variant="outline" className="bg-white"
              onClick={async () => {
                try {
                  const { request: req } = await import("@/lib/request");
                  const data = await req.get("/api/oauth/codex/start");
                  const url = (data.data as any)?.auth_url;
                  if (url) window.open(url, "_blank", "width=600,height=700");
                  else toast.error("Không thể tạo URL OAuth");
                } catch (e) { toast.error("Lỗi tạo OAuth URL"); }
              }}>
              Mở trang Đăng nhập OpenAI
            </Button>
          </div>

          <div className="rounded-2xl border border-stone-200 bg-stone-100 p-4">
            <div className="mb-2 text-sm font-medium">Bước 2: Dán URL callback</div>
            <p className="text-sm text-stone-600 mb-3">Sau khi đăng nhập, copy TOÀN Bộ URL trên thanh địa chỉ (bắt đầu bằng http://localhost:3030...) và dán vào đây:</p>
            <Textarea
              placeholder="http://localhost:3030/auth/callback?code=..."
              value={oauthRedirectUrl}
              onChange={(e) => setOauthRedirectUrl(e.target.value)}
              className="min-h-24 resize-none rounded-xl border-stone-300 font-mono text-xs mb-3"
            />
            <Button className="w-full bg-stone-900 text-white hover:bg-stone-800"
              disabled={!oauthRedirectUrl || isSubmitting}
              onClick={async () => {
                setIsSubmitting(true);
                try {
                  const { request: req } = await import("@/lib/request");
                  await req.post("/api/oauth/codex/exchange", { redirect_url: oauthRedirectUrl });
                  toast.success("Đăng nhập thành công! Token đã được thêm.");
                  setOpen(false);
                  resetState();
                  onImported([]);
                } catch (error) {
                  toast.error(error instanceof Error ? error.message : "Xác thực thất bại");
                } finally { setIsSubmitting(false); }
              }}>
              {isSubmitting ? <LoaderCircle className="mr-2 size-4 animate-spin" /> : null}
              Xác nhận và Lưu Token
            </Button>
          </div>
        </div>
      );
    }

    if (method === "multi_tap" || method === "multi_auth") {
      const preferMethod: "tap" | "auth" = method === "multi_auth" ? "auth" : "tap";
      const isAuth = preferMethod === "auth";
      const profileFor = (email: string) => {
        const local = (email.split("@")[0] || "default").replace(/[^a-z0-9-]/gi, "-");
        return `google-${local}`;
      };
      const stopMultiPoll = () => {
        if (multiPollRef.current) {
          window.clearInterval(multiPollRef.current);
          multiPollRef.current = null;
        }
      };
      const startMultiOnboard = async () => {
        if (!multiDraft.email.trim() || !multiDraft.password) {
          toast.error("Cần email + mật khẩu Google");
          return;
        }
        const profile = profileFor(multiDraft.email);
        stopMultiPoll();
        setMultiRunning(true);
        setMultiStage("starting");
        setMultiResults({});
        setMultiNeedCode(false);
        try {
          const res = await fetch(`${csCfg.url}/v1/multi-onboard`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${csCfg.apiKey}`, "Content-Type": "application/json" },
            body: JSON.stringify({
              profile,
              email: multiDraft.email.trim(),
              password: multiDraft.password,
              prefer_method: preferMethod,
              services: ["gemini_web", "flow", "chatgpt"],
            }),
          });
          if (!res.ok) throw new Error(`multi-onboard HTTP ${res.status}`);
        } catch (e: any) {
          toast.error(`Onboard error: ${e?.message || e}`);
          setMultiRunning(false);
          return;
        }
        // Poll the multi-onboard status. When the embedded Google session
        // reports state=need_code, light the code input. When stage=done,
        // collect tokens and push them into the chatgpt2api accounts pool.
        const handleDone = async (state: any) => {
          stopMultiPoll();
          const results = state.results || {};
          setMultiResults(results);
          const chatgptToken = results.chatgpt?.token;
          let added = 0;
          if (chatgptToken) {
            try {
              await request.post("/api/accounts", { tokens: [chatgptToken] });
              added += 1;
            } catch (e) {
              // best-effort
            }
          }
          // Update gemini_web + chatgpt_web + flow with this profile so
          // it appears in the Settings list.
          try {
            const cur = (await request.get("/api/settings")).data as any;
            const providers = (cur?.config?.providers || {}) as Record<string, any>;
            const ensureProfile = (key: string) => {
              const cfg = providers[key] || {};
              const accounts = Array.isArray(cfg.accounts) ? cfg.accounts.slice() : [];
              if (!accounts.some((a: any) => a?.profile === profile)) {
                accounts.push({ profile, label: multiDraft.email });
              }
              providers[key] = { ...cfg, enabled: true, accounts };
            };
            if (results.gemini_web?.state === "success") ensureProfile("gemini_web");
            if (results.flow?.state === "success") ensureProfile("flow");
            if (results.chatgpt?.state === "success") ensureProfile("chatgpt_web");
            await request.post("/api/settings", { providers });
          } catch (e) {
            console.error("merge providers config failed", e);
          }
          toast.success(`Multi onboard xong — ChatGPT pool +${added}, các service đã ghi vào Settings`);
          setMultiRunning(false);
          setMultiDraft({ email: "", password: "", code: "" });
          setOpen(false);
          resetState();
          onImported([]);
        };
        multiPollRef.current = window.setInterval(async () => {
          try {
            const r = await fetch(
              `${csCfg.url}/v1/multi-onboard/${encodeURIComponent(profile)}/status`,
              { headers: { "Authorization": `Bearer ${csCfg.apiKey}` } },
            );
            if (!r.ok) return;
            const data = await r.json();
            setMultiStage(data.stage || "");
            const gState = data.google?.state || "";
            if (isAuth && gState === "need_code") setMultiNeedCode(true);
            else if (gState !== "need_code") setMultiNeedCode(false);
            if (data.stage === "done") void handleDone(data);
            if (data.stage === "failed") {
              stopMultiPoll();
              setMultiRunning(false);
              toast.error(`Multi onboard fail: ${data.error || ""}`);
            }
          } catch {/* ignore poll errors */}
        }, 1500) as unknown as number;
      };
      const submitCode = async () => {
        if (multiDraft.code.length < 4) return;
        const profile = profileFor(multiDraft.email);
        try {
          await fetch(
            `${csCfg.url}/v1/session/${encodeURIComponent(profile)}/auto-login-2fa-code`,
            {
              method: "POST",
              headers: { "Authorization": `Bearer ${csCfg.apiKey}`, "Content-Type": "application/json" },
              body: JSON.stringify({ code: multiDraft.code }),
            },
          );
          setMultiNeedCode(false);
          setMultiDraft({ ...multiDraft, code: "" });
        } catch (e: any) {
          toast.error(`Submit code fail: ${e?.message || e}`);
        }
      };
      return (
        <div className="space-y-4">
          <button type="button" onClick={() => { stopMultiPoll(); setMethod("menu"); }}
            className="inline-flex items-center gap-1 text-sm text-stone-500 transition hover:text-stone-800">
            <ArrowLeft className="size-4" /> Quay lại
          </button>

          <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4 text-sm text-stone-600">
            <p className="mb-1 font-medium text-stone-900">
              {isAuth
                ? "1-click đăng nhập Google + onboard ChatGPT/Gemini Web/Flow. Xác thực 2FA bằng mã 6 số từ Google Authenticator."
                : "1-click đăng nhập Google + onboard ChatGPT/Gemini Web/Flow. Xác thực 2FA bằng cách bấm 'Có' trên điện thoại đã đăng nhập sẵn."}
            </p>
            <p className="text-xs text-stone-500">
              Profile sẽ tạo dưới tên <code>google-&lt;localpart-of-email&gt;</code>.
              Sau khi xong: ChatGPT JWT → pool, Gemini Web + ChatGPT Web + Flow → Settings.
            </p>
          </div>

          <div className="grid gap-3">
            <Input
              type="email"
              placeholder="email Google"
              value={multiDraft.email}
              onChange={(e) => setMultiDraft({ ...multiDraft, email: e.target.value })}
              disabled={multiRunning}
            />
            <Input
              type="password"
              placeholder="mật khẩu Google"
              value={multiDraft.password}
              onChange={(e) => setMultiDraft({ ...multiDraft, password: e.target.value })}
              disabled={multiRunning}
            />
            {isAuth && (
              <div className={cn(
                "rounded-xl border-2 p-3 transition",
                multiNeedCode
                  ? "border-amber-400 bg-amber-50 shadow-[0_0_0_4px_rgba(251,191,36,0.2)] animate-pulse"
                  : "border-stone-200 bg-white",
              )}>
                <div className="mb-2 text-xs font-semibold text-stone-700">
                  {multiNeedCode
                    ? "⚡ Hệ thống đang cần mã Authenticator — nhập ngay (mã đổi mỗi 30s)"
                    : "Mã Google Authenticator (sẽ sáng đèn khi cần)"}
                </div>
                <div className="flex gap-2">
                  <Input
                    inputMode="numeric"
                    maxLength={8}
                    placeholder="123456"
                    value={multiDraft.code}
                    onChange={(e) => setMultiDraft({ ...multiDraft, code: e.target.value.replace(/[^0-9]/g, "") })}
                    disabled={!multiNeedCode}
                    className="font-mono tracking-widest"
                  />
                  <Button
                    onClick={submitCode}
                    disabled={!multiNeedCode || multiDraft.code.length < 4}
                    className="bg-stone-900 text-white hover:bg-stone-800"
                  >
                    Gửi mã
                  </Button>
                </div>
              </div>
            )}
          </div>

          {multiRunning && (
            <div className="rounded-xl bg-stone-100 p-3 text-sm text-stone-700">
              <LoaderCircle className="mr-2 inline size-4 animate-spin" />
              Đang chạy — stage: <span className="font-mono">{multiStage}</span>
              {Object.keys(multiResults).length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-xs">
                  {Object.entries(multiResults).map(([svc, r]: [string, any]) => (
                    <li key={svc}>
                      {svc}: {r?.state || "?"}
                      {r?.error ? ` — ${r.error}` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              onClick={() => { stopMultiPoll(); setMethod("menu"); }}
              disabled={multiRunning}
            >
              Đóng
            </Button>
            <Button
              onClick={startMultiOnboard}
              disabled={multiRunning || !multiDraft.email || !multiDraft.password}
              className="bg-stone-900 text-white hover:bg-stone-800"
            >
              {multiRunning ? <LoaderCircle className="mr-2 size-4 animate-spin" /> : null}
              {isAuth ? "Bắt đầu (Auth)" : "Bắt đầu (thiết bị)"}
            </Button>
          </div>
        </div>
      );
    }

    if (method === "antigravity_flow") {
      return (
        <div className="space-y-4">
          <button type="button" onClick={() => setMethod("menu")}
            className="inline-flex items-center gap-1 text-sm text-stone-500 transition hover:text-stone-800">
            <ArrowLeft className="size-4" /> Quay lại
          </button>

          <div className="rounded-2xl border border-stone-200 bg-stone-100 p-4">
            <div className="mb-2 text-sm font-medium">Bước 1: Đăng nhập Google (Antigravity)</div>
            <p className="text-sm text-stone-600 mb-3">Nhấn nút bên dưới để mở trang đăng nhập tài khoản Google. Sau khi đăng nhập và cấp quyền, trình duyệt của bạn sẽ chuyển hướng đến localhost (có thể báo lỗi "không thể kết nối" hoặc "không tìm thấy trang"). Hãy copy TOÀN BỘ URL trên thanh địa chỉ đó.</p>
            <Button variant="outline" className="bg-white"
              onClick={async () => {
                try {
                  const { request: req } = await import("@/lib/request");
                  const data = await req.get("/api/oauth/antigravity/start");
                  const url = (data.data as any)?.auth_url;
                  if (url) window.open(url, "_blank", "width=600,height=700");
                  else toast.error("Không thể tạo URL OAuth");
                } catch (e) { toast.error("Lỗi tạo OAuth URL"); }
              }}>
              Mở trang Đăng nhập Google
            </Button>
          </div>

          <div className="rounded-2xl border border-stone-200 bg-stone-100 p-4">
            <div className="mb-2 text-sm font-medium">Bước 2: Dán URL callback</div>
            <p className="text-sm text-stone-600 mb-3">Dán toàn bộ URL đã copy ở Bước 1 vào ô dưới đây (có dạng http://localhost:8080/callback?code=...):</p>
            <Textarea
              placeholder="http://localhost:8080/callback?code=..."
              value={oauthRedirectUrl}
              onChange={(e) => setOauthRedirectUrl(e.target.value)}
              className="min-h-24 resize-none rounded-xl border-stone-300 font-mono text-xs mb-3"
            />
            <Button className="w-full bg-stone-900 text-white hover:bg-stone-800"
              disabled={!oauthRedirectUrl || isSubmitting}
              onClick={async () => {
                setIsSubmitting(true);
                try {
                  const { request: req } = await import("@/lib/request");
                  await req.post("/api/oauth/antigravity/exchange", { redirect_url: oauthRedirectUrl });
                  toast.success("Đăng nhập thành công! Tài khoản Antigravity đã được thêm vào pool.");
                  setOpen(false);
                  resetState();
                  onImported([]);
                } catch (error) {
                  toast.error(error instanceof Error ? error.message : "Xác thực thất bại");
                } finally { setIsSubmitting(false); }
              }}>
              {isSubmitting ? <LoaderCircle className="mr-2 size-4 animate-spin" /> : null}
              Xác nhận và Lưu Token
            </Button>
          </div>
        </div>
      );
    }

    return (
      <div className="space-y-3">
        <MethodCard
          title="Nhập Access Token"
          description="Hỗ trợ dán trực tiếp hoặc đọc từ tệp TXT, mỗi dòng một Token."
          icon={KeyRound}
          onClick={() => setMethod("token")}
        />
        <MethodCard
          title="Nhập Session JSON"
          description="Sao chép toàn bộ JSON từ API session của chatgpt.com, tự động trích xuất accessToken."
          icon={FileJson}
          onClick={() => setMethod("session")}
        />
        <MethodCard
          title="Nhập tệp CPA JSON"
          description="Hỗ trợ chọn nhiều tệp JSON cùng lúc, tự động đọc access_token từ từng tệp."
          icon={Files}
          onClick={() => setMethod("cpa")}
        />
        <MethodCard
          title="Nhập từ máy chủ CPA từ xa"
          description="Vào trang cài đặt để cấu hình máy chủ CPA từ xa trước khi thực hiện nhập."
          icon={Files}
          onClick={() => {
            setOpen(false);
            resetState();
            router.push("/settings");
          }}
        />
        <MethodCard
          title="Nhập OAuth Token (9router)"
          description="Dán Codex OAuth token từ backup 9router. Gọi thẳng OpenAI API — không giới hạn 24KB."
          icon={KeyRound}
          onClick={() => setMethod("oauth")}
        />
        <MethodCard
          title="Đăng nhập Codex OAuth"
          description="Đăng nhập bằng tài khoản OpenAI để lấy token OAuth (hỗ trợ Docker/Server)."
          icon={KeyRound}
          onClick={() => setMethod("oauth_flow")}
        />
        <MethodCard
          title="Đăng nhập Antigravity (Google)"
          description="Đăng nhập bằng tài khoản Google để lấy token Antigravity (hỗ trợ Docker/Server)."
          icon={KeyRound}
          onClick={() => setMethod("antigravity_flow")}
        />
        <MethodCard
          title="Multi qua thiết bị"
          description="1-click Google login + onboard ChatGPT + Gemini Web + Flow. Xác thực 2FA bằng cách bấm 'Có' trên điện thoại đã đăng nhập."
          icon={KeyRound}
          onClick={() => setMethod("multi_tap")}
        />
        <MethodCard
          title="Multi qua Auth"
          description="Tương tự nhưng dùng mã 6 số từ Google Authenticator. Khi cần mã, ô nhập sẽ sáng đèn."
          icon={KeyRound}
          onClick={() => setMethod("multi_auth")}
        />
        <MethodCard
          title="Lấy token tạo ảnh"
          description="Mở chatgpt.com — đăng nhập → copy JSON → paste vào mục Session JSON ở trên."
          icon={KeyRound}
          onClick={() => window.open("https://chatgpt.com/api/auth/session", "_blank")}
        />
        <MethodCard
          title="Nhập từ máy chủ Sub2API"
          description="Vào trang cài đặt để cấu hình máy chủ Sub2API, sau đó chọn tài khoản OpenAI để nhập."
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
          className="h-10 rounded-xl bg-stone-900 px-4 text-white hover:bg-stone-800"
          onClick={() => setOpen(true)}
          disabled={disabled}
        >
          <Upload className="size-4" />
          Nhập tài khoản
        </Button>
        <DialogContent showCloseButton={false} className="rounded-2xl p-6 max-h-[85vh] overflow-y-auto">
          <DialogHeader className="gap-2">
            <DialogTitle>
              {method === "menu"
                ? "Nhập tài khoản"
                : method === "token"
                  ? "Nhập Access Token"
                  : method === "session"
                    ? "Nhập Session JSON"
                    : method === "antigravity_flow"
                      ? "Đăng nhập Antigravity (Google)"
                      : "Nhập CPA JSON"}
            </DialogTitle>
            <DialogDescription className="text-sm leading-6">
              {method === "menu"
                ? "Chọn một phương thức nhập. Sau khi nhập thành công, hệ thống sẽ tự động lấy thông tin email, loại và hạn mức."
                : method === "token"
                  ? "Hỗ trợ dán thủ công hoặc nhập từ tệp TXT, mỗi dòng một Token."
                  : method === "session"
                    ? "Dán toàn bộ Session JSON, hệ thống sẽ tự động trích xuất accessToken."
                    : method === "antigravity_flow"
                      ? "Đăng nhập bằng tài khoản Google để lấy token Antigravity."
                      : "Hỗ trợ đọc nhiều tệp JSON cùng lúc và xác nhận số lượng trước khi gửi."}
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
              Hủy
            </Button>
            {method === "token" ? (
              <Button
                className="h-10 rounded-xl bg-stone-900 px-5 text-white hover:bg-stone-800"
                onClick={() => void handleImportTokenText()}
                disabled={footerDisabled}
              >
                {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
                Nhập Token
              </Button>
            ) : null}
            {method === "session" ? (
              <Button
                className="h-10 rounded-xl bg-stone-900 px-5 text-white hover:bg-stone-800"
                onClick={() => void handleImportSessionJson()}
                disabled={footerDisabled}
              >
                {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
                Nhập JSON
              </Button>
            ) : null}
            {method === "cpa" ? (
              <Button
                className={cn(
                  "h-10 rounded-xl bg-stone-900 px-5 text-white hover:bg-stone-800",
                  !pendingCpaImport ? "hidden" : "",
                )}
                onClick={() => setConfirmOpen(true)}
                disabled={footerDisabled || !pendingCpaImport}
              >
                Xem xác nhận nhập
              </Button>
            ) : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="rounded-2xl p-6">
          <DialogHeader className="gap-2">
            <DialogTitle>Xác nhận nhập CPA Token</DialogTitle>
            <DialogDescription className="text-sm leading-6">
              {pendingCpaImport
                ? `Xác nhận đã nhận diện ${pendingCpaImport.parsedFileCount} Token, bạn có chắc chắn muốn nhập?`
                : "Chưa đọc được Token nào khả dụng để nhập."}
              {pendingCpaImport?.errorCount
                ? `，ngoài ra có ${pendingCpaImport.errorCount} tệp không trích xuất thành công.`
                : "."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="pt-2">
            <Button
              variant="secondary"
              className="h-10 rounded-xl bg-stone-100 px-5 text-stone-700 hover:bg-stone-200"
              onClick={() => setConfirmOpen(false)}
              disabled={isSubmitting}
            >
              Quay lại
            </Button>
            <Button
              className="h-10 rounded-xl bg-stone-900 px-5 text-white hover:bg-stone-800"
              onClick={() => void submitTokens(pendingCpaImport?.tokens ?? [], "Nhập CPA JSON hoàn tất")}
              disabled={isSubmitting || !pendingCpaImport}
            >
              {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
              Xác nhận nhập
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
