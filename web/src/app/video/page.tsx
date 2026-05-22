"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Video, LoaderCircle, Play } from "lucide-react";
import { toast } from "sonner";

import { getValidatedAuthSession } from "@/lib/auth-session";
import { request } from "@/lib/request";
import { useAuthGuard } from "@/lib/use-auth-guard";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export default function VideoPage() {
  const { session } = useAuthGuard(["admin", "user"]);
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const [aspectRatio, setAspectRatio] = useState("16:9");
  const [duration, setDuration] = useState("8");
  const [resolution, setResolution] = useState("720p");
  const [generating, setGenerating] = useState(false);
  const [resultB64, setResultB64] = useState<string | null>(null);
  const [error, setError] = useState("");

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      toast.error("Vui lòng nhập mô tả video");
      return;
    }
    setGenerating(true);
    setError("");
    setResultB64(null);
    try {
      const resp = await request.post("/v1/video/generations", {
        prompt: prompt.trim(),
        aspect_ratio: aspectRatio,
        duration: duration,
        resolution: resolution,
      });
      const data = resp.data as any;
      if (data?.data?.[0]?.b64_json) {
        setResultB64(data.data[0].b64_json);
        toast.success("Đã tạo video thành công!");
      } else if (data?.detail?.error) {
        setError(data.detail.error);
        toast.error(data.detail.error);
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail?.error || e?.message || "Lỗi tạo video";
      setError(msg);
      toast.error(msg);
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = () => {
    if (!resultB64) return;
    const a = document.createElement("a");
    a.href = `data:video/mp4;base64,${resultB64}`;
    a.download = `veo-${Date.now()}.mp4`;
    a.click();
  };

  if (!session) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 border-b border-black/[0.04] pb-6">
        <div className="flex size-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 shadow-lg shadow-violet-500/20">
          <Video className="size-5 text-white" />
        </div>
        <div>
          <p className="text-[11px] font-bold tracking-widest text-violet-500 uppercase mb-1">Tạo video AI</p>
          <h1 className="text-[26px] font-bold tracking-tight text-slate-900">Tạo video</h1>
          <p className="text-[14px] text-slate-500 mt-0.5">Veo 3.1 — Google DeepMind video generation</p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="rounded-2xl card-3d card-tint-indigo">
          <CardContent className="space-y-4 p-6">
            <div className="space-y-2">
              <label className="text-sm font-medium text-stone-700">Mô tả video</label>
              <Textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Mô tả cảnh bạn muốn tạo... A cinematic drone shot of..."
                className="min-h-[120px] rounded-xl border-stone-200 bg-white"
              />
              <p className="text-xs text-stone-500">
                Mô tả càng chi tiết, video càng đẹp. Bao gồm: chủ thể, hành động, góc quay, ánh sáng, phong cách.
              </p>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-stone-600">Tỷ lệ</label>
                <select
                  value={aspectRatio}
                  onChange={(e) => setAspectRatio(e.target.value)}
                  className="h-10 w-full rounded-xl border border-stone-200 bg-white px-3 text-sm"
                >
                  <option value="16:9">16:9 (ngang)</option>
                  <option value="9:16">9:16 (dọc)</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-stone-600">Thời lượng</label>
                <select
                  value={duration}
                  onChange={(e) => setDuration(e.target.value)}
                  className="h-10 w-full rounded-xl border border-stone-200 bg-white px-3 text-sm"
                >
                  <option value="4">4 giây</option>
                  <option value="6">6 giây</option>
                  <option value="8">8 giây</option>
                </select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-stone-600">Độ phân giải</label>
                <select
                  value={resolution}
                  onChange={(e) => setResolution(e.target.value)}
                  className="h-10 w-full rounded-xl border border-stone-200 bg-white px-3 text-sm"
                >
                  <option value="720p">720p</option>
                  <option value="1080p">1080p (8s)</option>
                  <option value="4k">4K (8s)</option>
                </select>
              </div>
            </div>

            <Button
              className="w-full h-12 rounded-xl bg-gradient-to-r from-violet-500 to-purple-600 text-white font-semibold hover:from-violet-600 hover:to-purple-700 shadow-lg shadow-violet-500/25"
              onClick={handleGenerate}
              disabled={generating || !prompt.trim()}
            >
              {generating ? (
                <><LoaderCircle className="size-5 animate-spin" /> Đang tạo video... (có thể mất 1-5 phút)</>
              ) : (
                <><Play className="size-5" /> Tạo video</>
              )}
            </Button>
          </CardContent>
        </Card>

        <Card className="rounded-2xl card-3d card-tint-indigo">
          <CardContent className="flex min-h-[350px] flex-col items-center justify-center p-6">
            {generating ? (
              <div className="flex flex-col items-center gap-4 text-stone-500">
                <LoaderCircle className="size-12 animate-spin text-violet-500" />
                <p className="text-sm">Đang tạo video bằng Veo 3.1...</p>
                <p className="text-xs text-stone-400">Quá trình này có thể mất 1-5 phút</p>
              </div>
            ) : resultB64 ? (
              <div className="flex w-full flex-col items-center gap-4">
                <video
                  src={`data:video/mp4;base64,${resultB64}`}
                  controls
                  className="w-full max-h-[400px] rounded-xl shadow-lg"
                />
                <Button
                  className="rounded-xl bg-stone-900 text-white hover:bg-stone-800"
                  onClick={handleDownload}
                >
                  <Play className="size-4" /> Tải video MP4
                </Button>
              </div>
            ) : error ? (
              <div className="text-center space-y-2">
                <p className="text-rose-500 font-medium">Lỗi tạo video</p>
                <p className="text-sm text-stone-500 max-w-md">{error}</p>
                <p className="text-xs text-stone-400">
                  Veo 3.1 yêu cầu API key có quyền truy cập.{" "}
                  <a href="https://aistudio.google.com" className="text-violet-500 underline" target="_blank">
                    Đăng ký tại Google AI Studio
                  </a>
                </p>
              </div>
            ) : (
              <div className="text-center space-y-2 text-stone-400">
                <Video className="size-16 mx-auto opacity-30" />
                <p className="text-sm">Nhập mô tả và nhấn "Tạo video"</p>
                <p className="text-xs">Video sẽ hiển thị ở đây sau khi tạo xong</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
