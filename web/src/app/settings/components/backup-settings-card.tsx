"use client";

import { CloudUpload, Download, Eye, LoaderCircle, Play, RefreshCcw, Shield, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import webConfig from "@/constants/common-env";
import { fetchBackupDetail, getBackupDownloadUrl, type BackupDetail, type BackupInclude } from "@/lib/api";
import { getStoredAuthKey } from "@/store/auth";
import { useSettingsStore } from "../store";

function formatDateTime(value?: string | null) {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size >= 10 || index === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`;
}

function getFilenameFromContentDisposition(value: string | null) {
  const header = String(value || "").trim();
  if (!header) {
    return "";
  }
  const utf8Match = header.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }
  const plainMatch = header.match(/filename\s*=\s*"?([^";]+)"?/i);
  return plainMatch?.[1] || "";
}

const includeLabels: Array<{ key: keyof BackupInclude; label: string }> = [
  { key: "config", label: "Cấu hình hệ thống" },
  { key: "register", label: "Cấu hình đăng ký" },
  { key: "cpa", label: "Cấu hình CPA" },
  { key: "sub2api", label: "Cấu hình Sub2API" },
  { key: "logs", label: "Nhật ký điều phối và cuộc gọi" },
  { key: "image_tasks", label: "Nhật ký tác vụ hình ảnh" },
  { key: "accounts_snapshot", label: "Bản chụp tài khoản" },
  { key: "auth_keys_snapshot", label: "Bản chụp mã khóa người dùng" },
  { key: "images", label: "Thư mục tệp hình ảnh" },
];

export function BackupSettingsCard() {
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<BackupDetail | null>(null);
  const config = useSettingsStore((state) => state.config);
  const backups = useSettingsStore((state) => state.backups);
  const backupState = useSettingsStore((state) => state.backupState);
  const isLoadingConfig = useSettingsStore((state) => state.isLoadingConfig);
  const isSavingConfig = useSettingsStore((state) => state.isSavingConfig);
  const isLoadingBackups = useSettingsStore((state) => state.isLoadingBackups);
  const isRunningBackup = useSettingsStore((state) => state.isRunningBackup);
  const deletingBackupKey = useSettingsStore((state) => state.deletingBackupKey);
  const isTestingBackup = useSettingsStore((state) => state.isTestingBackup);
  const saveConfig = useSettingsStore((state) => state.saveConfig);
  const loadBackups = useSettingsStore((state) => state.loadBackups);
  const runBackup = useSettingsStore((state) => state.runBackup);
  const removeBackup = useSettingsStore((state) => state.removeBackup);
  const testBackup = useSettingsStore((state) => state.testBackup);
  const setBackupField = useSettingsStore((state) => state.setBackupField);
  const setBackupInclude = useSettingsStore((state) => state.setBackupInclude);

  if (isLoadingConfig) {
    return (
      <Card className="rounded-2xl card-3d card-tint-amber">
        <CardContent className="flex items-center justify-center p-10">
          <LoaderCircle className="size-5 animate-spin text-stone-500" />
        </CardContent>
      </Card>
    );
  }

  const backup = config?.backup;
  if (!backup) {
    return null;
  }

  const handleOpenDetail = async (key: string) => {
    setDetailLoading(true);
    setDetailOpen(true);
    try {
      const data = await fetchBackupDetail(key);
      setDetail(data.item);
    } catch (error) {
      setDetail(null);
      toast.error(error instanceof Error ? error.message : "Đọc chi tiết sao lưu thất bại");
    } finally {
      setDetailLoading(false);
    }
  };

  const handleDownload = async (key: string, name: string) => {
    try {
      const authKey = await getStoredAuthKey();
      if (!authKey) {
        toast.error("Trạng thái đăng nhập hiện tại đã hết hạn, vui lòng đăng nhập lại trước khi tải xuống");
        return;
      }
      const response = await fetch(`${webConfig.apiUrl.replace(/\/$/, "")}${getBackupDownloadUrl(key)}`, {
        headers: {
          Authorization: `Bearer ${authKey}`,
        },
      });
      if (!response.ok) {
        let message = "Tải xuống bản sao lưu thất bại";
        try {
          const data = await response.json() as { detail?: { error?: string }; error?: string; message?: string };
          message = data.detail?.error || data.error || data.message || message;
        } catch {
          message = response.status === 401 ? "Đăng nhập đã hết hạn, vui lòng đăng nhập lại và thử lại" : message;
        }
        throw new Error(message);
      }
      const downloadName = getFilenameFromContentDisposition(response.headers.get("Content-Disposition")) || name || "backup.bin";
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = downloadName;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Quá trình tải xuống bản sao lưu đã bắt đầu");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Tải xuống bản sao lưu thất bại");
    }
  };

  return (
    <>
      <Card className="rounded-2xl card-3d card-tint-amber">
        <CardContent className="space-y-6 p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-xl bg-stone-100">
                <CloudUpload className="size-5 text-stone-600" />
              </div>
              <div>
                <h2 className="text-lg font-semibold tracking-tight">Quản lý sao lưu R2</h2>
                <p className="text-sm text-stone-500">Định kỳ sao lưu dữ liệu quan trọng lên Cloudflare R2, hỗ trợ mã hóa tùy chọn, xoay vòng, thực thi thủ công và dọn dẹp lịch sử.</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={backupState?.running ? "warning" : backupState?.last_status === "success" ? "success" : "secondary"} className="rounded-md">
                {backupState?.running ? "Đang sao lưu" : backupState?.last_status === "success" ? "Thành công gần đây" : backupState?.last_status === "error" ? "Thất bại gần đây" : "Chưa thực hiện"}
              </Badge>
            </div>
          </div>

          <div className="rounded-xl border border-stone-200 bg-stone-100 px-4 py-3 text-sm leading-6 text-stone-600">
            Tài khoản và mã khóa người dùng sẽ xuất bản chụp logic từ backend lưu trữ hiện tại, không phụ thuộc vào lớp dưới cùng là `json`, `sqlite`, `postgres` hay `git`. Thư mục hình ảnh không được sao lưu theo mặc định để tránh kích thước bản sao lưu quá lớn.
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700">
              <Checkbox
                checked={Boolean(backup.enabled)}
                onCheckedChange={(checked) => setBackupField("enabled", Boolean(checked))}
              />
              Bật sao lưu định kỳ
            </label>
            <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700">
              <Checkbox
                checked={Boolean(backup.encrypt)}
                onCheckedChange={(checked) => setBackupField("encrypt", Boolean(checked))}
              />
              Bật mã hóa sao lưu
            </label>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">Cloudflare Account ID</label>
            <Input value={String(backup.account_id || "")} onChange={(event) => setBackupField("account_id", event.target.value)} className="h-10 rounded-xl border-stone-200 bg-white" />
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">R2 Endpoint (S3 API)</label>
            <Input value={String(backup.endpoint || "")} onChange={(event) => setBackupField("endpoint", event.target.value)} placeholder="https://{id}.r2.cloudflarestorage.com" className="h-10 rounded-xl border-stone-200 bg-white" />
            <p className="text-xs text-stone-500">Lấy từ R2 bucket → Settings → S3 API. Dùng cho cả backup và RAG online.</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">Tên Bucket</label>
            <Input value={String(backup.bucket || "")} onChange={(event) => setBackupField("bucket", event.target.value)} className="h-10 rounded-xl border-stone-200 bg-white" />
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">Access Key ID</label>
            <Input value={String(backup.access_key_id || "")} onChange={(event) => setBackupField("access_key_id", event.target.value)} className="h-10 rounded-xl border-stone-200 bg-white" />
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">Secret Access Key</label>
            <Input type="password" value={String(backup.secret_access_key || "")} onChange={(event) => setBackupField("secret_access_key", event.target.value)} className="h-10 rounded-xl border-stone-200 bg-white" />
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">Tiền tố sao lưu</label>
            <Input value={String(backup.prefix || "")} onChange={(event) => setBackupField("prefix", event.target.value)} placeholder="backups" className="h-10 rounded-xl border-stone-200 bg-white" />
            <p className="text-xs text-stone-500">Tiền tố đối tượng trong R2, ví dụ `backups/prod`.</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">Khoảng thời gian sao lưu định kỳ</label>
            <Input value={String(backup.interval_minutes || "")} onChange={(event) => setBackupField("interval_minutes", event.target.value)} placeholder="360" className="h-10 rounded-xl border-stone-200 bg-white" />
            <p className="text-xs text-stone-500">Tính bằng phút, quá trình tự động thăm dò sẽ được thực hiện theo khoảng thời gian này sau khi dịch vụ khởi động.</p>
          </div>

          <div className="space-y-2">
            <label className="text-sm text-stone-700">Số lượng bản sao lưu giữ lại</label>
            <Input value={String(backup.rotation_keep || "")} onChange={(event) => setBackupField("rotation_keep", event.target.value)} placeholder="10" className="h-10 rounded-xl border-stone-200 bg-white" />
            <p className="text-xs text-stone-500">Tự động xóa các bản sao lưu cũ hơn sau khi tải lên thành công. Điền `0` để không tự động xoay vòng.</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">Mật khẩu mã hóa</label>
            <Input type="password" value={String(backup.passphrase || "")} onChange={(event) => setBackupField("passphrase", event.target.value)} placeholder={backup.encrypt ? "Bắt buộc nếu bật mã hóa" : "Để trống"} className="h-10 rounded-xl border-stone-200 bg-white" />
            <p className="text-xs text-stone-500">Chỉ được sử dụng khi bật mã hóa. Vui lòng giữ an toàn, nếu không sẽ không thể giải mã nội dung sao lưu.</p>
          </div>
          </div>

          <div className="space-y-3 rounded-xl border border-stone-200 bg-white px-4 py-4">
          <div>
            <div className="text-sm font-medium text-stone-800">Nội dung sao lưu</div>
            <p className="mt-1 text-xs text-stone-500">Chọn các thành phần cần đưa vào gói sao lưu.</p>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            {includeLabels.map((item) => (
              <label key={item.key} className="flex items-center gap-3 text-sm text-stone-700">
                <Checkbox
                  checked={Boolean(backup.include[item.key])}
                  onCheckedChange={(checked) => setBackupInclude(item.key, Boolean(checked))}
                />
                {item.label}
              </label>
            ))}
          </div>
          </div>

          <div className="grid gap-3 rounded-xl border border-stone-200 bg-stone-100 px-4 py-4 text-sm text-stone-600 md:grid-cols-3">
          <div>
            <div className="text-xs text-stone-500">Bắt đầu gần nhất</div>
            <div className="mt-1 font-medium text-stone-800">{formatDateTime(backupState?.last_started_at)}</div>
          </div>
          <div>
            <div className="text-xs text-stone-500">Hoàn thành gần nhất</div>
            <div className="mt-1 font-medium text-stone-800">{formatDateTime(backupState?.last_finished_at)}</div>
          </div>
          <div>
            <div className="text-xs text-stone-500">Đối tượng gần nhất</div>
            <div className="mt-1 break-all font-medium text-stone-800">{backupState?.last_object_key || "—"}</div>
          </div>
          {backupState?.last_error ? (
            <div className="md:col-span-3">
              <div className="text-xs text-rose-500">Lỗi gần nhất</div>
              <div className="mt-1 break-all rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-rose-700">{backupState.last_error}</div>
            </div>
          ) : null}
          </div>

          <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700" onClick={() => void testBackup()} disabled={isTestingBackup}>
            {isTestingBackup ? <LoaderCircle className="size-4 animate-spin" /> : <Shield className="size-4" />}
            Kiểm tra kết nối
          </Button>
          <Button type="button" variant="outline" className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700" onClick={() => void loadBackups()} disabled={isLoadingBackups}>
            {isLoadingBackups ? <LoaderCircle className="size-4 animate-spin" /> : <RefreshCcw className="size-4" />}
            Làm mới danh sách
          </Button>
          <Button type="button" variant="outline" className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700" onClick={() => void runBackup()} disabled={isRunningBackup || Boolean(backupState?.running)}>
            {isRunningBackup || backupState?.running ? <LoaderCircle className="size-4 animate-spin" /> : <Play className="size-4" />}
            Sao lưu ngay
          </Button>
          <Button className="h-9 rounded-xl bg-stone-900 px-4 text-white hover:bg-stone-800" onClick={() => void saveConfig()} disabled={isSavingConfig}>
            {isSavingConfig ? <LoaderCircle className="size-4 animate-spin" /> : <CloudUpload className="size-4" />}
            Lưu cấu hình
          </Button>
          </div>

          <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-medium text-stone-800">Lịch sử sao lưu</h3>
              <p className="text-xs text-stone-500">Hỗ trợ xem thông tin đối tượng và xóa trực tiếp bản sao lưu từ xa.</p>
            </div>
          </div>

          {isLoadingBackups ? (
            <div className="flex items-center justify-center py-10">
              <LoaderCircle className="size-5 animate-spin text-stone-500" />
            </div>
          ) : backups.length === 0 ? (
            <div className="rounded-xl bg-stone-100 px-6 py-10 text-center text-sm text-stone-500">
              Chưa có bản sao lưu từ xa. Lưu cấu hình và thực hiện sao lưu thủ công một lần để nó xuất hiện ở đây.
            </div>
          ) : (
            <div className="space-y-3">
              {backups.map((item) => {
                const isDeleting = deletingBackupKey === item.key;
                return (
                  <div key={item.key} className="flex flex-col gap-3 rounded-xl border border-stone-200 bg-white px-4 py-4 md:flex-row md:items-center md:justify-between">
                    <div className="min-w-0 space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="break-all text-sm font-medium text-stone-800">{item.name}</div>
                        {item.encrypted ? <Badge variant="secondary" className="rounded-md">Đã mã hóa</Badge> : null}
                      </div>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-500">
                        <span>Dung lượng {formatBytes(item.size)}</span>
                        <span>Cập nhật lúc {formatDateTime(item.updated_at)}</span>
                        <span className="break-all">Key đối tượng {item.key}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                        onClick={() => void handleDownload(item.key, item.name)}
                      >
                        <Download className="size-4" />
                        Tải xuống
                      </Button>
                      <Button type="button" variant="outline" className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700" onClick={() => void handleOpenDetail(item.key)}>
                        <Eye className="size-4" />
                        Xem chi tiết
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        className="h-9 rounded-xl border-rose-200 bg-white px-4 text-rose-700"
                        onClick={() => void removeBackup(item.key)}
                        disabled={isDeleting}
                      >
                        {isDeleting ? <LoaderCircle className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
                        Xóa
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          </div>
        </CardContent>
      </Card>

      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="flex max-h-[85vh] max-w-3xl flex-col overflow-hidden rounded-2xl border-stone-200 bg-white">
          <DialogHeader className="shrink-0 border-b border-stone-200 pb-3">
            <DialogTitle>Chi tiết sao lưu</DialogTitle>
          </DialogHeader>
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
            {detailLoading ? (
              <div className="flex items-center justify-center py-16">
                <LoaderCircle className="size-5 animate-spin text-stone-500" />
              </div>
            ) : !detail ? (
              <div className="rounded-xl bg-stone-100 px-6 py-10 text-center text-sm text-stone-500">
                Tạm thời không thể đọc chi tiết bản sao lưu; nếu đây là bản sao lưu được mã hóa, vui lòng xác nhận rằng bạn đã điền đúng mật khẩu mã hóa và lưu cấu hình trước.
              </div>
            ) : (
              <>
                <div className="grid gap-3 rounded-xl border border-stone-200 bg-stone-100 px-4 py-4 text-sm text-stone-600 md:grid-cols-2">
                  <div>
                    <div className="text-xs text-stone-500">Tên đối tượng</div>
                    <div className="mt-1 break-all font-medium text-stone-800">{detail.name}</div>
                  </div>
                  <div>
                    <div className="text-xs text-stone-500">Thời gian tạo</div>
                    <div className="mt-1 font-medium text-stone-800">{formatDateTime(detail.created_at)}</div>
                  </div>
                  <div>
                    <div className="text-xs text-stone-500">Cách thức kích hoạt</div>
                    <div className="mt-1 font-medium text-stone-800">{detail.trigger || "—"}</div>
                  </div>
                  <div>
                    <div className="text-xs text-stone-500">Phiên bản ứng dụng</div>
                    <div className="mt-1 font-medium text-stone-800">{detail.app_version || "—"}</div>
                  </div>
                  <div className="md:col-span-2">
                    <div className="text-xs text-stone-500">Backend lưu trữ</div>
                    <pre className="mt-1 overflow-x-auto rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-stone-700">{JSON.stringify(detail.storage_backend || {}, null, 2)}</pre>
                  </div>
                </div>

                <div className="space-y-3">
                  <h4 className="text-sm font-medium text-stone-800">Nội dung tệp</h4>
                  <div className="space-y-2">
                    {detail.files.map((item) => (
                      <div key={item.name} className="rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm">
                        <div className="break-all font-medium text-stone-800">{item.name}</div>
                        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-500">
                          <span>{item.exists ? "Đã bao gồm" : "Thiếu"}</span>
                          <span>Dung lượng {formatBytes(item.size)}</span>
                          <span>{item.content_type || "application/octet-stream"}</span>
                          <span className="break-all">SHA256 {item.sha256 || "—"}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="space-y-3">
                  <h4 className="text-sm font-medium text-stone-800">Nội dung bản chụp (Snapshot)</h4>
                  <div className="grid gap-3 md:grid-cols-2">
                    {detail.snapshots.map((item) => (
                      <div key={item.name} className="rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm">
                        <div className="font-medium text-stone-800">{item.name}</div>
                        <div className="mt-2 text-xs text-stone-500">Số bản ghi {item.count}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}


