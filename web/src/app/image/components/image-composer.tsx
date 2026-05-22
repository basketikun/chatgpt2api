"use client";
import { ArrowUp, Check, ChevronDown, ImagePlus, LoaderCircle, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ClipboardEvent, type RefObject } from "react";

import { ImageLightbox } from "@/components/image-lightbox";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type ImageComposerProps = {
  prompt: string;
  imageCount: string;
  imageSize: string;
  model: string;
  imageModels: Array<{ id: string; label: string }>;
  availableQuota: string;
  activeTaskCount: number;
  referenceImages: Array<{ name: string; dataUrl: string }>;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onPromptChange: (value: string) => void;
  onImageCountChange: (value: string) => void;
  onImageSizeChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onSubmit: () => void | Promise<void>;
  onPickReferenceImage: () => void;
  onPickLibraryImage: () => void;
  onReferenceImageChange: (files: File[]) => void | Promise<void>;
  onRemoveReferenceImage: (index: number) => void;
};

export function ImageComposer({
  prompt,
  imageCount,
  imageSize,
  model,
  imageModels,
  availableQuota,
  activeTaskCount,
  referenceImages,
  textareaRef,
  fileInputRef,
  onPromptChange,
  onImageCountChange,
  onImageSizeChange,
  onModelChange,
  onSubmit,
  onPickReferenceImage,
  onPickLibraryImage,
  onReferenceImageChange,
  onRemoveReferenceImage,
}: ImageComposerProps) {
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState(0);
  const [isSizeMenuOpen, setIsSizeMenuOpen] = useState(false);
  const [sizeMenuPos, setSizeMenuPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const sizeMenuRef = useRef<HTMLDivElement>(null);
  const sizeMenuBtnRef = useRef<HTMLButtonElement>(null);
  const lightboxImages = useMemo(
    () => referenceImages.map((image, index) => ({ id: `${image.name}-${index}`, src: image.dataUrl })),
    [referenceImages],
  );
  const imageSizeOptions = [
    { value: "", label: "Mặc định" },
    { value: "1:1", label: "1:1 (Hình vuông)" },
    { value: "16:9", label: "16:9 (Ngang)" },
    { value: "4:3", label: "4:3 (Ngang)" },
    { value: "3:4", label: "3:4 (Dọc)" },
    { value: "9:16", label: "9:16 (Dọc)" },
  ];
  const imageSizeLabel = imageSizeOptions.find((option) => option.value === imageSize)?.label || "Mặc định";

  useEffect(() => {
    if (!isSizeMenuOpen) {
      return;
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (!sizeMenuRef.current?.contains(event.target as Node)) {
        setIsSizeMenuOpen(false);
      }
    };
    window.addEventListener("mousedown", handlePointerDown);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
    };
  }, [isSizeMenuOpen]);

  const handleTextareaPaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const imageFiles = Array.from(event.clipboardData.files).filter((file) => file.type.startsWith("image/"));
    if (imageFiles.length === 0) {
      return;
    }

    event.preventDefault();
    void onReferenceImageChange(imageFiles);
  };

  return (
    <div className="shrink-0 flex justify-center px-1 sm:px-0">
      <div style={{ width: "min(980px, 100%)" }}>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(event) => {
            void onReferenceImageChange(Array.from(event.target.files || []));
          }}
        />

        {referenceImages.length > 0 ? (
          <div className="mb-2 flex gap-2 overflow-x-auto px-1 pb-1 sm:mb-3 sm:flex-wrap sm:overflow-visible sm:pb-0">
            {referenceImages.map((image, index) => (
              <div key={`${image.name}-${index}`} className="relative size-14 shrink-0 sm:size-16">
                <button
                  type="button"
                  onClick={() => {
                    setLightboxIndex(index);
                    setLightboxOpen(true);
                  }}
                  className="group size-14 overflow-hidden rounded-2xl border border-stone-200 bg-stone-100 transition hover:border-stone-300 sm:size-16"
                  aria-label={`Xem ảnh tham khảo ${image.name || index + 1}`}
                >
                  <img
                    src={image.dataUrl}
                    alt={image.name || `ảnh tham khảo ${index + 1}`}
                    className="h-full w-full object-cover"
                  />
                </button>
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onRemoveReferenceImage(index);
                  }}
                  className="absolute -right-1 -top-1 inline-flex size-5 items-center justify-center rounded-full border border-stone-200 bg-white text-stone-500 transition hover:border-stone-300 hover:text-stone-800"
                  aria-label={`Xóa ảnh tham khảo ${image.name || index + 1}`}
                >
                  <X className="size-3" />
                </button>
              </div>
            ))}
          </div>
        ) : null}

        <div className="overflow-hidden rounded-[24px] border border-stone-200 bg-white shadow-[0_14px_60px_-42px_rgba(15,23,42,0.45)] sm:rounded-[32px] sm:shadow-none">
          <div
            className="relative cursor-text"
            onClick={() => {
              textareaRef.current?.focus();
            }}
          >
            <ImageLightbox
              images={lightboxImages}
              currentIndex={lightboxIndex}
              open={lightboxOpen}
              onOpenChange={setLightboxOpen}
              onIndexChange={setLightboxIndex}
            />
            <Textarea
              ref={textareaRef}
              value={prompt}
              onChange={(event) => onPromptChange(event.target.value)}
              onPaste={handleTextareaPaste}
              placeholder={
                referenceImages.length > 0
                  ? "Mô tả cách bạn muốn sửa ảnh tham chiếu"
                  : "Nhập mô tả hình ảnh bạn muốn tạo, hoặc dán ảnh vào đây"
              }
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void onSubmit();
                }
              }}
              className="min-h-[120px] resize-none rounded-[24px] border-2 border-indigo-200 bg-indigo-50/50 px-4 pt-4 pb-4 text-[16px] font-semibold leading-7 text-slate-900 shadow-none placeholder:text-slate-400 focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:border-indigo-400 sm:min-h-[160px] sm:rounded-[32px] sm:px-6 sm:pt-6 sm:pb-6 dark:bg-[#1a1a1a] dark:border-indigo-500/30 dark:text-[#ededed] dark:placeholder:text-[#6b7280]"
            />

            <div className="rounded-b-[24px] border-t border-stone-200 bg-white px-3 pb-3 pt-2 sm:px-6 sm:pb-4 sm:pt-3" onClick={(event) => event.stopPropagation()}>
              <div className="flex items-end justify-between gap-2 sm:gap-3">
                <div className="hide-scrollbar flex min-w-0 flex-1 flex-nowrap items-center gap-1.5 overflow-x-auto pb-0.5 sm:flex-wrap sm:gap-2 sm:overflow-visible sm:pb-0">
                  <Button
                    type="button"
                    variant="outline"
                    className="h-8 shrink-0 rounded-full border-stone-200 bg-white px-2.5 text-xs font-medium text-stone-700 shadow-none"
                    onClick={onPickReferenceImage}
                  >
                    <ImagePlus className="size-3.5" />
                    <span className="hidden sm:inline ml-1">Tải ảnh</span>
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    className="h-8 shrink-0 rounded-full border-stone-200 bg-white px-2.5 text-xs font-medium text-stone-700 shadow-none"
                    onClick={onPickLibraryImage}
                  >
                    <ImagePlus className="size-3.5" />
                    <span className="hidden sm:inline ml-1">Thư viện</span>
                  </Button>
                  {activeTaskCount > 0 && (
                    <div className="flex shrink-0 items-center gap-1 rounded-full bg-amber-50 px-2 py-1 text-[10px] font-medium text-amber-700 sm:gap-1.5 sm:px-3 sm:py-2 sm:text-xs">
                      <LoaderCircle className="size-3 animate-spin" />
                      {activeTaskCount}<span className="hidden sm:inline"> đang xử lý</span>
                    </div>
                  )}
                  {imageModels.length > 0 && (
                    <div className="flex h-8 shrink-0 items-center gap-1 rounded-full border border-stone-200 bg-white px-2 sm:px-3">
                      <select
                        value={model}
                        onChange={(e) => onModelChange(e.target.value)}
                        className="h-7 bg-transparent text-xs font-medium text-stone-700 focus:outline-none max-w-[130px] truncate"
                      >
                        {imageModels.map(m => (
                          <option key={m.id} value={m.id}>{m.label}</option>
                        ))}
                      </select>
                    </div>
                  )}
                  <div className="flex h-8 shrink-0 items-center gap-1 rounded-full border border-stone-200 bg-white px-2 sm:px-3">
                    <Input
                      type="number"
                      inputMode="numeric"
                      min="1"
                      max="100"
                      step="1"
                      value={imageCount}
                      onChange={(event) => onImageCountChange(event.target.value)}
                      className="h-7 w-[40px] border-0 bg-transparent px-0 text-center text-xs font-medium text-stone-700 shadow-none focus-visible:ring-0 sm:h-8 sm:w-[64px] sm:text-sm"
                    />
                  </div>
                  <div
                    className="relative flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-stone-200 bg-white px-2 py-0.5 text-[11px] sm:h-auto sm:gap-2 sm:px-3 sm:py-1 sm:text-[13px]"
                  >
                    <span className="hidden font-medium text-stone-700 sm:inline sm:text-sm">Tỷ lệ</span>
                    <button
                      ref={sizeMenuBtnRef}
                      type="button"
                      className="flex h-7 w-[78px] items-center justify-between bg-transparent text-left text-xs font-bold text-stone-700 min-[390px]:w-[96px] sm:h-8 sm:w-[132px]"
                      onClick={() => {
                        if (!isSizeMenuOpen && sizeMenuBtnRef.current) {
                          const rect = sizeMenuBtnRef.current.getBoundingClientRect();
                          const menuWidth = Math.min(186, window.innerWidth - 32);
                          setSizeMenuPos({ top: rect.top - 8, left: Math.max(16, Math.min(rect.left, window.innerWidth - menuWidth - 16)) });
                        }
                        setIsSizeMenuOpen((open) => !open);
                      }}
                    >
                      <span className="truncate">{imageSizeLabel}</span>
                      <ChevronDown className={cn("size-4 shrink-0 opacity-60 transition", isSizeMenuOpen && "rotate-180")} />
                    </button>
                    {isSizeMenuOpen ? (
                      <div
                        ref={sizeMenuRef}
                        className="fixed z-[80] max-h-[45dvh] overflow-y-auto rounded-3xl border border-stone-200 bg-white p-2 shadow-[0_24px_80px_-32px_rgba(15,23,42,0.35)]"
                        style={{
                          top: sizeMenuPos.top,
                          left: sizeMenuPos.left,
                          transform: "translateY(-100%)",
                          width: "min(186px, calc(100vw - 2rem))",
                        }}
                      >
                        {imageSizeOptions.map((option) => {
                          const active = option.value === imageSize;
                          return (
                            <button
                              key={option.label}
                              type="button"
                              className={cn(
                                "flex w-full items-center justify-between rounded-2xl px-3 py-2 text-left text-sm text-stone-700 transition hover:bg-stone-200",
                                active && "bg-stone-100 font-medium text-stone-950",
                              )}
                              onClick={() => {
                                onImageSizeChange(option.value);
                                setIsSizeMenuOpen(false);
                              }}
                            >
                              <span>{option.label}</span>
                              {active ? <Check className="size-4" /> : null}
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>

                </div>

                <button
                  type="button"
                  onClick={() => void onSubmit()}
                  disabled={!prompt.trim()}
                  className="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-stone-900 text-white transition hover:bg-stone-800 disabled:cursor-not-allowed disabled:bg-stone-300 sm:size-11"
                  aria-label={referenceImages.length > 0 ? "Sửa ảnh" : "Tạo ảnh"}
                >
                  <ArrowUp className="size-3.5 sm:size-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

