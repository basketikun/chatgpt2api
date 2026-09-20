"use client";

import { useEffect, useState } from "react";
import { ChevronDown, FileArchive, FileText, KeyRound, ListChecks, type LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import webConfig from "@/constants/common-env";
import { useI18n } from "@/lib/i18n";
import { getStoredAuthSession } from "@/store/auth";

type ParamRow = [string, string, string];

type ApiDoc = {
  title: string;
  method: string;
  path: string;
  icon: LucideIcon;
  input: ParamRow[];
  output: ParamRow[];
  example: (baseUrl: string, key: string) => string;
};

function getApiDocs(locale: string): ApiDoc[] {
  const isZh = locale === "zh";
  const isFa = locale === "fa";
  const isAr = locale === "ar";

  const t = {
    models: {
      title: isFa ? "لیست مدل‌ها" : isAr ? "قائمة النماذج" : isZh ? "模型列表" : "Models List",
      inAuth: isFa ? "کلید احراز هویت با فرمت Bearer <auth-key>." : isAr ? "مفتاح المصادقة بتنسيق Bearer <auth-key>." : isZh ? "Bearer <auth-key>。" : "Bearer <auth-key>.",
      outData: isFa ? "لیست مدل‌ها شامل id، object، created و owned_by." : isAr ? "قائمة النماذج تتضمن id و object و created و owned_by." : isZh ? "模型列表，包含 id、object、created、owned_by。" : "Model list containing id, object, created, owned_by.",
    },
    chat: {
      title: isFa ? "تکمیل چت (Chat Completions)" : isAr ? "إكمال المحادثة (Chat Completions)" : isZh ? "聊天补全" : "Chat Completions",
      inModel: isFa ? "نام مدل، مانند gpt-5-mini، برای تولید تصویر نیز قابل استفاده است." : isAr ? "اسم النموذج، مثل gpt-5-mini، صالح أيضًا لتوليد الصور." : isZh ? "模型名，例如 gpt-5-mini，也可用于图片兼容场景。" : "Model name, e.g. gpt-5-mini, also usable for image compatibility.",
      inMessages: isFa ? "آرایه پیام‌های استاندارد سازگار با OpenAI." : isAr ? "مصفوفة رسائل متوافقة مع OpenAI." : isZh ? "OpenAI 兼容消息数组。" : "OpenAI-compatible messages array.",
      inStream: isFa ? "اختیاری، ارسال پاسخ به صورت استریم (جریان داده)." : isAr ? "اختياري، هل يتم التدفق (stream)." : isZh ? "可选，是否流式返回。" : "Optional, whether to stream responses.",
      inN: isFa ? "اختیاری، در سناریوی تصویر به عنوان تعداد تولید تفسیر می‌شود." : isAr ? "اختياري، يفسر كعدد الصور في سيناريو توليد الصور." : isZh ? "可选，图片兼容场景会解析为生成数量。" : "Optional, parsed as image count in image-compatible scenarios.",
      outId: isFa ? "شناسه پاسخ." : isAr ? "معرف الاستجابة." : isZh ? "响应 ID。" : "Response ID.",
      outChoices: isFa ? "آرایه انتخاب‌های سازگار با OpenAI." : isAr ? "خيارات متوافقة مع OpenAI." : isZh ? "OpenAI 兼容 choices。" : "OpenAI-compatible choices.",
      outUsage: isFa ? "اختیاری، اطلاعات توکن‌های مصرف‌شده." : isAr ? "اختياري، تفاصيل استهلاك الرموز." : isZh ? "可选，token 使用信息。" : "Optional, token usage stats.",
      exampleMsg: isFa ? "سلام" : isAr ? "مرحبا" : isZh ? "你好" : "Hello",
    },
    responses: {
      title: "Responses",
      inModel: isFa ? "نام مدل." : isAr ? "اسم النموذج." : isZh ? "模型名。" : "Model name.",
      inInput: isFa ? "ورودی کاربر، برای تولید تصویر پرامپت از آن استخراج می‌شود." : isAr ? "مدخلات المستخدم، يتم استخراج الوصف لتوليد الصور." : isZh ? "用户输入，图片生成会从中解析提示词。" : "User input, prompts extracted for image generation.",
      inTools: isFa ? "اختیاری، تعریف ابزارهای Responses." : isAr ? "اختياري، تعريف أدوات Responses." : isZh ? "可选，Responses 工具定义。" : "Optional, Responses tool definitions.",
      inStream: isFa ? "اختیاری، دریافت استریم." : isAr ? "اختياري، التدفق." : isZh ? "可选，是否流式返回。" : "Optional, whether to stream responses.",
      outId: isFa ? "شناسه پاسخ." : isAr ? "معرف الاستجابة." : isZh ? "响应 ID。" : "Response ID.",
      outOutput: isFa ? "خروجی سازگار با فرمت Responses." : isAr ? "مخرجات متوافقة مع Responses." : isZh ? "Responses 兼容输出。" : "Responses-compatible output.",
      outStatus: isFa ? "وضعیت پاسخ." : isAr ? "حالة الاستجابة." : isZh ? "响应状态。" : "Response status.",
      examplePrompt: isFa ? "یک تصویر از شهر آینده بساز" : isAr ? "أنشئ صورة لمدينة مستقبلية" : isZh ? "生成一张未来城市图片" : "Generate a picture of a futuristic city",
    },
    search: {
      title: isFa ? "جستجوی وب" : isAr ? "البحث في الويب" : isZh ? "搜索" : "Search",
      inPrompt: isFa ? "سوال جستجو یا دستور وب‌گردی." : isAr ? "سؤال البحث أو أمر الاسترجاع." : isZh ? "搜索问题或检索指令。" : "Search query or instruction.",
      outAnswer: isFa ? "پاسخ حاصل از جستجو؛ ساختار فیلدها طبق نتیجه بازگشتی است." : isAr ? "الإجابة المسترجعة من البحث؛ تعتمد الحقول على النتيجة." : isZh ? "搜索后的回答内容，具体字段以返回结果为准。" : "Answer content after searching.",
      outSources: isFa ? "اختیاری، منابع و پیوندهای استناد شده." : isAr ? "اختياري، مصادر المراجع والروابط." : isZh ? "可选，搜索引用来源。" : "Optional, search citation sources.",
      outEmail: isFa ? "ایمیل اکانت استفاده‌شده در این درخواست." : isAr ? "البريد الإلكتروني للحساب المستخدم." : isZh ? "本次使用的账号邮箱。" : "Account email used for this request.",
      examplePrompt: isFa ? "روش‌های استفاده از chatgpt2api" : isAr ? "أحدث طرق استخدام chatgpt2api" : isZh ? "搜索 chatgpt2api 最新使用方式" : "Search latest usage of chatgpt2api",
    },
    images: {
      title: isFa ? "تولید تصویر" : isAr ? "توليد الصور" : isZh ? "图片生成" : "Image Generation",
      inPrompt: isFa ? "پرامپت و توصیف تصویر مورد نظر." : isAr ? "وصف ومطالبة توليد الصورة." : isZh ? "图片生成提示词。" : "Image generation prompt.",
      inModel: isFa ? "اختیاری، پیش‌فرض gpt-image-2." : isAr ? "اختياري، الافتراضي gpt-image-2." : isZh ? "可选，默认 gpt-image-2。" : "Optional, default gpt-image-2.",
      inN: isFa ? "اختیاری، تعداد تصاویر، در حال حاضر ۱ تا ۴." : isAr ? "اختياري، عدد الصور، محدد حالياً بين 1-4." : isZh ? "可选，生成数量，当前限制 1-4。" : "Optional, image count, limited to 1-4.",
      inSize: isFa ? "اختیاری، ابعاد تصویر." : isAr ? "اختياري، أبعاد الصورة." : isZh ? "可选，图片尺寸。" : "Optional, image size.",
      inQuality: isFa ? "اختیاری، کیفیت تصویر، پیش‌فرض auto." : isAr ? "اختياري، الجودة، الافتراضي auto." : isZh ? "可选，默认 auto。" : "Optional, default auto.",
      inFormat: isFa ? "اختیاری، فرمت پاسخ، پیش‌فرض b64_json." : isAr ? "اختياري، صيغة الاستجابة، الافتراضي b64_json." : isZh ? "可选，默认 b64_json。" : "Optional, default b64_json.",
      outData: isFa ? "لیست نتایج تصویر." : isAr ? "قائمة نتائج الصور." : isZh ? "图片结果列表。" : "List of image results.",
      outB64: isFa ? "محتوای تصویر به فرمت base64." : isAr ? "محتوى الصورة بصيغة base64." : isZh ? "base64 图片内容。" : "base64 image content.",
      outUrl: isFa ? "آدرس URL تصویر در صورت پیکربندی مناسب." : isAr ? "رابط الصورة في بعض الإعدادات." : isZh ? "部分配置下返回图片 URL。" : "Image URL under certain configurations.",
      examplePrompt: isFa ? "پوستر مینیمال محصول" : isAr ? "ملصق منتج بسيط" : isZh ? "一张极简产品海报" : "A minimalist product poster",
    },
    edits: {
      title: isFa ? "ویرایش تصویر" : isAr ? "تعديل الصور" : isZh ? "图片编辑" : "Image Editing",
      inImage: isFa ? "تصویر مرجع، پشتیبانی از آپلود چندبخشی (multipart) یا لینک JSON." : isAr ? "الصورة المرجعية، يدعم رفع multipart أو رابط JSON." : isZh ? "参考图，支持 multipart 上传，也支持 JSON 图片链接。" : "Reference image, supports multipart upload or JSON image URL.",
      inPrompt: isFa ? "پرامپت ویرایش تصویر." : isAr ? "وصف التعديل المطلوب." : isZh ? "编辑提示词。" : "Edit prompt.",
      examplePrompt: isFa ? "تبدیل به نمای شب سایبرپانک" : isAr ? "تغيير إلى مشهد ليلي سايبربانك" : isZh ? "改成赛博朋克夜景" : "Change to cyberpunk night scene",
    },
    ppt: {
      title: isFa ? "ایجاد تسک ساخت اسلاید PPT" : isAr ? "إنشاء مهمة عرض تقديمي PPT" : isZh ? "创建 PPT 任务" : "Create PPT Task",
      inPrompt: isFa ? "توصیف نیازمندی‌های PPT شامل موضوع، تعداد اسلاید، سبک و ساختار." : isAr ? "وصف متطلبات PPT، يوصى بملء الموضوع وعدد الشرائح والأسلوب." : isZh ? "PPT 需求描述，可为空但建议填写完整主题、页数、风格和内容结构。" : "PPT requirements description; theme, slides, and style recommended.",
      inImages: isFa ? "اختیاری، آرایه data URL/base64 تصاویر به عنوان متریال مرجع PPT." : isAr ? "اختياري، مصفوفة صور base64 كمراجع للـ PPT." : isZh ? "可选，图片 data URL/base64，用作 PPT 参考素材。" : "Optional, image data URLs/base64 as reference assets.",
      inClientTaskId: isFa ? "اختیاری، شناسه یکتا از سمت کلاینت؛ ارسال شناسه تکراری همان تسک را برمی‌گرداند." : isAr ? "اختياري، معرف المهمة من العميل لمنع التكرار." : isZh ? "可选，客户端幂等任务 ID；重复提交同 ID 会返回已有任务。" : "Optional, idempotent client task ID.",
      outId: isFa ? "شناسه تسک برای استعلام وضعیت." : isAr ? "معرف المهمة للاستعلام عن الحالة." : isZh ? "任务 ID，用于轮询状态。" : "Task ID for polling status.",
      outStatus: isFa ? "وضعیت تسک (queued | running | success | error)." : isAr ? "حالة المهمة." : isZh ? "任务状态。" : "Task status.",
      outKind: isFa ? "نوع تسک (ppt)." : isAr ? "نوع المهمة." : isZh ? "任务类型。" : "Task kind.",
      outTimestamps: isFa ? "زمان ایجاد و به‌روزرسانی تسک." : isAr ? "وقت إنشاء المهمة وتحديثها." : isZh ? "任务创建和更新时间。" : "Task creation and update timestamps.",
      examplePrompt: isFa ? "ساخت گزارش تجاری فصلی در کمتر از ۸ اسلاید" : isAr ? "إنشاء عرض تقرير أعمال فصلي في أقل من 8 شرائح" : isZh ? "制作一份 8 页以内的季度业务汇报 PPT" : "Create a quarterly business report PPT under 8 pages",
    },
    psd: {
      title: isFa ? "ایجاد تسک تفکیک لایه‌های PSD" : isAr ? "إنشاء مهمة تفكيك PSD" : isZh ? "创建 PSD 任务" : "Create PSD Task",
      inPrompt: isFa ? "الزامات تفکیک و ترکیب لایه‌ها، حفظ پس‌زمینه و بسته zip متریال‌ها." : isAr ? "متطلبات تفكيك وتجميع PSD وحفظ الطبقات والخلفية." : isZh ? "PSD 拆分与合成要求，例如保留图层、位置、背景和素材 zip。" : "PSD layer separation and composition requirements.",
      inImages: isFa ? "الزامی، حداقل یک تصویر data URL/base64 به عنوان تصویر مرجع تفکیک." : isAr ? "مطلوب، صورة واحدة على الأقل بصيغة base64." : isZh ? "必填，至少一张图片 data URL/base64，作为 PSD 拆分源图。" : "Required, at least one image data URL/base64 as source.",
      outError: isFa ? "در صورت شکست پیام خطا را برمی‌گرداند." : isAr ? "رسالة الخطأ عند الفشل." : isZh ? "失败时返回错误信息。" : "Error message upon failure.",
      examplePrompt: isFa ? "تفکیک المان‌های پوستر به لایه‌های مجزا و ایجاد فایل PSD قابل ویرایش" : isAr ? "تفكيك عناصر الملصق إلى طبقات PSD قابلة للتعديل" : isZh ? "按原图位置拆分海报元素并合成可编辑 PSD" : "Split poster elements and synthesize editable PSD",
    },
    tasks: {
      title: isFa ? "استعلام وضعیت تسک‌ها" : isAr ? "الاستعلام عن حالة المهام" : isZh ? "任务状态查询" : "Task Status Query",
      inIds: isFa ? "اختیاری، شناسه‌های تسک با ویرگول جدا شده؛ در صورت خالی بودن تمام تسک‌ها بازگردانده می‌شوند." : isAr ? "اختياري، معرفات المهام مفصولة بفواصل." : isZh ? "可选，逗号分隔任务 ID；不传则返回当前用户全部可编辑文件任务。" : "Optional, comma-separated task IDs.",
      outItems: isFa ? "لیست تسک‌ها. در تسک‌های موفق آدرس‌های primary_url و zip_url در فیلد result قرار دارند." : isAr ? "قائمة المهام، تتضمن primary_url و zip_url عند النجاح." : isZh ? "任务列表。成功任务的 result 内包含 primary_url 和 zip_url。" : "Task list. Successful tasks contain primary_url and zip_url.",
      outMissing: isFa ? "شناسه‌هایی که یافت نشدند." : isAr ? "معرفات المهام غير الموجودة." : isZh ? "查询指定 ids 时，返回未找到的任务 ID。" : "Missing task IDs when querying specific ids.",
      outPrimary: isFa ? "آدرس دانلود فایل اصلی." : isAr ? "رابط تنزيل الملف الأساسي." : isZh ? "主文件下载地址。" : "Main file download URL.",
      outZip: isFa ? "آدرس دانلود فایل zip متریال‌ها." : isAr ? "رابط تنزيل ملف zip للملحقات." : isZh ? "素材 zip 下载地址。" : "Asset zip download URL.",
    },
    files: {
      title: isFa ? "دانلود فایل نتیجه" : isAr ? "تنزيل ملف النتيجة" : isZh ? "结果文件下载" : "Result File Download",
      inPath: isFa ? "از result.primary_url یا result.zip_url دریافت می‌شود و نیاز به ترکیب دستی ندارد." : isAr ? "يتم الحصول عليه من نتيجة المهمة primary_url أو zip_url." : isZh ? "由任务 result.primary_url 或 result.zip_url 返回，通常不需要手动拼接。" : "Returned by result.primary_url or result.zip_url.",
      outBinary: isFa ? "بازگرداندن فایل pptx/psd/zip به صورت بایت‌های باینری." : isAr ? "إرجاع تدفق ملف pptx/psd/zip الثنائي." : isZh ? "返回 pptx/psd/zip 文件流。" : "Returns pptx/psd/zip file stream.",
    },
  };

  return [
    {
      title: t.models.title,
      method: "GET",
      path: "/v1/models",
      icon: ListChecks,
      input: [["Authorization", "header", t.models.inAuth]],
      output: [["data", "array", t.models.outData]],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/models \\
  -H "Authorization: Bearer ${key}"`,
    },
    {
      title: t.chat.title,
      method: "POST",
      path: "/v1/chat/completions",
      icon: FileText,
      input: [
        ["model", "string", t.chat.inModel],
        ["messages", "array", t.chat.inMessages],
        ["stream", "boolean", t.chat.inStream],
        ["n", "number", t.chat.inN],
      ],
      output: [
        ["id", "string", t.chat.outId],
        ["choices", "array", t.chat.outChoices],
        ["usage", "object", t.chat.outUsage],
      ],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{"model":"gpt-5-mini","messages":[{"role":"user","content":"${t.chat.exampleMsg}"}]}'`,
    },
    {
      title: t.responses.title,
      method: "POST",
      path: "/v1/responses",
      icon: FileText,
      input: [
        ["model", "string", t.responses.inModel],
        ["input", "string | array | object", t.responses.inInput],
        ["tools", "array", t.responses.inTools],
        ["stream", "boolean", t.responses.inStream],
      ],
      output: [
        ["id", "string", t.responses.outId],
        ["output", "array", t.responses.outOutput],
        ["status", "string", t.responses.outStatus],
      ],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/responses \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{"model":"gpt-5-mini","input":"${t.responses.examplePrompt}"}'`,
    },
    {
      title: t.search.title,
      method: "POST",
      path: "/v1/search",
      icon: ListChecks,
      input: [["prompt", "string", t.search.inPrompt]],
      output: [
        ["answer", "string", t.search.outAnswer],
        ["sources", "array", t.search.outSources],
        ["_account_email", "string", t.search.outEmail],
      ],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/search \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{"prompt":"${t.search.examplePrompt}"}'`,
    },
    {
      title: t.images.title,
      method: "POST",
      path: "/v1/images/generations",
      icon: FileArchive,
      input: [
        ["prompt", "string", t.images.inPrompt],
        ["model", "string", t.images.inModel],
        ["n", "number", t.images.inN],
        ["size", "string", t.images.inSize],
        ["quality", "string", t.images.inQuality],
        ["response_format", "string", t.images.inFormat],
      ],
      output: [
        ["data", "array", t.images.outData],
        ["data[].b64_json", "string", t.images.outB64],
        ["data[].url", "string", t.images.outUrl],
      ],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/images/generations \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{"model":"gpt-image-2","prompt":"${t.images.examplePrompt}","n":1}'`,
    },
    {
      title: t.edits.title,
      method: "POST",
      path: "/v1/images/edits",
      icon: FileArchive,
      input: [
        ["image", "file | file[] | URL", t.edits.inImage],
        ["prompt", "string", t.edits.inPrompt],
        ["model", "string", t.images.inModel],
        ["n", "number", t.images.inN],
        ["size", "string", t.images.inSize],
        ["quality", "string", t.images.inQuality],
      ],
      output: [
        ["data", "array", t.images.outData],
        ["data[].b64_json", "string", t.images.outB64],
        ["data[].url", "string", t.images.outUrl],
      ],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/images/edits \\
  -H "Authorization: Bearer ${key}" \\
  -F "model=gpt-image-2" \\
  -F "prompt=${t.edits.examplePrompt}" \\
  -F "image=@./input.png"`,
    },
    {
      title: t.ppt.title,
      method: "POST",
      path: "/v1/ppt/generations",
      icon: FileText,
      input: [
        ["prompt", "string", t.ppt.inPrompt],
        ["base64_images", "string[]", t.ppt.inImages],
        ["client_task_id", "string", t.ppt.inClientTaskId],
      ],
      output: [
        ["id / taskId", "string", t.ppt.outId],
        ["status", "queued | running | success | error", t.ppt.outStatus],
        ["kind", "ppt", t.ppt.outKind],
        ["created_at / updated_at", "string", t.ppt.outTimestamps],
      ],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/ppt/generations \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{"prompt":"${t.ppt.examplePrompt}","base64_images":[]}'`,
    },
    {
      title: t.psd.title,
      method: "POST",
      path: "/v1/psd/generations",
      icon: FileArchive,
      input: [
        ["prompt", "string", t.psd.inPrompt],
        ["base64_images", "string[]", t.psd.inImages],
        ["client_task_id", "string", t.ppt.inClientTaskId],
      ],
      output: [
        ["id / taskId", "string", t.ppt.outId],
        ["status", "queued | running | success | error", t.ppt.outStatus],
        ["kind", "psd", t.ppt.outKind],
        ["error", "string", t.psd.outError],
      ],
      example: (baseUrl: string, key: string) => `curl ${baseUrl}/psd/generations \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{"prompt":"${t.psd.examplePrompt}","base64_images":["data:image/png;base64,..."]}'`,
    },
    {
      title: t.tasks.title,
      method: "GET",
      path: "/v1/editable-file-tasks?ids={taskId1,taskId2}",
      icon: ListChecks,
      input: [["ids", "string", t.tasks.inIds]],
      output: [
        ["items", "array", t.tasks.outItems],
        ["missing_ids", "string[]", t.tasks.outMissing],
        ["result.primary_url", "string", t.tasks.outPrimary],
        ["result.zip_url", "string", t.tasks.outZip],
      ],
      example: (baseUrl: string, key: string) => `curl "${baseUrl}/editable-file-tasks?ids=<task_id>" \\
  -H "Authorization: Bearer ${key}"`,
    },
    {
      title: t.files.title,
      method: "GET",
      path: "/files/{file_path}",
      icon: FileArchive,
      input: [["file_path", "string", t.files.inPath]],
      output: [["binary", "file", t.files.outBinary]],
      example: (baseUrl: string, _key: string) => `curl ${baseUrl.replace(/\/v1$/, "")}/files/<file_path> -o result.zip`,
    },
  ];
}

const usableModels = ["gpt-image-2", "codex-gpt-image-2", "auto", "gpt-5", "gpt-5-1", "gpt-5-2", "gpt-5-3", "gpt-5-3-mini", "gpt-5-mini"];

function ParamTable({ rows, thParam, thType, thDesc }: { rows: ParamRow[]; thParam: string; thType: string; thDesc: string }) {
  return (
    <div className="overflow-hidden rounded-lg border border-stone-200">
      <table className="w-full text-start text-xs">
        <thead className="bg-stone-50 text-stone-500">
          <tr>
            <th className="px-3 py-2 font-medium">{thParam}</th>
            <th className="px-3 py-2 font-medium">{thType}</th>
            <th className="px-3 py-2 font-medium">{thDesc}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-stone-100 bg-white">
          {rows.map(([name, type, desc]) => (
            <tr key={name}>
              <td className="px-3 py-2 font-mono text-stone-800">{name}</td>
              <td className="px-3 py-2 font-mono text-stone-500">{type}</td>
              <td className="px-3 py-2 text-stone-600">{desc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ApiDocsCard() {
  const { t, locale } = useI18n();
  const [authKey, setAuthKey] = useState("");
  const serviceBaseUrl = webConfig.apiUrl.replace(/\/$/, "") || (typeof window !== "undefined" ? window.location.origin : "");
  const openAIBaseUrl = `${serviceBaseUrl}/v1`;
  const displayKey = authKey || t.apiDocs.displayKeyPlaceholder;
  const docs = getApiDocs(locale);

  useEffect(() => {
    let active = true;
    void getStoredAuthSession().then((session) => {
      if (active) setAuthKey(session?.key || "");
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-5 p-6">
        <div>
          <div className="flex items-center gap-2 text-base font-semibold text-stone-900">
            <KeyRound className="size-5 text-stone-500" />
            {t.apiDocs.title}
          </div>
          <p className="mt-1 text-xs leading-6 text-stone-500">
            {t.apiDocs.desc}
          </p>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1 rounded-xl border border-stone-200 bg-white px-3 py-2">
            <div className="text-xs text-stone-500">{t.apiDocs.serviceUrl}</div>
            <div className="break-all font-mono text-xs text-stone-800">{serviceBaseUrl}</div>
          </div>
          <div className="space-y-1 rounded-xl border border-stone-200 bg-white px-3 py-2">
            <div className="text-xs text-stone-500">Base URL (OpenAI)</div>
            <div className="break-all font-mono text-xs text-stone-800">{openAIBaseUrl}</div>
          </div>
          <div className="space-y-1 rounded-xl border border-stone-200 bg-white px-3 py-2">
            <div className="text-xs text-stone-500">API Key</div>
            <div className="break-all font-mono text-xs text-stone-800">{displayKey}</div>
          </div>
          <div className="space-y-1 rounded-xl border border-stone-200 bg-white px-3 py-2">
            <div className="text-xs text-stone-500">{t.apiDocs.headers}</div>
            <div className="break-all font-mono text-xs text-stone-800">Authorization: Bearer {displayKey}</div>
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-xs font-medium text-stone-600">{t.apiDocs.popularModels}</div>
          <div className="flex flex-wrap gap-2">
            {usableModels.map((model) => (
              <span key={model} className="rounded-md border border-stone-200 bg-white px-2 py-1 font-mono text-xs text-stone-700">{model}</span>
            ))}
          </div>
        </div>

        <div className="space-y-3">
          {docs.map((item) => {
            const Icon = item.icon;
            return (
              <details key={item.path} className="group rounded-xl border border-stone-200 bg-white px-4 py-3">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
                  <span className="flex min-w-0 items-center gap-3">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-stone-100 text-stone-600">
                      <Icon className="size-4" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-stone-900">{item.title}</span>
                      <span className="mt-1 block truncate font-mono text-xs text-stone-500">{item.method} {item.path}</span>
                    </span>
                  </span>
                  <ChevronDown className="size-4 shrink-0 text-stone-400 transition group-open:rotate-180" />
                </summary>

                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  <div className="space-y-2">
                    <h3 className="text-xs font-semibold text-stone-700">{t.apiDocs.inputParams}</h3>
                    <ParamTable rows={item.input} thParam={t.apiDocs.thParam} thType={t.apiDocs.thType} thDesc={t.apiDocs.thDesc} />
                  </div>
                  <div className="space-y-2">
                    <h3 className="text-xs font-semibold text-stone-700">{t.apiDocs.outputParams}</h3>
                    <ParamTable rows={item.output} thParam={t.apiDocs.thParam} thType={t.apiDocs.thType} thDesc={t.apiDocs.thDesc} />
                  </div>
                  <div className="space-y-2 lg:col-span-2">
                    <h3 className="text-xs font-semibold text-stone-700">{t.apiDocs.callExample}</h3>
                    <pre className="overflow-auto whitespace-pre-wrap break-all rounded-xl bg-stone-950 px-3 py-3 text-xs leading-5 text-stone-100" dir="ltr">{item.example(openAIBaseUrl, displayKey)}</pre>
                  </div>
                </div>
              </details>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
