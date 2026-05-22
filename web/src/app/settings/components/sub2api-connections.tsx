"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Eye,
  EyeOff,
  Import,
  Layers,
  Link2,
  LoaderCircle,
  Mail,
  Pencil,
  Plus,
  RefreshCcw,
  Save,
  Search,
  ServerCog,
  Trash2,
  Unplug,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  createSub2APIServer,
  deleteSub2APIServer,
  fetchSub2APIServerAccounts,
  fetchSub2APIServerGroups,
  fetchSub2APIServers,
  startSub2APIImport,
  updateSub2APIServer,
  type Sub2APIRemoteAccount,
  type Sub2APIRemoteGroup,
  type Sub2APIServer,
} from "@/lib/api";

const PAGE_SIZE_OPTIONS = ["50", "100", "200"] as const;

type AuthMode = "password" | "api_key";

function normalizeAccounts(items: Sub2APIRemoteAccount[]) {
  const seen = new Set<string>();
  const accounts: Sub2APIRemoteAccount[] = [];
  for (const item of items) {
    const id = String(item.id || "").trim();
    if (!id || seen.has(id)) {
      continue;
    }
    seen.add(id);
    accounts.push({
      id,
      name: String(item.name || "").trim(),
      email: String(item.email || "").trim(),
      plan_type: String(item.plan_type || "").trim(),
      status: String(item.status || "").trim(),
      expires_at: String(item.expires_at || "").trim(),
      has_refresh_token: Boolean(item.has_refresh_token),
    });
  }
  return accounts;
}

