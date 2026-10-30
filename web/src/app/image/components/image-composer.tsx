"use client";
import { ArrowUp, ChevronDown, ImagePlus, Info, LoaderCircle, RectangleHorizontal, RectangleVertical, Square, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ClipboardEvent, type DragEvent, type RefObject } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { ImageLightbox } from "@/components/image-lightbox";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { ImageModel } from "@/lib/api";
import { cn } from "@/lib/utils";

type ImageComposerProps = {
  prompt: string;
  imageCount: string;
  imageRatio: string;
  imageTier: string;
  imageWidth: string;
  imageHeight: string;
  imageQuality: string;
  imageModel: ImageModel;
  imageModels: ImageModel[];
  availableQuota: string;
  activeTaskCount: number;
  referenceImages: Array<{ name: string; dataUrl: string }>;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onPromptChange: (value: string) => void;
  onImageCountChange: (value: string) => void;
  onImageRatioChange: (value: string) => void;
  onImageTierChange: (value: string) => void;
  onImageWidthChange: (value: string) => void;
  onImageHeightChange: (value: string) => void;
  onImageQualityChange: (value: string) => void;
  onImageModelChange: (value: ImageModel) => void;
  onSubmit: () => void | Promise<void>;
  onPickReferenceImage: () => void;
  onReferenceImageChange: (files: File[]) => void | Promise<void>;
  onRemoveReferenceImage: (index: number) => void;
};

const imageFileNamePattern = /\.(avif|bmp|gif|heic|heif|ico|jpe?g|png|svg|tiff?|webp)$/i;

function isImageFile(file: File) {
  return file.type.startsWith("image/") || (!file.type && imageFileNamePattern.test(file.name));
}

function hasDraggedImages(dataTransfer: DataTransfer) {
  const items = Array.from(dataTransfer.items || []);
  if (items.length > 0) {
    return items.some((item) => item.kind === "file" && (item.type.startsWith("image/") || !item.type));
  }
  return Array.from(dataTransfer.files || []).some(isImageFile);
}

function getDraggedImageFiles(dataTransfer: DataTransfer) {
  return Array.from(dataTransfer.files || []).filter(isImageFile);
}

function buildQualityOptions(t: TFunction) {
  return [
    { value: "auto", label: t("composer.quality.auto") },
    { value: "low", label: t("composer.quality.low") },
    { value: "medium", label: t("composer.quality.medium") },
    { value: "high", label: t("composer.quality.high") },
  ];
}
const aspectOptions = [
  { ratio: "1:1", tier: "1k", width: "1024", height: "1024", label: "1:1", icon: Square },
  { ratio: "2:3", tier: "1k", width: "1024", height: "1536", label: "2:3", icon: RectangleVertical },
  { ratio: "3:2", tier: "1k", width: "1536", height: "1024", label: "3:2", icon: RectangleHorizontal },
  { ratio: "3:4", tier: "1k", width: "1024", height: "1365", label: "3:4", icon: RectangleVertical },
  { ratio: "4:3", tier: "1k", width: "1365", height: "1024", label: "4:3", icon: RectangleHorizontal },
  { ratio: "9:16", tier: "1k", width: "1088", height: "1920", label: "9:16", icon: RectangleVertical },
  { ratio: "16:9", tier: "1k", width: "1920", height: "1088", label: "16:9", icon: RectangleHorizontal },
  { ratio: "1:1", tier: "2k", width: "2048", height: "2048", label: "1:1(2k)", icon: Square },
  { ratio: "16:9", tier: "2k", width: "2560", height: "1440", label: "16:9(2k)", icon: RectangleHorizontal },
  { ratio: "9:16", tier: "2k", width: "1440", height: "2560", label: "9:16(2k)", icon: RectangleVertical },
  { ratio: "16:9", tier: "4k", width: "3840", height: "2160", label: "16:9(4k)", icon: RectangleHorizontal },
  { ratio: "9:16", tier: "4k", width: "2160", height: "3840", label: "9:16(4k)", icon: RectangleVertical },
  { ratio: "auto", tier: "auto", width: "1024", height: "1024", label: "auto", icon: null },
];
const countOptions = Array.from({ length: 10 }, (_, index) => String(index + 1));

