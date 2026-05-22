"use client";

import { useEffect, useState } from "react";
import { Film, Download, Trash2, LoaderCircle, Play } from "lucide-react";
import { toast } from "sonner";

import { getValidatedAuthSession } from "@/lib/auth-session";
import { request } from "@/lib/request";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type VideoItem = {
  path: string;
  name: string;
  size_bytes: number;
  created_at: string;
};

export default function VideoManagerPage() {
  const { session } = useAuthGuard(["admin"]);
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [loading, setLoading] = useState(true);

  const loadVideos = async () => {
    try {
      // Videos are stored alongside images — filter by video extensions
      const resp = await request.get("/api/images");
      const items = (resp.data as any)?.items || [];
      const videoItems = items.filter((i: any) => {
        const name = (i.path || i.name || "").toLowerCase();
        return name.endsWith(".mp4") || name.endsWith(".webm") || name.endsWith(".mov") || name.endsWith(".avi");
      });
      setVideos(videoItems);
    } catch (e) {
      toast.error("Không tải được danh sách video");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadVideos();
  }, []);

  const handleDelete = async (path: string) => {
    try {
      await request.post("/api/images/delete", { paths: [path] });
      toast.success("Đã xóa video");
      loadVideos();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail?.error || "Không xóa được video");
    }
  };

  const handleDownload = (path: string) => {
    window.open(`/api/images/download/${encodeURIComponent(path)}`, "_blank");
  };

  if (!session) return null;

  const formatSize = (bytes: number) => {
    if (bytes > 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    if (bytes > 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${bytes} B`;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between border-b border-black/[0.04] pb-6">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 shadow-lg shadow-violet-500/20">
            <Film className="size-5 text-white" />
          </div>
          <div>
            <p className="text-[11px] font-bold tracking-widest text-violet-500 uppercase mb-1">Thư viện</p>
            <h1 className="text-[26px] font-bold tracking-tight text-slate-900">Quản lý video</h1>
            <p className="text-[14px] text-slate-500 mt-0.5">Video đã tạo từ Veo và các model khác</p>
          </div>
        </div>
        <Button className="rounded-xl" onClick={loadVideos} disabled={loading}>
          <LoaderCircle className={`size-4 ${loading ? "animate-spin" : ""}`} />
          Làm mới
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <LoaderCircle className="size-8 animate-spin text-stone-400" />
        </div>
      ) : videos.length === 0 ? (
        <Card className="rounded-2xl card-3d card-tint-sky">
          <CardContent className="flex flex-col items-center py-16 text-center">
            <Film className="size-16 text-stone-300" />
            <p className="mt-4 text-stone-500">Chưa có video nào</p>
            <p className="text-sm text-stone-400">Video tạo từ Veo sẽ hiển thị ở đây</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {videos.map((video) => (
            <Card key={video.path} className="group rounded-2xl card-3d card-tint-sky hover:shadow-md transition-all">
              <CardContent className="p-4">
                <div className="flex items-center gap-3 mb-3">
                  <div className="flex size-10 items-center justify-center rounded-xl bg-violet-100">
                    <Play className="size-5 text-violet-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-stone-800 truncate">{video.name}</p>
                    <p className="text-xs text-stone-400">{formatSize(video.size_bytes)}</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1 rounded-lg text-xs"
                    onClick={() => handleDownload(video.path)}
                  >
                    <Download className="size-3" /> Tải
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="rounded-lg text-xs text-rose-600 hover:bg-rose-50"
                    onClick={() => handleDelete(video.path)}
                  >
                    <Trash2 className="size-3" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