export function Sub2APIConnections() {
  const didLoadRef = useRef(false);
  const pollTimerRef = useRef<number | null>(null);

  const [servers, setServers] = useState<Sub2APIServer[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingServer, setEditingServer] = useState<Sub2APIServer | null>(null);
  const [formName, setFormName] = useState("");
  const [formBaseUrl, setFormBaseUrl] = useState("");
  const [formEmail, setFormEmail] = useState("");
  const [formPassword, setFormPassword] = useState("");
  const [formApiKey, setFormApiKey] = useState("");
  const [formGroupId, setFormGroupId] = useState("");
  const [authMode, setAuthMode] = useState<AuthMode>("password");
  const [showSecret, setShowSecret] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const [remoteGroups, setRemoteGroups] = useState<Sub2APIRemoteGroup[] | null>(null);
  const [isLoadingGroups, setIsLoadingGroups] = useState(false);

  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [loadingAccountsId, setLoadingAccountsId] = useState<string | null>(null);

  const [browserOpen, setBrowserOpen] = useState(false);
  const [browserServer, setBrowserServer] = useState<Sub2APIServer | null>(null);
  const [remoteAccounts, setRemoteAccounts] = useState<Sub2APIRemoteAccount[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [accountQuery, setAccountQuery] = useState("");
  const [accountPage, setAccountPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZE_OPTIONS)[number]>("100");
  const [isStartingImport, setIsStartingImport] = useState(false);

  const loadServers = async () => {
    setIsLoading(true);
    try {
      const data = await fetchSub2APIServers();
      setServers(data.servers);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Tải kết nối Sub2API thất bại");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (didLoadRef.current) {
      return;
    }
    didLoadRef.current = true;
    void loadServers();
  }, []);

  useEffect(() => {
    const hasRunningJobs = servers.some(
      (server) => server.import_job?.status === "pending" || server.import_job?.status === "running",
    );
    if (!hasRunningJobs) {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      return;
    }

    pollTimerRef.current = window.setInterval(() => {
      void fetchSub2APIServers()
        .then((data) => {
          setServers(data.servers);
        })
        .catch((error) => {
          if (pollTimerRef.current !== null) {
            window.clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
          }
          toast.error(error instanceof Error ? error.message : "Không tìm được tiến độ nhập");
        });
    }, 1500);

    return () => {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [servers]);

  const openAddDialog = () => {
    setEditingServer(null);
    setFormName("");
    setFormBaseUrl("");
    setFormEmail("");
    setFormPassword("");
    setFormApiKey("");
    setFormGroupId("");
    setAuthMode("password");
    setShowSecret(false);
    setRemoteGroups(null);
    setDialogOpen(true);
  };

  const openEditDialog = (server: Sub2APIServer) => {
    setEditingServer(server);
    setFormName(server.name);
    setFormBaseUrl(server.base_url);
    setFormEmail(server.email);
    setFormPassword("");
    setFormApiKey("");
    setFormGroupId(server.group_id || "");
    setAuthMode(server.has_api_key ? "api_key" : "password");
    setShowSecret(false);
    setRemoteGroups(null);
    setDialogOpen(true);
  };

  const handleFetchGroups = async () => {
    if (!editingServer) {
      toast.error("请先Lưukết nốisau再lấynhóm");
      return;
    }
    setIsLoadingGroups(true);
    try {
      const data = await fetchSub2APIServerGroups(editingServer.id);
      setRemoteGroups(data.groups);
      if (data.groups.length === 0) {
        toast.message("Máy chủ từ xa không có cấu hình nhóm");
      } else {
        toast.success(`Đọc到 ${data.groups.length} 个nhóm`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "lấynhómthất bại");
    } finally {
      setIsLoadingGroups(false);
    }
  };

  const handleSave = async () => {
    if (!formBaseUrl.trim()) {
      toast.error("Vui lòng nhập địa chỉ Sub2API");
      return;
    }
    if (authMode === "password") {
      if (!formEmail.trim()) {
        toast.error("Vui lòng nhập email quản trị");
        return;
      }
      if (!editingServer && !formPassword.trim()) {
        toast.error("Vui lòng nhập mật khẩu quản trị");
        return;
      }
    } else if (!editingServer && !formApiKey.trim()) {
      toast.error("Vui lòng nhập Admin API Key");
      return;
    }

    setIsSaving(true);
    try {
      if (editingServer) {
        const updates: Parameters<typeof updateSub2APIServer>[1] = {
          name: formName.trim(),
          base_url: formBaseUrl.trim(),
          group_id: formGroupId.trim(),
        };
        if (authMode === "password") {
          updates.email = formEmail.trim();
          if (formPassword.trim()) {
            updates.password = formPassword.trim();
          }
          updates.api_key = "";
        } else {
          if (formApiKey.trim()) {
            updates.api_key = formApiKey.trim();
          }
          updates.email = "";
          updates.password = "";
        }
        const data = await updateSub2APIServer(editingServer.id, updates);
        setServers(data.servers);
        toast.success("Đã cập nhật kết nối");
      } else {
        const data = await createSub2APIServer({
          name: formName.trim(),
          base_url: formBaseUrl.trim(),
          email: authMode === "password" ? formEmail.trim() : "",
          password: authMode === "password" ? formPassword.trim() : "",
          api_key: authMode === "api_key" ? formApiKey.trim() : "",
          group_id: formGroupId.trim(),
        });
        setServers(data.servers);
        toast.success("Đã thêm kết nối");
      }
      setDialogOpen(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Lưuthất bại");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (server: Sub2APIServer) => {
    setDeletingId(server.id);
    try {
      const data = await deleteSub2APIServer(server.id);
      setServers(data.servers);
      toast.success("kết nốiĐã Xóa");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Xóathất bại");
    } finally {
      setDeletingId(null);
    }
  };

  const handleBrowseAccounts = async (server: Sub2APIServer) => {
    setLoadingAccountsId(server.id);
    try {
      const data = await fetchSub2APIServerAccounts(server.id);
      const accounts = normalizeAccounts(data.accounts);
      setBrowserServer(server);
      setRemoteAccounts(accounts);
      setSelectedIds([]);
      setAccountQuery("");
      setAccountPage(1);
      setBrowserOpen(true);
      toast.success(`Đã đọc, tổng cộng  ${accounts.length} tài khoản OpenAI`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Đọc tài khoản Sub2API thất bại");
    } finally {
      setLoadingAccountsId(null);
    }
  };

  const filteredAccounts = useMemo(() => {
    const query = accountQuery.trim().toLowerCase();
    if (!query) {
      return remoteAccounts;
    }
    return remoteAccounts.filter((item) => {
      return (
        item.email.toLowerCase().includes(query) ||
        item.name.toLowerCase().includes(query) ||
        item.plan_type.toLowerCase().includes(query) ||
        item.id.toLowerCase().includes(query)
      );
    });
  }, [accountQuery, remoteAccounts]);

  const currentPageSize = Number(pageSize);
  const accountPageCount = Math.max(1, Math.ceil(filteredAccounts.length / currentPageSize));
  const safeAccountPage = Math.min(accountPage, accountPageCount);
  const pagedAccounts = filteredAccounts.slice(
    (safeAccountPage - 1) * currentPageSize,
    safeAccountPage * currentPageSize,
  );
  const allFilteredSelected =
    filteredAccounts.length > 0 && filteredAccounts.every((item) => selectedIds.includes(item.id));

  const toggleAccount = (id: string, checked: boolean) => {
    setSelectedIds((prev) => {
      if (checked) {
        return Array.from(new Set([...prev, id]));
      }
      return prev.filter((item) => item !== id);
    });
  };

  const handleToggleSelectAllFiltered = (checked: boolean) => {
    if (checked) {
      setSelectedIds(Array.from(new Set([...selectedIds, ...filteredAccounts.map((item) => item.id)])));
      return;
    }
    const filteredSet = new Set(filteredAccounts.map((item) => item.id));
    setSelectedIds((prev) => prev.filter((id) => !filteredSet.has(id)));
  };

  const handleStartImport = async () => {
    if (!browserServer) {
      return;
    }
    if (selectedIds.length === 0) {
      toast.error("Vui lòng chọn tài khoản cần nhập");
      return;
    }

    setIsStartingImport(true);
    try {
      const result = await startSub2APIImport(browserServer.id, selectedIds);
      setServers((prev) =>
        prev.map((server) =>
          server.id === browserServer.id ? { ...server, import_job: result.import_job } : server,
        ),
      );
      setBrowserOpen(false);
      toast.success("Đã khởi chạy tác vụ nhập");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Không bắt đầu được nhập");
    } finally {
      setIsStartingImport(false);
    }
  };

  return (
    <>
      <Card className="rounded-2xl card-3d card-tint-violet">
        <CardContent className="space-y-6 p-6">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-xl bg-stone-100">
                <ServerCog className="size-5 text-stone-600" />
              </div>
              <div>
                <h2 className="text-lg font-semibold tracking-tight">Quản lý kết nối Sub2API</h2>
                <p className="text-sm text-stone-500">
                  Cấu hình máy chủ Sub2API, sau đó có thể tìm tài khoản OpenAI OAuth và nhập hàng loạt vào kho địa phương.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {servers.length > 0 ? <Badge className="rounded-md px-2.5 py-1">{servers.length} 个kết nối</Badge> : null}
              <Button
                className="h-9 rounded-xl bg-stone-900 px-4 text-white hover:bg-stone-800"
                onClick={openAddDialog}
              >
                <Plus className="size-4" />
                Thêm kết nối
              </Button>
            </div>
          </div>

          {isLoading ? (
            <div className="flex items-center justify-center py-10">
              <LoaderCircle className="size-5 animate-spin text-stone-500" />
            </div>
          ) : servers.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 rounded-xl bg-stone-100 px-6 py-10 text-center">
              <ServerCog className="size-8 text-stone-700" />
              <div className="space-y-1">
                <p className="text-sm font-medium text-stone-600">Chưa có kết nối Sub2API nào</p>
                <p className="text-sm text-stone-500">Nhấn "Thêm kết nối" để lưu thông tin Sub2API của bạn.</p>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {servers.map((server) => {
                const isBusy = deletingId === server.id || loadingAccountsId === server.id;
                const importJob = server.import_job ?? null;
                return (
                  <div
                    key={server.id}
                    className="flex flex-col gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-stone-800">{server.name || server.base_url}</div>
                        <div className="truncate text-xs text-stone-500">
                          {server.base_url}
                          {server.email ? ` · ${server.email}` : server.has_api_key ? " · API Key" : ""}
                          {server.group_id ? ` · nhóm ${server.group_id}` : " · 全部nhóm"}
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          className="rounded-lg p-2 text-stone-500 transition hover:bg-stone-200 hover:text-stone-700"
                          onClick={() => openEditDialog(server)}
                          disabled={isBusy}
                          title="Chỉnh sửa"
                        >
                          <Pencil className="size-4" />
                        </button>
                        <button
                          type="button"
                          className="rounded-lg p-2 text-stone-500 transition hover:bg-rose-50 hover:text-rose-500"
                          onClick={() => void handleDelete(server)}
                          disabled={isBusy}
                          title="Xóa"
                        >
                          {deletingId === server.id ? (
                            <LoaderCircle className="size-4 animate-spin" />
                          ) : (
                            <Trash2 className="size-4" />
                          )}
                        </button>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        className="h-8 rounded-lg border-stone-200 bg-white px-3 text-xs text-stone-600"
                        onClick={() => void handleBrowseAccounts(server)}
                        disabled={isBusy}
                      >
                        {loadingAccountsId === server.id ? (
                          <LoaderCircle className="size-3.5 animate-spin" />
                        ) : (
                          <Import className="size-3.5" />
                        )}
                        Đồng bộ
                      </Button>
                    </div>

                    {importJob ? (
                      <div className="space-y-2 rounded-xl bg-stone-100 px-3 py-3">
                        <div className="text-xs font-medium tracking-[0.16em] text-stone-500 uppercase">Tác vụ nhập</div>
                        {(() => {
                          const progress =
                            importJob.total > 0
                              ? Math.round((importJob.completed / importJob.total) * 100)
                              : 0;
                          return (
                            <div className="rounded-lg border border-stone-200 bg-white px-3 py-3">
                              <div className="flex items-center justify-between gap-3">
                                <div className="min-w-0">
                                  <div className="text-sm font-medium text-stone-700">
                                    Trạng thái {importJob.status}，Đã 处理 {importJob.completed}/{importJob.total}
                                  </div>
                                  <div className="truncate text-xs text-stone-500">
                                    Tác vụ {importJob.job_id.slice(0, 8)} · {importJob.created_at}
                                  </div>
                                </div>
                                <Badge
                                  variant={
                                    importJob.status === "completed"
                                      ? "success"
                                      : importJob.status === "failed"
                                        ? "danger"
                                        : "info"
                                  }
                                  className="rounded-md"
                                >
                                  {progress}%
                                </Badge>
                              </div>
                              <div className="mt-3 h-2 overflow-hidden rounded-full bg-stone-200">
                                <div
                                  className="h-full rounded-full bg-white transition-all"
                                  style={{ width: `${progress}%` }}
                                />
                              </div>
                              <div className="mt-2 flex flex-wrap gap-2 text-xs text-stone-500">
                                <span>Mới {importJob.added}</span>
                                <span>Bỏ qua {importJob.skipped}</span>
                                <span>Làm mới {importJob.refreshed}</span>
                                <span>thất bại {importJob.failed}</span>
                              </div>
                            </div>
                          );
                        })()}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}

          <div className="rounded-xl bg-stone-100 px-4 py-3 text-sm leading-6 text-stone-500">
            <p className="font-medium text-stone-600">Hướng dẫn sử dụng</p>
            <ul className="mt-1 list-inside list-disc space-y-0.5">
              <li>Nhập địa chỉ Sub2API và tài khoản quản trị (hoặc Admin API Key), lưu thành một kết nối.</li>
              <li>Nhấn "Đồng bộ" trên một kết nối sẽ lấy danh sách tài khoản có platform=openai và type=oauth.</li>
              <li>Chọn tài khoản cần, backend sẽ tải access_token và tự động nhập vào kho địa phương kèm trạng thái.</li>
              <li>Chỉ đọc access_token từ Sub2API; refresh_token và các trường khác không được lưu.</li>
            </ul>
          </div>
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent showCloseButton={false} className="rounded-2xl p-6">
          <DialogHeader className="gap-2">
            <DialogTitle>{editingServer ? "Chỉnh sửakết nối" : "Thêm kết nối"}</DialogTitle>
            <DialogDescription className="text-sm leading-6">
              {editingServer ? "sửa Sub2API kết nốithông tin" : "thêmmộtmới Sub2API kết nối"}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-stone-700">Tên（tùy chọn）</label>
              <Input
                value={formName}
                onChange={(event) => setFormName(event.target.value)}
                placeholder="例如：自建 sub2api"
                className="h-11 rounded-xl border-stone-200 bg-white"
              />
            </div>
            <div className="space-y-2">
              <label className="flex items-center gap-1.5 text-sm font-medium text-stone-700">
                <Link2 className="size-3.5" />
                Địa chỉ Sub2API
              </label>
              <Input
                value={formBaseUrl}
                onChange={(event) => setFormBaseUrl(event.target.value)}
                placeholder="http://your-sub2api-host:8080"
                className="h-11 rounded-xl border-stone-200 bg-white"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-stone-700">Phương thức xác thực</label>
              <Select value={authMode} onValueChange={(value) => setAuthMode(value as AuthMode)}>
                <SelectTrigger className="h-11 rounded-xl border-stone-200 bg-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="password">Email quản trị + mật khẩu</SelectItem>
                  <SelectItem value="api_key">Admin API Key</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {authMode === "password" ? (
              <>
                <div className="space-y-2">
                  <label className="flex items-center gap-1.5 text-sm font-medium text-stone-700">
                    <Mail className="size-3.5" />
                    Email quản trị
                  </label>
                  <Input
                    value={formEmail}
                    onChange={(event) => setFormEmail(event.target.value)}
                    placeholder="admin@example.com"
                    className="h-11 rounded-xl border-stone-200 bg-white"
                  />
                </div>
                <div className="space-y-2">
                  <label className="flex items-center gap-1.5 text-sm font-medium text-stone-700">
                    <Unplug className="size-3.5" />
                    Mật khẩu quản trị
                  </label>
                  <div className="relative">
                    <Input
                      type={showSecret ? "text" : "password"}
                      value={formPassword}
                      onChange={(event) => setFormPassword(event.target.value)}
                      placeholder={editingServer ? "留空则不sửamật khẩu" : "Mật khẩu quản trị"}
                      className="h-11 rounded-xl border-stone-200 bg-white pr-10"
                    />
                    <button
                      type="button"
                      className="absolute top-1/2 right-3 -translate-y-1/2 text-stone-500 transition hover:text-stone-600"
                      onClick={() => setShowSecret((prev) => !prev)}
                    >
                      {showSecret ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="space-y-2">
                <label className="flex items-center gap-1.5 text-sm font-medium text-stone-700">
                  <Unplug className="size-3.5" />
                  Admin API Key
                </label>
                <div className="relative">
                  <Input
                    type={showSecret ? "text" : "password"}
                    value={formApiKey}
                    onChange={(event) => setFormApiKey(event.target.value)}
                    placeholder={editingServer ? "Để trống nếu không sửa khóa" : "Sub2API Admin API Key"}
                    className="h-11 rounded-xl border-stone-200 bg-white pr-10"
                  />
                  <button
                    type="button"
                    className="absolute top-1/2 right-3 -translate-y-1/2 text-stone-500 transition hover:text-stone-600"
                    onClick={() => setShowSecret((prev) => !prev)}
                  >
                    {showSecret ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
              </div>
            )}
            <div className="space-y-2">
              <label className="flex items-center gap-1.5 text-sm font-medium text-stone-700">
                <Layers className="size-3.5" />
                nhóm（tùy chọn）
              </label>
              {remoteGroups && remoteGroups.length > 0 ? (
                <Select value={formGroupId || "__all__"} onValueChange={(value) => setFormGroupId(value === "__all__" ? "" : value)}>
                  <SelectTrigger className="h-11 rounded-xl border-stone-200 bg-white">
                    <SelectValue placeholder="Chọn nhóm" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all__">全部nhóm（不限制）</SelectItem>
                    <SelectItem value="ungrouped">未nhóm</SelectItem>
                    {remoteGroups.map((group) => (
                      <SelectItem key={group.id} value={group.id}>
                        {group.name || `Group ${group.id}`}
                        {group.platform ? `（${group.platform}）` : ""}
                        {group.account_count
                          ? ` · ${group.active_account_count}/${group.account_count}`
                          : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  value={formGroupId}
                  onChange={(event) => setFormGroupId(event.target.value)}
                  placeholder="留空则Đồng bộ所有nhóm；或填写nhóm ID / ungrouped"
                  className="h-11 rounded-xl border-stone-200 bg-white"
                />
              )}
              {editingServer ? (
                <div className="flex items-center justify-between gap-2 text-xs text-stone-500">
                  <span>Khi đồng bộ sẽ lọc theo ID nhóm, để trống = đồng bộ tất cả tài khoản OpenAI OAuth.</span>
                  <Button
                    variant="outline"
                    className="h-8 rounded-lg border-stone-200 bg-white px-2 text-xs text-stone-600"
                    onClick={() => void handleFetchGroups()}
                    disabled={isLoadingGroups}
                  >
                    {isLoadingGroups ? (
                      <LoaderCircle className="size-3.5 animate-spin" />
                    ) : (
                      <RefreshCcw className="size-3.5" />
                    )}
                    {remoteGroups ? "重新lấy" : "lấynhóm"}
                  </Button>
                </div>
              ) : (
                <div className="text-xs text-stone-500">
                  thêm完kết nốisaucó thểtrongChỉnh sửahộp thoạinàynhấn「lấynhóm」chọncụ thểnhóm。
                </div>
              )}
            </div>
          </div>
          <DialogFooter className="pt-2">
            <Button
              variant="secondary"
              className="h-10 rounded-xl bg-stone-100 px-5 text-stone-700 hover:bg-stone-200"
              onClick={() => setDialogOpen(false)}
              disabled={isSaving}
            >
              Hủy
            </Button>
            <Button
              className="h-10 rounded-xl bg-stone-900 px-5 text-white hover:bg-stone-800"
              onClick={() => void handleSave()}
              disabled={isSaving}
            >
              {isSaving ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
              {editingServer ? "Lưusửa" : "thêm"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={browserOpen} onOpenChange={setBrowserOpen}>
        <DialogContent showCloseButton={false} className="max-h-[90vh] max-w-5xl rounded-2xl p-6">
          <DialogHeader className="gap-2">
            <DialogTitle>Chọn tài khoản cần nhập</DialogTitle>
            <DialogDescription className="text-sm leading-6">
              {browserServer ? `来自 ${browserServer.name || browserServer.base_url}` : "Tài khoản OpenAI OAuth trên Sub2API"}
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="relative min-w-[260px]">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-stone-500" />
              <Input
                value={accountQuery}
                onChange={(event) => {
                  setAccountQuery(event.target.value);
                  setAccountPage(1);
                }}
                placeholder="搜索邮箱、套餐或Tên"
                className="h-10 rounded-xl border-stone-200 bg-white pl-10"
              />
            </div>
            <div className="flex items-center gap-2">
              <Select
                value={pageSize}
                onValueChange={(value) => {
                  setPageSize(value as (typeof PAGE_SIZE_OPTIONS)[number]);
                  setAccountPage(1);
                }}
              >
                <SelectTrigger className="h-10 w-[120px] rounded-xl border-stone-200 bg-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PAGE_SIZE_OPTIONS.map((item) => (
                    <SelectItem key={item} value={item}>
                      {item} / 页
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                className="h-10 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                onClick={() => handleToggleSelectAllFiltered(!allFilteredSelected)}
              >
                {allFilteredSelected ? "Bỏ chọn tất cả" : "Chọn tất cả kết quả lọc"}
              </Button>
            </div>
          </div>

          <div className="rounded-xl border border-stone-200">
            <div className="flex items-center justify-between border-b border-stone-200 px-4 py-3 text-sm text-stone-500">
              <div className="flex items-center gap-3">
                <Checkbox
                  checked={allFilteredSelected}
                  onCheckedChange={(checked) => handleToggleSelectAllFiltered(Boolean(checked))}
                />
                <span>Kết quả lọc {filteredAccounts.length} 个</span>
              </div>
              <span>Đã chọn {selectedIds.length} 个</span>
            </div>
            <div className="max-h-[420px] overflow-auto">
              {pagedAccounts.length === 0 ? (
                <div className="flex items-center justify-center py-12 text-sm text-stone-500">Không có tài khoản phù hợp</div>
              ) : (
                <div className="divide-y divide-stone-100">
                  {pagedAccounts.map((item) => (
                    <label
                      key={item.id}
                      className="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-stone-800"
                    >
                      <Checkbox
                        checked={selectedIds.includes(item.id)}
                        onCheckedChange={(checked) => toggleAccount(item.id, Boolean(checked))}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-sm font-medium text-stone-700">
                            {item.email || item.name || item.id}
                          </span>
                          {item.plan_type ? (
                            <Badge className="rounded-md bg-stone-100 text-stone-600">{item.plan_type}</Badge>
                          ) : null}
                          {item.status ? (
                            <Badge
                              variant={item.status === "active" ? "success" : "info"}
                              className="rounded-md"
                            >
                              {item.status}
                            </Badge>
                          ) : null}
                        </div>
                        <div className="truncate text-xs text-stone-500">
                          id {item.id}
                          {item.expires_at ? ` · 过期 ${item.expires_at}` : ""}
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between text-sm text-stone-500">
            <span>
              第 {filteredAccounts.length === 0 ? 0 : (safeAccountPage - 1) * currentPageSize + 1} -{" "}
              {Math.min(safeAccountPage * currentPageSize, filteredAccounts.length)} 条，共 {filteredAccounts.length} 条
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                className="h-9 rounded-xl border-stone-200 bg-white px-3"
                onClick={() => setAccountPage((prev) => Math.max(1, prev - 1))}
                disabled={safeAccountPage <= 1}
              >
                Trang trước
              </Button>
              <span>
                {safeAccountPage}/{accountPageCount}
              </span>
              <Button
                variant="outline"
                className="h-9 rounded-xl border-stone-200 bg-white px-3"
                onClick={() => setAccountPage((prev) => Math.min(accountPageCount, prev + 1))}
                disabled={safeAccountPage >= accountPageCount}
              >
                Trang sau
              </Button>
            </div>
          </div>

          <DialogFooter className="pt-2">
            <Button
              variant="secondary"
              className="h-10 rounded-xl bg-stone-100 px-5 text-stone-700 hover:bg-stone-200"
              onClick={() => setBrowserOpen(false)}
              disabled={isStartingImport}
            >
              Hủy
            </Button>
            <Button
              className="h-10 rounded-xl bg-stone-900 px-5 text-white hover:bg-stone-800"
              onClick={() => void handleStartImport()}
              disabled={isStartingImport || selectedIds.length === 0}
            >
              {isStartingImport ? <LoaderCircle className="size-4 animate-spin" /> : <Import className="size-4" />}
              Nhập tài khoản đã chọn
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}


