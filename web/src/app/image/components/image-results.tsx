"use client";

import { AlertCircle, LoaderCircle } from "lucide-react";
import { useMemo, useState } from "react";

import { ImageLightbox } from "@/components/image-lightbox";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { ImageConversation, ImageConversationTurn, StoredImage, StoredReferenceImage } from "@/store/image-conversations";

type ImageResultsProps = {
  selectedConversation: ImageConversation | null;
  isSelectedGenerating: boolean;
  openLightbox: (imageId: string) => void;
  formatConversationTime: (value: string) => string;
};

export function ImageResults({
  selectedConversation,
  isSelectedGenerating,
  openLightbox,
  formatConversationTime,
}: ImageResultsProps) {
  const [referenceLightboxImages, setReferenceLightboxImages] = useState<Array<{ id: string; src: string }>>([]);
  const [referenceLightboxOpen, setReferenceLightboxOpen] = useState(false);
  const [referenceLightboxIndex, setReferenceLightboxIndex] = useState(0);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);

  const latestTurnId = useMemo(
    () => selectedConversation?.turns[selectedConversation.turns.length - 1]?.id ?? null,
    [selectedConversation],
  );

  if (!selectedConversation) {
    return (
      <div className="flex h-full min-h-[420px] items-center justify-center text-center">
        <div className="w-full max-w-4xl">
          <h1
            className="text-6xl font-semibold tracking-tight text-stone-950 md:text-8xl"
            style={{
              fontFamily: '"Palatino Linotype","Book Antiqua","URW Palladio L","Times New Roman",serif',
            }}
          >
            将想法变成图像
          </h1>
          <p
            className="mt-4 text-[30px] italic tracking-[0.01em] text-stone-500"
            style={{
              fontFamily: '"Palatino Linotype","Book Antiqua","URW Palladio L","Times New Roman",serif',
            }}
          >
            描述一个场景、一种氛围或一个角色，让下一张图像从这里开始。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-[980px] flex-col gap-6">
      <ImageLightbox
        images={referenceLightboxImages}
        currentIndex={referenceLightboxIndex}
        open={referenceLightboxOpen}
        onOpenChange={setReferenceLightboxOpen}
        onIndexChange={setReferenceLightboxIndex}
      />
      <ErrorDetailDialog error={errorDetail} onOpenChange={(open) => !open && setErrorDetail(null)} />

      {selectedConversation.turns.map((turn) => (
        <ConversationTurnSection
          key={turn.id}
          turn={turn}
          isGenerating={isSelectedGenerating && latestTurnId === turn.id}
          openLightbox={openLightbox}
          formatConversationTime={formatConversationTime}
          onOpenReference={(images, index) => {
            setReferenceLightboxImages(
              images.map((image, imageIndex) => ({
                id: `${image.name}-${imageIndex}`,
                src: image.dataUrl,
              })),
            );
            setReferenceLightboxIndex(index);
            setReferenceLightboxOpen(true);
          }}
          onShowError={setErrorDetail}
        />
      ))}
    </div>
  );
}

