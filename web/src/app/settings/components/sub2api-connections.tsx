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
      toast.error(error instanceof Error ? error.message : "Failed to load Sub2API connections");
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
          toast.error(error instanceof Error ? error.message : "Failed to query import progress");
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
      toast.error("Please save the connection first before fetching groups");
      return;
    }
    setIsLoadingGroups(true);
    try {
      const data = await fetchSub2APIServerGroups(editingServer.id);
      setRemoteGroups(data.groups);
      if (data.groups.length === 0) {
        toast.message("No groups configured on remote");
      } else {
        toast.success(`Fetched ${data.groups.length} groups`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to fetch groups");
    } finally {
      setIsLoadingGroups(false);
    }
  };

  const handleSave = async () => {
    if (!formBaseUrl.trim()) {
      toast.error("Please enter Sub2API address");
      return;
    }
    if (authMode === "password") {
      if (!formEmail.trim()) {
        toast.error("Please enter admin email");
        return;
      }
      if (!editingServer && !formPassword.trim()) {
        toast.error("Please enter admin password");
        return;
      }
    } else if (!editingServer && !formApiKey.trim()) {
      toast.error("Please enter Admin API Key");
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
        toast.success("Connection updated");
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
        toast.success("Connection added");
      }
      setDialogOpen(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Save failed");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (server: Sub2APIServer) => {
    setDeletingId(server.id);
    try {
      const data = await deleteSub2APIServer(server.id);
      setServers(data.servers);
      toast.success("Connection deleted");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Delete failed");
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
      toast.success(`Fetched ${accounts.length} OpenAI accounts`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to fetch Sub2API accounts");
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
      toast.error("Please select accounts to import first");
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
      toast.success("Import task started");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to start import");
    } finally {
      setIsStartingImport(false);
    }
  };

  return (
    <>
      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="space-y-6 p-6">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-xl bg-stone-100">
                <ServerCog className="size-5 text-stone-600" />
              </div>
              <div>
                <h2 className="text-lg font-semibold tracking-tight">Sub2API Connection Management</h2>
                <p className="text-sm text-stone-500">
                  After configuring Sub2API servers, you can query OpenAI OAuth accounts and batch import to local pool.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {servers.length > 0 ? <Badge className="rounded-md px-2.5 py-1">{servers.length} connections</Badge> : null}
              <Button
                className="h-9 rounded-xl bg-stone-950 px-4 text-white hover:bg-stone-800"
                onClick={openAddDialog}
              >
                <Plus className="size-4" />
                Add Connection
              </Button>
            </div>
          </div>

          {isLoading ? (
            <div className="flex items-center justify-center py-10">
              <LoaderCircle className="size-5 animate-spin text-stone-400" />
            </div>
          ) : servers.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 rounded-xl bg-stone-50 px-6 py-10 text-center">
              <ServerCog className="size-8 text-stone-300" />
              <div className="space-y-1">
                <p className="text-sm font-medium text-stone-600">No Sub2API connections yet</p>
                <p className="text-sm text-stone-400">Click "Add Connection" to save your Sub2API info.</p>
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
                        <div className="truncate text-xs text-stone-400">
                          {server.base_url}
                          {server.email ? ` · ${server.email}` : server.has_api_key ? " · API Key" : ""}
                          {server.group_id ? ` · Group ${server.group_id}` : " · All Groups"}
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          className="rounded-lg p-2 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
                          onClick={() => openEditDialog(server)}
                          disabled={isBusy}
                          title="Edit"
                        >
                          <Pencil className="size-4" />
                        </button>
                        <button
                          type="button"
                          className="rounded-lg p-2 text-stone-400 transition hover:bg-rose-50 hover:text-rose-500"
                          onClick={() => void handleDelete(server)}
                          disabled={isBusy}
                          title="Delete"
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
                        Sync
                      </Button>
                    </div>

                    {importJob ? (
                      <div className="space-y-2 rounded-xl bg-stone-50 px-3 py-3">
                        <div className="text-xs font-medium tracking-[0.16em] text-stone-400 uppercase">Import Job</div>
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
                                    Status {importJob.status}, processed {importJob.completed}/{importJob.total}
                                  </div>
                                  <div className="truncate text-xs text-stone-400">
                                    Job {importJob.job_id.slice(0, 8)} · {importJob.created_at}
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
                                  className="h-full rounded-full bg-stone-900 transition-all"
                                  style={{ width: `${progress}%` }}
                                />
                              </div>
                              <div className="mt-2 flex flex-wrap gap-2 text-xs text-stone-500">
                                <span>Added {importJob.added}</span>
                                <span>Skipped {importJob.skipped}</span>
                                <span>Refreshed {importJob.refreshed}</span>
                                <span>Failed {importJob.failed}</span>
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

          <div className="rounded-xl bg-stone-50 px-4 py-3 text-sm leading-6 text-stone-500">
            <p className="font-medium text-stone-600">Usage Instructions</p>
            <ul className="mt-1 list-inside list-disc space-y-0.5">
              <li>Enter Sub2API address and admin account (or Admin API Key), save as a connection.</li>
              <li>Click "Sync" on a connection to fetch accounts where platform=openai and type=oauth.</li>
              <li>After selecting accounts, the backend concurrently fetches access_tokens and automatically imports to local pool and refreshes status.</li>
              <li>Only reads access_token from sub2api credentials; refresh_token and other fields will not be written locally.</li>
            </ul>
          </div>
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent showCloseButton={false} className="rounded-2xl p-6">
          <DialogHeader className="gap-2">
            <DialogTitle>{editingServer ? "Edit Connection" : "Add Connection"}</DialogTitle>
            <DialogDescription className="text-sm leading-6">
              {editingServer ? "Modify Sub2API connection info" : "Add a new Sub2API connection"}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-stone-700">Name (optional)</label>
              <Input
                value={formName}
                onChange={(event) => setFormName(event.target.value)}
                placeholder="e.g., Self-hosted sub2api"
                className="h-11 rounded-xl border-stone-200 bg-white"
              />
            </div>
            <div className="space-y-2">
              <label className="flex items-center gap-1.5 text-sm font-medium text-stone-700">
                <Link2 className="size-3.5" />
                Sub2API Address
              </label>
              <Input
                value={formBaseUrl}
                onChange={(event) => setFormBaseUrl(event.target.value)}
                placeholder="http://your-sub2api-host:8080"
                className="h-11 rounded-xl border-stone-200 bg-white"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-stone-700">Auth Method</label>
              <Select value={authMode} onValueChange={(value) => setAuthMode(value as AuthMode)}>
                <SelectTrigger className="h-11 rounded-xl border-stone-200 bg-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="password">Admin Email + Password</SelectItem>
                  <SelectItem value="api_key">Admin API Key</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {authMode === "password" ? (
              <>
                <div className="space-y-2">
                  <label className="flex items-center gap-1.5 text-sm font-medium text-stone-700">
                    <Mail className="size-3.5" />
                    Admin Email
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
                    Admin Password
                  </label>
                  <div className="relative">
                    <Input
                      type={showSecret ? "text" : "password"}
                      value={formPassword}
                      onChange={(event) => setFormPassword(event.target.value)}
                      placeholder={editingServer ? "Leave empty to keep password" : "Admin password"}
                      className="h-11 rounded-xl border-stone-200 bg-white pr-10"
                    />
                    <button
                      type="button"
                      className="absolute top-1/2 right-3 -translate-y-1/2 text-stone-400 transition hover:text-stone-600"
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
                    placeholder={editingServer ? "Leave empty to keep key" : "Sub2API Admin API Key"}
                    className="h-11 rounded-xl border-stone-200 bg-white pr-10"
                  />
                  <button
                    type="button"
                    className="absolute top-1/2 right-3 -translate-y-1/2 text-stone-400 transition hover:text-stone-600"
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
                Group (optional)
              </label>
              {remoteGroups && remoteGroups.length > 0 ? (
                <Select value={formGroupId || "__all__"} onValueChange={(value) => setFormGroupId(value === "__all__" ? "" : value)}>
                  <SelectTrigger className="h-11 rounded-xl border-stone-200 bg-white">
                    <SelectValue placeholder="Select group" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all__">All Groups (no restriction)</SelectItem>
                    <SelectItem value="ungrouped">Ungrouped</SelectItem>
                    {remoteGroups.map((group) => (
                      <SelectItem key={group.id} value={group.id}>
                        {group.name || `Group ${group.id}`}
                        {group.platform ? ` (${group.platform})` : ""}
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
                  placeholder="Leave empty to sync all groups; or fill group ID / ungrouped"
                  className="h-11 rounded-xl border-stone-200 bg-white"
                />
              )}
              {editingServer ? (
                <div className="flex items-center justify-between gap-2 text-xs text-stone-500">
                  <span>Sync will filter by group ID, empty = sync all OpenAI OAuth accounts.</span>
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
                    {remoteGroups ? "Refetch Groups" : "Fetch Groups"}
                  </Button>
                </div>
              ) : (
                <div className="text-xs text-stone-500">
                  After adding the connection, you can click "Fetch Groups" in the edit dialog to select a specific group.
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
              Cancel
            </Button>
            <Button
              className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
              onClick={() => void handleSave()}
              disabled={isSaving}
            >
              {isSaving ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
              {editingServer ? "Save Changes" : "Add"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={browserOpen} onOpenChange={setBrowserOpen}>
        <DialogContent showCloseButton={false} className="max-h-[90vh] max-w-5xl rounded-2xl p-6">
          <DialogHeader className="gap-2">
            <DialogTitle>Select accounts to import</DialogTitle>
            <DialogDescription className="text-sm leading-6">
              {browserServer ? `From ${browserServer.name || browserServer.base_url}` : "OpenAI OAuth accounts on Sub2API"}
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="relative min-w-[260px]">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-stone-400" />
              <Input
                value={accountQuery}
                onChange={(event) => {
                  setAccountQuery(event.target.value);
                  setAccountPage(1);
                }}
                placeholder="Search email, plan or name"
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
                      {item} / page
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                className="h-10 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                onClick={() => handleToggleSelectAllFiltered(!allFilteredSelected)}
              >
                {allFilteredSelected ? "Deselect All" : "Select All Filtered"}
              </Button>
            </div>
          </div>

          <div className="rounded-xl border border-stone-200">
            <div className="flex items-center justify-between border-b border-stone-100 px-4 py-3 text-sm text-stone-500">
              <div className="flex items-center gap-3">
                <Checkbox
                  checked={allFilteredSelected}
                  onCheckedChange={(checked) => handleToggleSelectAllFiltered(Boolean(checked))}
                />
                <span>{filteredAccounts.length} filtered results</span>
              </div>
              <span>{selectedIds.length} selected</span>
            </div>
            <div className="max-h-[420px] overflow-auto">
              {pagedAccounts.length === 0 ? (
                <div className="flex items-center justify-center py-12 text-sm text-stone-400">No matching accounts</div>
              ) : (
                <div className="divide-y divide-stone-100">
                  {pagedAccounts.map((item) => (
                    <label
                      key={item.id}
                      className="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-stone-50"
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
                        <div className="truncate text-xs text-stone-400">
                          id {item.id}
                          {item.expires_at ? ` · Expires ${item.expires_at}` : ""}
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
              {(safeAccountPage - 1) * currentPageSize + 1} - {Math.min(safeAccountPage * currentPageSize, filteredAccounts.length)} of {filteredAccounts.length}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                className="h-9 rounded-xl border-stone-200 bg-white px-3"
                onClick={() => setAccountPage((prev) => Math.max(1, prev - 1))}
                disabled={safeAccountPage <= 1}
              >
                Previous
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
                Next
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
              Cancel
            </Button>
            <Button
              className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
              onClick={() => void handleStartImport()}
              disabled={isStartingImport || selectedIds.length === 0}
            >
              {isStartingImport ? <LoaderCircle className="size-4 animate-spin" /> : <Import className="size-4" />}
              Import Selected Accounts
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