export function ImageComposer({
  prompt,
  imageCount,
  imageRatio,
  imageTier,
  imageWidth,
  imageHeight,
  imageQuality,
  imageModel,
  imageModels,
  availableQuota,
  activeTaskCount,
  referenceImages,
  textareaRef,
  fileInputRef,
  onPromptChange,
  onImageCountChange,
  onImageRatioChange,
  onImageTierChange,
  onImageWidthChange,
  onImageHeightChange,
  onImageQualityChange,
  onImageModelChange,
  onSubmit,
  onPickReferenceImage,
  onReferenceImageChange,
  onRemoveReferenceImage,
}: ImageComposerProps) {
  const { t } = useTranslation("image");
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState(0);
  const [isSizeMenuOpen, setIsSizeMenuOpen] = useState(false);
  const [isDraggingImage, setIsDraggingImage] = useState(false);
  const [sizeMenuPos, setSizeMenuPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const sizeMenuRef = useRef<HTMLDivElement>(null);
  const sizeMenuBtnRef = useRef<HTMLButtonElement>(null);
  const lightboxImages = useMemo(
    () => referenceImages.map((image, index) => ({ id: `${image.name}-${index}`, src: image.dataUrl })),
    [referenceImages],
  );
  const modelOptions = useMemo(
    () => imageModels.map((model) => ({ value: model, label: model })),
    [imageModels],
  );
  const qualityOptions = useMemo(() => buildQualityOptions(t), [t]);
  const qualityLabel = qualityOptions.find((option) => option.value === imageQuality)?.label || t("composer.quality.auto");
  const ratioLabel = imageRatio === "auto" ? "auto" : `${imageRatio}(${imageTier})`;
  const imageSizeLabel = t("composer.sizeSummary", { quality: qualityLabel, ratio: ratioLabel, count: Number(imageCount) || 1 });
  const selectedModelLabel = modelOptions.find((option) => option.value === imageModel)?.label || imageModel;
  const isCodexModel = imageModel.toLowerCase().includes("codex");

  useEffect(() => {
    if (!isSizeMenuOpen) {
      return;
    }
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest('[data-slot="select-content"], [data-slot="select-trigger"]')
      ) {
        return;
      }
      if (!sizeMenuRef.current?.contains(target as Node)) {
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

  const handleComposerDragEnter = (event: DragEvent<HTMLDivElement>) => {
    if (!hasDraggedImages(event.dataTransfer)) {
      return;
    }

    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setIsSizeMenuOpen(false);
    setIsDraggingImage(true);
  };

  const handleComposerDragOver = (event: DragEvent<HTMLDivElement>) => {
    if (!hasDraggedImages(event.dataTransfer)) {
      return;
    }

    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setIsDraggingImage(true);
  };

  const handleComposerDragLeave = (event: DragEvent<HTMLDivElement>) => {
    const nextTarget = event.relatedTarget;
    if (nextTarget instanceof Node && event.currentTarget.contains(nextTarget)) {
      return;
    }
    setIsDraggingImage(false);
  };

  const handleComposerDrop = (event: DragEvent<HTMLDivElement>) => {
    const imageFiles = getDraggedImageFiles(event.dataTransfer);
    if (event.dataTransfer.files.length > 0 || imageFiles.length > 0) {
      event.preventDefault();
      event.stopPropagation();
    }

    setIsDraggingImage(false);
    if (imageFiles.length === 0) {
      return;
    }

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
                  className="group size-14 overflow-hidden rounded-2xl border border-stone-200 bg-stone-50 transition hover:border-stone-300 sm:size-16"
                  aria-label={t("composer.referenceImage.previewLabel", { name: image.name || index + 1 })}
                >
                  <img
                    src={image.dataUrl}
                    alt={image.name || t("composer.referenceImage.altFallback", { index: index + 1 })}
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
                  aria-label={t("composer.referenceImage.removeLabel", { name: image.name || index + 1 })}
                >
                  <X className="size-3" />
                </button>
              </div>
            ))}
          </div>
        ) : null}

        <div
          className={cn(
            "overflow-hidden rounded-[24px] border border-stone-200 bg-white shadow-[0_14px_60px_-42px_rgba(15,23,42,0.45)] transition dark:border-white/10 dark:bg-stone-950/80 sm:rounded-[32px] sm:shadow-none",
            isDraggingImage && "border-stone-900 bg-stone-50",
          )}
        >
          <div
            className="relative cursor-text"
            onDragEnter={handleComposerDragEnter}
            onDragOver={handleComposerDragOver}
            onDragLeave={handleComposerDragLeave}
            onDrop={handleComposerDrop}
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
                  ? t("composer.placeholder.editMode")
                  : t("composer.placeholder.generateMode")
              }
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void onSubmit();
                }
              }}
              className="min-h-[82px] resize-none rounded-[24px] border-0 bg-transparent px-4 pt-4 pb-2 text-[15px] leading-6 text-stone-900 shadow-none placeholder:text-stone-400 focus-visible:ring-0 dark:text-stone-100 dark:placeholder:text-stone-500 sm:min-h-[148px] sm:rounded-[32px] sm:px-6 sm:pt-6 sm:pb-20 sm:leading-7"
            />
            {isDraggingImage ? (
              <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center rounded-[24px] border-2 border-dashed border-stone-900 bg-white/85 text-sm font-medium text-stone-900 backdrop-blur-[1px] sm:rounded-[32px]">
                <div className="flex items-center gap-2 rounded-full bg-stone-950 px-4 py-2 text-white shadow-lg">
                  <ImagePlus className="size-4" />
                  <span>{t("composer.dropOverlay")}</span>
                </div>
              </div>
            ) : null}

            <div className="rounded-b-[24px] border-t border-stone-100 bg-white px-3 pb-3 pt-2 dark:border-white/10 dark:bg-stone-950/95 sm:absolute sm:inset-x-0 sm:bottom-0 sm:rounded-b-none sm:border-t-0 sm:bg-gradient-to-t sm:from-white sm:via-white/95 sm:to-transparent sm:px-6 sm:pb-4 sm:pt-6 sm:dark:from-stone-950 sm:dark:via-stone-950/95 sm:dark:to-stone-950/0" onClick={(event) => event.stopPropagation()}>
              <div className="flex items-end justify-between gap-2 sm:gap-3">
                <div className="hide-scrollbar flex min-w-0 flex-1 flex-nowrap items-center gap-1.5 overflow-x-auto pb-0.5 sm:flex-wrap sm:gap-3 sm:overflow-visible sm:pb-0">
                  <Button
                    type="button"
                    variant="outline"
                    className="h-9 shrink-0 rounded-full border-stone-200 bg-white px-3 text-xs font-medium text-stone-700 shadow-none sm:h-10 sm:px-4 sm:text-sm"
                    onClick={onPickReferenceImage}
                    aria-label={referenceImages.length > 0 ? t("composer.actions.addReference") : t("composer.actions.upload")}
                  >
                    <ImagePlus className="size-3.5 sm:size-4" />
                    <span className="hidden sm:inline">{referenceImages.length > 0 ? t("composer.actions.addReference") : t("composer.actions.upload")}</span>
                  </Button>
                  <div className="shrink-0 rounded-full bg-stone-100 px-2 py-1 text-[10px] font-medium text-stone-600 sm:px-3 sm:py-2 sm:text-xs">
                    <span className="hidden sm:inline">{t("composer.quota.label")} </span>{availableQuota}
                  </div>
                  {activeTaskCount > 0 && (
                    <div className="flex shrink-0 items-center gap-1 rounded-full bg-amber-50 px-2 py-1 text-[10px] font-medium text-amber-700 sm:gap-1.5 sm:px-3 sm:py-2 sm:text-xs">
                      <LoaderCircle className="size-3 animate-spin" />
                      {activeTaskCount}<span className="hidden sm:inline"> {t("composer.activeTasks.suffix")}</span>
                    </div>
                  )}
                  <div className="relative flex h-9 min-w-0 shrink items-center rounded-full bg-transparent text-[11px] sm:h-auto sm:shrink-0 sm:text-[13px]">
                    <button
                      ref={sizeMenuBtnRef}
                      type="button"
                      className="inline-flex h-9 w-fit max-w-[calc(100vw-12rem)] items-center justify-between gap-2 rounded-full bg-stone-100 px-4 text-left text-xs font-semibold text-stone-900 sm:h-10 sm:max-w-none sm:text-sm"
                      onClick={() => {
                        if (!isSizeMenuOpen && sizeMenuBtnRef.current) {
                          const rect = sizeMenuBtnRef.current.getBoundingClientRect();
                          const menuWidth = Math.min(460, window.innerWidth - 32);
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
                        className="fixed z-[80] max-h-[62dvh] overflow-y-auto rounded-[24px] border border-stone-200/70 bg-white p-4 shadow-[0_30px_90px_-34px_rgba(15,23,42,0.42)] sm:max-h-none sm:overflow-visible"
                        style={{
                          top: sizeMenuPos.top,
                          left: sizeMenuPos.left,
                          transform: "translateY(-100%)",
                          width: "min(460px, calc(100vw - 2rem))",
                        }}
                      >
                        <h3 className="mb-3 text-base font-semibold text-stone-950">{t("composer.sizeMenu.title")}</h3>
                        <div className="mb-3">
                          <div className="mb-2 text-sm font-medium text-stone-900">{t("composer.sizeMenu.modelLabel")}</div>
                          <Select
                            value={imageModel}
                            onValueChange={(value) => {
                              onImageModelChange(value as ImageModel);
                            }}
                          >
                            <SelectTrigger className="h-10 rounded-xl border-stone-200 bg-white text-sm shadow-none">
                              <div className="flex min-w-0 items-center gap-2">
                                <img
                                  src="/openai.svg"
                                  alt=""
                                  aria-hidden="true"
                                  className="size-4 shrink-0 text-stone-700"
                                />
                                <span className="truncate">{selectedModelLabel}</span>
                              </div>
                            </SelectTrigger>
                            <SelectContent className="z-[120]">
                              {modelOptions.map((option) => (
                                <SelectItem
                                  key={option.value}
                                  value={option.value}
                                  className="pl-10"
                                  style={{
                                    backgroundImage: "url('/openai.svg')",
                                    backgroundRepeat: "no-repeat",
                                    backgroundPosition: "12px center",
                                    backgroundSize: "16px 16px",
                                  }}
                                >
                                  {option.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="mb-3">
                          <div className="mb-2 text-sm font-medium text-stone-900">{t("composer.sizeMenu.qualityLabel")}</div>
                          <div className="grid grid-cols-4 gap-2">
                            {qualityOptions.map((option) => {
                              const active = option.value === imageQuality;
                              return (
                                <button
                                  key={option.value}
                                  type="button"
                                  className={cn(
                                    "h-9 cursor-pointer rounded-full border border-stone-200 bg-white text-sm text-stone-800 transition hover:border-stone-300 hover:bg-stone-50",
                                    active && "border-stone-950 bg-white font-medium text-stone-950",
                                  )}
                                  onClick={() => onImageQualityChange(option.value)}
                                >
                                  {option.label}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                        <div className="mb-3">
                          <div className="mb-2 flex items-center gap-1.5 text-sm font-medium text-stone-900">
                            {t("composer.sizeMenu.sizeLabel")} <Info className="size-3.5 text-stone-400" />
                          </div>
                          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
                            <div className="flex items-center rounded-lg bg-stone-100 px-3 py-1.5 text-sm text-stone-700">
                              <span className="mr-2 text-stone-500">W</span>
                              <Input
                                type="number"
                                inputMode="numeric"
                                min="1"
                                value={imageWidth}
                                onChange={(event) => onImageWidthChange(event.target.value)}
                                className="h-7 border-0 bg-transparent px-0 text-sm font-medium text-stone-800 shadow-none focus-visible:ring-0"
                              />
                            </div>
                            <span className="text-stone-400">×</span>
                            <div className="flex items-center rounded-lg bg-stone-100 px-3 py-1.5 text-sm text-stone-700">
                              <span className="mr-2 text-stone-500">H</span>
                              <Input
                                type="number"
                                inputMode="numeric"
                                min="1"
                                value={imageHeight}
                                onChange={(event) => onImageHeightChange(event.target.value)}
                                className="h-7 border-0 bg-transparent px-0 text-sm font-medium text-stone-800 shadow-none focus-visible:ring-0"
                              />
                            </div>
                          </div>
                        </div>
                        <div className="mb-3">
                          <div className="mb-2 flex items-center gap-1.5 text-sm font-medium text-stone-900">
                            {t("composer.sizeMenu.ratioLabel")} <Info className="size-3.5 text-stone-400" />
                          </div>
                          <div className="grid grid-cols-4 gap-2 sm:grid-cols-5">
                            {aspectOptions.map((option) => {
                              const active = option.ratio === imageRatio && option.tier === imageTier && option.width === imageWidth && option.height === imageHeight;
                              const Icon = option.icon;
                              const disabled = !isCodexModel && (option.tier === "2k" || option.tier === "4k");
                              return (
                                <button
                                  key={`${option.ratio}-${option.tier}-${option.label}`}
                                  type="button"
                                  disabled={disabled}
                                  className={cn(
                                    "flex h-[64px] cursor-pointer flex-col items-center justify-center gap-1 rounded-2xl border border-stone-200 bg-white text-sm text-stone-800 transition hover:border-stone-300 hover:bg-stone-50",
                                    active && "border-stone-950",
                                    disabled && "cursor-not-allowed border-stone-100 bg-stone-50 text-stone-300 hover:border-stone-100 hover:bg-stone-50",
                                  )}
                                  onClick={() => {
                                    if (disabled) {
                                      return;
                                    }
                                    onImageRatioChange(option.ratio);
                                    onImageTierChange(option.tier);
                                    onImageWidthChange(option.width);
                                    onImageHeightChange(option.height);
                                  }}
                                >
                                  {Icon ? (
                                    <>
                                      <Icon className="size-3.5 stroke-[1.8]" />
                                      <span>{option.label}</span>
                                    </>
                                  ) : (
                                    <span>{option.label}</span>
                                  )}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                        <div className="border-t border-stone-100 pt-3">
                          <div className="mb-2 text-sm font-medium text-stone-900">{t("composer.sizeMenu.countLabel")}</div>
                          <div className="grid grid-cols-4 gap-2 sm:grid-cols-5">
                            {countOptions.map((option) => {
                              const active = imageCount === option;
                              return (
                                <button
                                  key={option}
                                  type="button"
                                  className={cn(
                                    "h-9 cursor-pointer rounded-full border border-stone-200 bg-white text-sm text-stone-800 transition hover:border-stone-300 hover:bg-stone-50",
                                    active && "border-stone-950 bg-white font-medium text-stone-950",
                                  )}
                                  onClick={() => onImageCountChange(option)}
                                >
                                  {t("composer.sizeMenu.imageUnit", { count: Number(option) })}
                                </button>
                              );
                            })}
                            <Input
                              type="number"
                              inputMode="numeric"
                              min="1"
                              max="100"
                              step="1"
                              value={imageCount}
                              onChange={(event) => onImageCountChange(event.target.value)}
                              className="h-9 rounded-full border-stone-200 bg-white px-3 text-center text-sm font-medium text-stone-800 shadow-none focus-visible:ring-0"
                            />
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </div>

                </div>

                <button
                  type="button"
                  onClick={() => void onSubmit()}
                  disabled={!prompt.trim()}
                  className="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-stone-950 text-white transition hover:bg-stone-800 disabled:cursor-not-allowed disabled:bg-stone-300 sm:size-11"
                  aria-label={referenceImages.length > 0 ? t("composer.actions.editImage") : t("composer.actions.generateImage")}
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