function ConversationTurnSection({
  turn,
  isGenerating,
  openLightbox,
  formatConversationTime,
  onOpenReference,
  onShowError,
}: {
  turn: ImageConversationTurn;
  isGenerating: boolean;
  openLightbox: (imageId: string) => void;
  formatConversationTime: (value: string) => string;
  onOpenReference: (images: StoredReferenceImage[], index: number) => void;
  onShowError: (error: string) => void;
}) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex justify-end">
        <div className="w-full max-w-[min(820px,92%)] px-1 pt-1">
          <div className="ml-auto flex max-w-full flex-col items-end gap-2.5 text-right">
            <div className="w-fit max-w-[min(32rem,100%)] whitespace-pre-wrap break-words text-[15px] leading-6 text-stone-700 sm:leading-7">
              {turn.prompt}
            </div>
            {turn.optimizedPrompt ? (
              <div className="w-fit max-w-[min(32rem,100%)] rounded-2xl border border-emerald-100 bg-emerald-50/70 px-4 py-3 text-left text-xs leading-5 text-emerald-800">
                <div className="mb-1 font-semibold text-emerald-900">
                  已优化后发送{turn.promptOptimizer ? ` · ${turn.promptOptimizer}` : ""}
                </div>
                <div className="whitespace-pre-wrap break-words">{turn.optimizedPrompt}</div>
              </div>
            ) : null}
            {turn.referenceImages?.length ? (
              <div
                className="grid w-fit auto-rows-fr gap-3"
                style={{
                  gridTemplateColumns: `repeat(${Math.min(turn.referenceImages.length, 3)}, minmax(0, 1fr))`,
                }}
              >
                {turn.referenceImages.map((image, index) => (
                  <button
                    key={`${image.name}-${index}`}
                    type="button"
                    onClick={() => onOpenReference(turn.referenceImages || [], index)}
                    className="group relative aspect-square min-h-[112px] overflow-hidden rounded-[18px] border border-stone-200/80 bg-stone-100/60 text-left transition hover:border-stone-300 sm:min-h-[136px]"
                    aria-label={`预览参考图 ${image.name || index + 1}`}
                  >
                    <img
                      src={image.dataUrl}
                      alt={image.name || `参考图 ${index + 1}`}
                      className="absolute inset-0 h-full w-full object-cover transition duration-200 group-hover:scale-[1.02]"
                    />
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="flex justify-start">
        <div className="w-full p-1">
          <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-stone-500">
            <span className="rounded-full bg-stone-100 px-3 py-1">{turn.mode === "edit" ? "编辑图" : "文生图"}</span>
            <span className="rounded-full bg-stone-100 px-3 py-1">{turn.model}</span>
            <span className="rounded-full bg-stone-100 px-3 py-1">{turn.count} 张</span>
            {turn.optimizedPrompt ? (
              <span className="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">提示词已优化</span>
            ) : null}
            <span className="rounded-full bg-stone-100 px-3 py-1">{formatConversationTime(turn.createdAt)}</span>
            {isGenerating ? (
              <span className="rounded-full bg-amber-50 px-3 py-1 text-amber-700">处理中</span>
            ) : null}
          </div>

          {turn.status === "error" && turn.images.length === 0 ? (
            <ErrorNotice error={turn.error || "生成失败"} onShowDetail={onShowError} />
          ) : null}

          {turn.images.length > 0 ? (
            <div className="columns-1 gap-4 space-y-4 sm:columns-2 xl:columns-3">
              {turn.images.map((image, index) => (
                <div key={image.id} className="break-inside-avoid overflow-hidden rounded-[22px]">
                  <ImageResultCard image={image} index={index} onOpen={openLightbox} onShowError={onShowError} />
                </div>
              ))}
            </div>
          ) : null}

          {turn.status === "error" && turn.images.length > 0 ? (
            <div className="mt-4">
              <ErrorNotice error={turn.error || "生成失败"} tone="amber" onShowDetail={onShowError} />
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function ImageResultCard({
  image,
  index,
  onOpen,
  onShowError,
}: {
  image: StoredImage;
  index: number;
  onOpen: (imageId: string) => void;
  onShowError: (error: string) => void;
}) {
  if (image.status === "success" && image.b64_json) {
    return (
      <button type="button" onClick={() => onOpen(image.id)} className="group block w-full cursor-zoom-in">
        <img
          src={`data:image/png;base64,${image.b64_json}`}
          alt={`Generated result ${index + 1}`}
          className="block h-auto w-full transition duration-200 group-hover:brightness-90"
        />
      </button>
    );
  }

  if (image.status === "error") {
    const error = image.error || "生成失败";
    return (
      <div className="flex min-h-[320px] flex-col items-center justify-center gap-4 bg-rose-50 px-6 py-8 text-center text-sm leading-6 text-rose-600">
        <AlertCircle className="size-6" />
        <div>
          <p className="font-medium">第 {index + 1} 张生成失败</p>
          <p className="mt-1 line-clamp-2 text-rose-500">{summarizeError(error)}</p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="rounded-full border-rose-200 bg-white/70 text-rose-700 hover:bg-white"
          onClick={() => onShowError(error)}
        >
          查看完整错误
        </Button>
      </div>
    );
  }

  return (
    <div className="flex min-h-[320px] flex-col items-center justify-center gap-3 bg-stone-100/80 px-6 py-8 text-center text-stone-500">
      <div className="rounded-full bg-white p-3 shadow-sm">
        <LoaderCircle className="size-5 animate-spin" />
      </div>
      <p className="text-sm">正在生成图片...</p>
    </div>
  );
}

function summarizeError(error: string) {
  const normalized = String(error || "生成失败").replace(/\s+/g, " ").trim();
  return normalized.length > 96 ? `${normalized.slice(0, 96)}...` : normalized;
}

function ErrorNotice({
  error,
  tone = "rose",
  onShowDetail,
}: {
  error: string;
  tone?: "rose" | "amber";
  onShowDetail: (error: string) => void;
}) {
  const classes =
    tone === "amber"
      ? "border-amber-300 bg-amber-50/70 text-amber-700"
      : "border-rose-300 bg-rose-50/70 text-rose-600";

  return (
    <div className={`flex flex-col gap-3 border-l-2 px-4 py-3 text-sm leading-6 sm:flex-row sm:items-center sm:justify-between ${classes}`}>
      <span className="line-clamp-2">{summarizeError(error)}</span>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="w-fit shrink-0 rounded-full border-white/70 bg-white/70"
        onClick={() => onShowDetail(error)}
      >
        查看完整错误
      </Button>
    </div>
  );
}

function ErrorDetailDialog({
  error,
  onOpenChange,
}: {
  error: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={Boolean(error)} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[82vh] w-[min(92vw,820px)] overflow-hidden rounded-3xl bg-white p-0">
        <DialogHeader className="border-b border-stone-100 px-6 pb-4 pt-6">
          <DialogTitle>完整错误信息</DialogTitle>
          <DialogDescription>系统错误不会再挤在图片窗口里，完整内容在这里查看。</DialogDescription>
        </DialogHeader>
        <pre className="max-h-[58vh] overflow-auto whitespace-pre-wrap break-words bg-stone-950 px-6 py-5 text-xs leading-5 text-stone-100">
          {error}
        </pre>
      </DialogContent>
    </Dialog>
  );
}
