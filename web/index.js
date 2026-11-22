import Alpine from "alpinejs";
import dayjs from "dayjs";
import { EventSourceParserStream } from "eventsource-parser/stream";

/* ---------- 请求与登录态 ---------- */
const SESSION_KEY = "chatgpt2api_session";

const session = {
  get: () => JSON.parse(localStorage.getItem(SESSION_KEY)),
  set: (value) => localStorage.setItem(SESSION_KEY, JSON.stringify(value)),
  clear: () => localStorage.removeItem(SESSION_KEY),
};

function errorText(value) {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return "";
  return typeof value.message === "string" ? value.message : errorText(value.error);
}

async function send(path, { method = "GET", body, headers = {}, key = session.get()?.key, signal } = {}) {
  const json = body !== undefined && !(body instanceof FormData);
  const response = await fetch(path, {
    method,
    signal,
    headers: { ...(key ? { Authorization: `Bearer ${key}` } : {}), ...(json ? { "Content-Type": "application/json" } : {}), ...headers },
    body: json ? JSON.stringify(body) : body,
  });
  if (response.status === 401 && path !== "/auth/login") {
    session.clear();
    location.replace("/login");
    return new Promise(() => {});
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(errorText(payload.detail) || errorText(payload.error) || payload.message || `请求失败（${response.status}）`);
  }
  return response;
}

/** 发送请求并解析 JSON 响应；options 支持 method / body / headers / key / signal。 */
async function api(path, options) {
  return (await send(path, options)).json();
}

/** 获取二进制响应，用于音频与压缩包下载。 */
api.blob = async (path, options) => (await send(path, options)).blob();

/** 以 SSE 方式读取流式响应，逐条回调解析后的事件。 */
api.stream = async (path, body, onEvent) => {
  const response = await send(path, { method: "POST", body });
  const reader = response.body.pipeThrough(new TextDecoderStream()).pipeThrough(new EventSourceParserStream()).getReader();
  while (true) {
    const { done, value } = await reader.read();
    if (done || value.data === "[DONE]") return;
    const event = JSON.parse(value.data);
    if (event.error) throw new Error(errorText(event.error));
    onEvent(event);
  }
};

/* ---------- 通用函数与组件 ---------- */
/* ---------- 格式化 ---------- */
const fmtTime = (value) => value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "—";
const fmtShort = (value) => value ? dayjs(value).format("MM-DD HH:mm") : "—";
const fmtNumber = (value) => new Intl.NumberFormat("zh-CN").format(value);

function fmtBytes(bytes) {
  const index = bytes === 0 ? 0 : Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), 4);
  return `${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 }).format(bytes / 1024 ** index)} ${["B", "KB", "MB", "GB", "TB"][index]}`;
}

function fmtDuration(ms) {
  if (typeof ms !== "number") return "—";
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.floor(ms / 60000)}m ${Math.floor(ms % 60000 / 1000)}s`;
}

/* ---------- 文件与下载 ---------- */
const readDataUrl = (file) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(reader.result);
  reader.onerror = () => reject(reader.error);
  reader.readAsDataURL(file);
});

async function urlToFile(url, name) {
  const blob = await (await fetch(url)).blob();
  return new File([blob], name, { type: blob.type });
}

function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

/** 生成唯一 ID。crypto.randomUUID 只在安全上下文（HTTPS、localhost）可用，HTTP 访问时降级。 */
function uid() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  if (globalThis.crypto?.getRandomValues) crypto.getRandomValues(bytes);
  else for (let index = 0; index < bytes.length; index++) bytes[index] = Math.floor(Math.random() * 256);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** 复制文本。navigator.clipboard 同样只在安全上下文可用，HTTP 访问时退回 execCommand。 */
async function writeClipboard(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // 权限被拒或页面不是安全上下文时退回下面的兜底方案
    }
  }
  const area = Object.assign(document.createElement("textarea"), { value: text });
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.select();
  const copied = document.execCommand("copy");
  area.remove();
  if (!copied) throw new Error("当前浏览器不支持复制，请手动选择文本复制");
}

/* ---------- 反馈 ---------- */
/** 只在失败、需要等待或需要用户处理时调用，成功状态由界面变化体现。 */
function toast(text, type = "error", icon = "") {
  const store = Alpine.store("toast");
  const item = { id: uid(), text, type, icon };
  store.items.push(item);
  setTimeout(() => store.items.splice(store.items.indexOf(item), 1), type === "error" ? 6000 : 4000);
}

/** 确认弹窗，返回用户是否确认。 */
function confirmDialog({ title, text = "", ok = "确认", danger = true }) {
  return new Promise((resolve) => Object.assign(Alpine.store("confirm"), { open: true, title, text, ok, danger, resolve }));
}

/** 打开全屏图片查看器，images 为 { src, meta } 数组。 */
function lightbox(images, index) {
  Object.assign(Alpine.store("lightbox"), { images, index, zoom: false, open: true });
}

/** 复制文本，并让触发元素短暂高亮作为反馈。 */
async function copyText(text, el) {
  await writeClipboard(text);
  el.animate([{ background: "var(--color-success-soft)" }, { background: "transparent" }], { duration: 800 });
}

let markdownLib;
/** Markdown 渲染：按需加载 marked 与 DOMPurify。 */
async function markdown(text) {
  markdownLib ??= Promise.all([import("marked"), import("dompurify")]);
  const [{ marked }, { default: purify }] = await markdownLib;
  return purify.sanitize(marked.parse(text, { breaks: true }));
}

/* ---------- Web Components ---------- */
customElements.define("ui-icon", class extends HTMLElement {
  static observedAttributes = ["name"];
  attributeChangedCallback() {
    this.innerHTML = `<svg aria-hidden="true"><use href="#${this.getAttribute("name")}"></use></svg>`;
  }
});

/** 把浮层定位到触发按钮下方，空间不足时改为上方。 */
function anchor(button, panel, height) {
  const rect = button.getBoundingClientRect();
  const above = rect.bottom + height > innerHeight && rect.top > height;
  Object.assign(panel.style, { minWidth: `${rect.width}px`, left: `${Math.min(rect.left, innerWidth - panel.offsetWidth - 8)}px`, top: above ? "auto" : `${rect.bottom + 4}px`, bottom: above ? `${innerHeight - rect.top + 4}px` : "auto" });
}

/** 模型标签：显示 GPT 图标与模型名称，点击复制。 */
customElements.define("ui-model", class extends HTMLElement {
  static observedAttributes = ["name"];
  attributeChangedCallback() {
    const name = this.getAttribute("name");
    this.innerHTML = `<button type="button" class="model-chip" title="点击复制"><ui-icon name="openai" class="icon-sm"></ui-icon><span class="truncate"></span></button>`;
    this.querySelector("span").textContent = name;
    this.firstChild.onclick = () => writeClipboard(name).then(() => toast(`已复制 ${name}`, "success", "openai"), (error) => toast(error.message));
  }
});

/**
 * 下拉选择：替代浏览器原生选择面板。用法 <ui-select x-model="value"><option value="a">A</option></ui-select>，
 * 选项可由 x-for 生成；支持 placeholder、disabled、variant="ghost"、block 类，以及 multiple（值为数组，可多选）。
 */
customElements.define("ui-select", class extends HTMLElement {
  static observedAttributes = ["disabled", "placeholder"];
  #value = "";

  connectedCallback() {
    if (this.button) return;
    this.button = Object.assign(document.createElement("button"), { type: "button" });
    this.label = document.createElement("span");
    this.label.className = "truncate";
    this.button.append(this.label, Object.assign(document.createElement("ui-icon"), { className: "icon-sm text-subtle" }));
    this.button.lastChild.setAttribute("name", "chevron-down");
    this.panel = Object.assign(document.createElement("div"), { className: "dropdown-popover", popover: "auto" });
    this.append(this.button, this.panel);
    this.button.addEventListener("click", () => this.panel.togglePopover() && anchor(this.button, this.panel, 320));
    new MutationObserver((records) => records.some((record) => !this.button.contains(record.target) && !this.panel.contains(record.target)) && this.render()).observe(this, { childList: true, subtree: true, characterData: true, attributeFilter: ["value"] });
    this.render();
  }

  attributeChangedCallback() {
    if (this.button) this.render();
  }

  get value() {
    return this.#value;
  }

  set value(value) {
    this.#value = value;
    if (this.button) this.render();
  }

  get options() {
    return [...this.querySelectorAll(":scope > option")];
  }

  icon() {
    const icon = Object.assign(document.createElement("ui-icon"), { className: "icon-sm" });
    icon.setAttribute("name", this.getAttribute("icon"));
    return icon;
  }

  render() {
    const multiple = this.hasAttribute("multiple");
    const values = Array.isArray(this.#value) ? this.#value : [];
    const selected = (option) => multiple ? values.includes(option.value) : option.value === String(this.#value);
    const current = this.options.find(selected);
    this.label.textContent = multiple ? this.options.filter(selected).map((option) => option.textContent).join(" · ") || this.getAttribute("placeholder") : current ? current.textContent : this.getAttribute("placeholder");
    if (current && this.hasAttribute("icon")) this.label.prepend(this.icon());
    this.label.classList.toggle("text-subtle", !current);
    this.button.disabled = this.hasAttribute("disabled");
    this.panel.replaceChildren(...this.options.map((option) => {
      const item = Object.assign(document.createElement("button"), { type: "button", className: "dropdown-option", textContent: option.textContent });
      if (this.hasAttribute("icon")) item.prepend(this.icon());
      if (multiple) {
        const check = Object.assign(document.createElement("ui-icon"), { className: "icon-sm dropdown-check" });
        check.setAttribute("name", "check");
        item.prepend(check);
      }
      item.setAttribute("aria-selected", selected(option));
      item.addEventListener("click", () => {
        if (multiple) {
          const next = values.includes(option.value) ? values.filter((value) => value !== option.value) : this.options.map((item) => item.value).filter((value) => value === option.value || values.includes(value));
          if (!next.length) return;
          this.#value = next;
        } else {
          this.#value = option.value;
          this.panel.hidePopover();
        }
        this.render();
        const detail = this.#value;
        this.dispatchEvent(new CustomEvent("input", { detail, bubbles: true }));
        this.dispatchEvent(new CustomEvent("change", { detail, bubbles: true }));
      });
      return item;
    }));
  }
});

/**
 * 分页：<ui-pager :page="page" :size="size" :total="total" @change="...">，
 * 居中显示总条数、当前页 / 总页数与每页数量，change 事件 detail 为 { page, size }。
 */
customElements.define("ui-pager", class extends HTMLElement {
  static observedAttributes = ["page", "size", "total", "sizes"];

  attributeChangedCallback() {
    const page = Number(this.getAttribute("page"));
    const size = Number(this.getAttribute("size"));
    const total = Number(this.getAttribute("total"));
    const pages = Math.max(1, Math.ceil(total / size));
    const sizes = (this.getAttribute("sizes") || "10,20,50,100").split(",");
    this.innerHTML = `
      <span>共 ${fmtNumber(total)} 条</span>
      <button type="button" class="btn btn-ghost btn-xs btn-square" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""} aria-label="上一页"><ui-icon name="chevron-left" class="icon-sm"></ui-icon></button>
      <span class="num">${page} / ${pages}</span>
      <button type="button" class="btn btn-ghost btn-xs btn-square" data-page="${page + 1}" ${page >= pages ? "disabled" : ""} aria-label="下一页"><ui-icon name="chevron-right" class="icon-sm"></ui-icon></button>
      <ui-select variant="ghost">${sizes.map((item) => `<option value="${item}">${item} 条/页</option>`).join("")}</ui-select>`;
    const select = this.querySelector("ui-select");
    select.value = String(size);
    select.addEventListener("change", (event) => {
      event.stopPropagation();
      this.emit(1, Number(event.detail));
    });
    this.querySelectorAll("[data-page]").forEach((button) => button.addEventListener("click", () => this.emit(Number(button.dataset.page), size)));
  }

  emit(page, size) {
    this.dispatchEvent(new CustomEvent("change", { detail: { page, size } }));
  }
});

/**
 * 日期选择：原生实现的日历浮层，周一开始。mode="range" 时 x-model 值为 [开始, 结束]，否则为单个日期（YYYY-MM-DD）；未选择时为空。
 */
customElements.define("ui-date", class extends HTMLElement {
  #value = "";

  connectedCallback() {
    if (this.button) return;
    this.range = this.getAttribute("mode") === "range";
    this.button = Object.assign(document.createElement("button"), { type: "button" });
    this.panel = Object.assign(document.createElement("div"), { className: "dropdown-popover date-panel", popover: "auto" });
    this.append(this.button, this.panel);
    this.button.addEventListener("click", (event) => event.target.closest("[data-clear]") ? this.pick(this.range ? [] : "") : this.panel.togglePopover() && anchor(this.button, this.panel, 320));
    this.panel.addEventListener("beforetoggle", (event) => {
      if (event.newState !== "open") return;
      const first = [this.#value].flat()[0];
      this.month = (first ? dayjs(first) : dayjs()).startOf("month");
      this.start = "";
      this.renderPanel();
    });
    this.panel.addEventListener("click", (event) => {
      const step = event.target.closest("[data-step]");
      const day = event.target.closest("[data-day]")?.dataset.day;
      if (step) {
        this.month = this.month.add(Number(step.dataset.step), "month");
        this.renderPanel();
      } else if (day && this.range && !this.start) {
        this.start = this.hover = day;
        this.renderPanel();
      } else if (day) {
        this.pick(this.range ? [this.start, day].sort() : day);
      }
    });
    this.panel.addEventListener("mouseover", (event) => {
      const day = event.target.closest("[data-day]")?.dataset.day;
      if (!this.start || !day || day === this.hover) return;
      this.hover = day;
      this.renderPanel();
    });
    this.render();
  }

  get value() {
    return this.#value;
  }

  set value(value) {
    this.#value = value;
    if (this.button) this.render();
  }

  pick(value) {
    this.#value = value;
    this.render();
    this.panel.hidePopover();
    this.dispatchEvent(new CustomEvent("input", { detail: value, bubbles: true }));
  }

  render() {
    const text = [this.#value].flat().join(" 至 ");
    this.button.innerHTML = `<ui-icon name="calendar-days" class="icon-sm text-subtle"></ui-icon><span class="grow truncate${text ? "" : " text-subtle"}">${text || this.getAttribute("placeholder")}</span>${text ? `<span class="date-clear" data-clear role="button" aria-label="清除日期"><ui-icon name="x" class="icon-sm"></ui-icon></span>` : ""}`;
  }

  renderPanel() {
    const picked = [this.#value].flat();
    const [from, to] = this.start ? [this.start, this.hover].sort() : [picked[0], picked.at(-1)];
    const today = dayjs().format("YYYY-MM-DD");
    const begin = this.month.subtract((this.month.day() + 6) % 7, "day");
    const days = Array.from({ length: 42 }, (_, index) => begin.add(index, "day")).map((day) => {
      const key = day.format("YYYY-MM-DD");
      const classes = [day.month() !== this.month.month() && "outside", key === today && "today", from && key >= from && key <= to && "in-range", (key === from || key === to) && "edge"].filter(Boolean).join(" ");
      return `<button type="button" class="date-day ${classes}" data-day="${key}">${day.date()}</button>`;
    });
    this.panel.innerHTML = `
      <div class="date-head">
        <button type="button" class="btn btn-ghost btn-xs btn-square" data-step="-1" aria-label="上个月"><ui-icon name="chevron-left" class="icon-sm"></ui-icon></button>
        <span class="num">${this.month.format("YYYY 年 M 月")}</span>
        <button type="button" class="btn btn-ghost btn-xs btn-square" data-step="1" aria-label="下个月"><ui-icon name="chevron-right" class="icon-sm"></ui-icon></button>
      </div>
      <div class="date-grid">${["一", "二", "三", "四", "五", "六", "日"].map((name) => `<span class="date-week">${name}</span>`).join("")}${days.join("")}</div>`;
  }
});

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/* ---------- 页面：login ---------- */
Alpine.data("login", () => ({
  key: "",
  visible: false,
  loading: false,
  error: "",

  async submit() {
    this.loading = true;
    try {
      const data = await api("/auth/login", { method: "POST", body: {}, key: this.key });
      session.set({ key: this.key, role: data.role, name: data.name });
      this.$go("/");
    } catch (error) {
      this.error = error.message;
    } finally {
      this.loading = false;
    }
  },
}));

/* ---------- 页面：overview ---------- */
Alpine.data("overview", () => {
  let chart;
  const timers = {};

  return {
    period: "24h",
    calls: null,
    system: null,
    callsError: "",
    systemError: "",
    loading: false,
    modelPage: 1,
    modelSize: 8,

    init() {
      this.poll("calls", 30000);
      this.poll("system", 5000);
      this.$watch("period", () => {
        chart?.destroy();
        chart = undefined;
        this.calls = null;
        this.modelPage = 1;
        this.load("calls");
      });
    },

    destroy() {
      Object.values(timers).forEach(clearTimeout);
      chart?.destroy();
    },

    poll(kind, interval) {
      const tick = async () => {
        if (!document.hidden) await this.load(kind);
        timers[kind] = setTimeout(tick, interval);
      };
      tick();
    },

    async load(kind) {
      try {
        this[kind] = await api(kind === "calls" ? `/api/overview/calls?period=${this.period}` : "/api/overview/system");
        this[`${kind}Error`] = "";
        if (kind === "calls") this.drawChart();
      } catch (error) {
        this[`${kind}Error`] = error.message;
      }
    },

    async refresh() {
      this.loading = true;
      await Promise.all([this.load("calls"), this.load("system")]);
      this.loading = false;
    },

    rate: (value) => value === null ? "—" : `${value.toFixed(1)}%`,

    get metrics() {
      const { summary } = this.calls;
      return [
        { label: "调用量", icon: "activity", value: fmtNumber(summary.total), meta: `成功 ${fmtNumber(summary.success)} · 失败 ${fmtNumber(summary.failed)}` },
        { label: "成功率", icon: "circle-check", value: this.rate(summary.success_rate), meta: `已完成 ${fmtNumber(summary.success + summary.failed)}` },
        { label: "进行中", icon: "loader-circle", value: fmtNumber(summary.running), meta: "尚未完成的调用" },
        { label: "平均耗时", icon: "clock-3", value: summary.average_duration_ms === null ? "—" : `${(summary.average_duration_ms / 1000).toFixed(1)} s`, meta: "已完成调用" },
      ];
    },

    get pagedModels() {
      return this.calls.models.slice((this.modelPage - 1) * this.modelSize, this.modelPage * this.modelSize);
    },

    get resources() {
      const { memory, disk } = this.system ?? {};
      return [
        { label: "本进程内存", icon: "memory-stick", tip: memory ? `本服务进程占用内存占系统总内存的比例；系统可用 ${fmtBytes(memory.available)}` : "本服务进程占用内存占系统总内存的比例", percent: memory?.process_percent, meta: memory ? `${fmtBytes(memory.process)} · 系统整体 ${memory.percent.toFixed(1)}%（${fmtBytes(memory.used)} / ${fmtBytes(memory.total)}）` : "—" },
        { label: "磁盘", icon: "hard-drive", tip: disk ? `运行目录所在磁盘：${disk.path}` : "运行目录所在磁盘", percent: disk?.percent, meta: disk ? `${fmtBytes(disk.used)} / ${fmtBytes(disk.total)} · 剩余 ${fmtBytes(disk.free)}` : "—" },
      ];
    },

    async drawChart() {
      const { default: Chart } = await import("chart.js/auto");
      await this.$nextTick();
      const style = getComputedStyle(document.documentElement);
      const token = (name) => style.getPropertyValue(name).trim();
      const labels = this.calls.trend.map((item) => dayjs(item.time).format(this.period === "24h" ? "HH:mm" : "MM-DD HH:mm"));
      const datasets = [["success", "成功", "--chart-1"], ["failed", "失败", "--chart-2"], ["running", "进行中", "--chart-3"]].map(([key, label, color]) => ({
        label,
        data: this.calls.trend.map((item) => item[key]),
        backgroundColor: token(color),
        borderRadius: 4,
        maxBarThickness: 20,
        stack: "calls",
      }));
      if (chart) {
        Object.assign(chart.data, { labels, datasets });
        chart.update("none");
        return;
      }
      Chart.defaults.font.family = token("--font-sans");
      Chart.defaults.font.size = 12;
      Chart.defaults.color = token("--color-text-muted");
      chart = new Chart(this.$refs.trend, {
        type: "bar",
        data: { labels, datasets },
        options: {
          maintainAspectRatio: false,
          animation: false,
          interaction: { mode: "index", intersect: false },
          plugins: { legend: { position: "bottom", labels: { boxWidth: 8, boxHeight: 8, usePointStyle: true, pointStyle: "rectRounded" } } },
          scales: {
            x: { stacked: true, grid: { display: false }, border: { display: false }, ticks: { maxTicksLimit: 8, maxRotation: 0 } },
            y: { stacked: true, beginAtZero: true, border: { display: false }, grid: { color: token("--chart-grid") }, ticks: { precision: 0 } },
          },
        },
      });
    },
  };
});

/* ---------- 页面：chat ---------- */
const progressLabels = { getting_account: "确认可用账号", uploading: "上传图片", bootstrapping: "预热首页", getting_token: "获取凭证", preparing_conversation: "准备会话", starting_generation: "启动生成", generating: "生成中", receiving_image: "接收图片" };
const ratios = [["1:1", 1024, 1024, "square"], ["2:3", 1024, 1536, "rectangle-vertical"], ["3:2", 1536, 1024, "rectangle-horizontal"], ["3:4", 1024, 1365, "rectangle-vertical"], ["4:3", 1365, 1024, "rectangle-horizontal"], ["9:16", 1088, 1920, "rectangle-vertical"], ["16:9", 1920, 1088, "rectangle-horizontal"], ["auto", 1024, 1024, "image"]];
const running = (part) => part.status === "queued" || part.status === "running";
const imagePart = (task, index, total, ratio) => ({ type: "image_task", task_id: String(task.id), index, total, ratio, status: task.status, progress: task.progress, elapsed_seconds: task.elapsed_seconds, duration_ms: task.duration_ms, url: task.results[0]?.url, error: task.error });
const userContent = (text, images) => images.length ? [...(text ? [{ type: "text", text }] : []), ...images.map((image) => ({ type: "image_url", image_url: { url: image.url } }))] : text;
const sizeOf = (settings) => settings.ratio === "auto" ? "auto" : ratios.find(([value]) => value === settings.ratio).slice(1, 3).join("x");
const fromUrl = async (url, name) => ({ id: uid(), name, url, file: await urlToFile(url, name) });

/** 创作模式：每个模式对应的记录类型，第一个为默认类型。 */
const creationModes = [
  { value: "chat", label: "聊天", icon: "message-circle", types: ["chat"] },
  { value: "image", label: "生图", icon: "image", types: ["image"] },
  { value: "voice", label: "语音", icon: "audio-lines", types: ["speech", "transcription"] },
];
const recordIcons = { chat: "message-circle", image: "image", speech: "audio-lines", transcription: "mic" };

Alpine.data("chat", () => {
  const retrying = new Set();
  let followed, recorder;

  return {
    modes: creationModes,
    recordIcons,
    efforts: [["", "默认思考"], ["low", "低思考"], ["medium", "中思考"], ["high", "高思考"], ["xhigh", "超高思考"]],
    voices: [
      ["juniper", "Juniper · 开朗轻快"],
      ["maple", "Maple · 欢快直率"],
      ["cove", "Cove · 沉稳直接"],
      ["breeze", "Breeze · 生动真诚"],
      ["orbit", "Spruce · 平静笃定"],
      ["glimmer", "Sol · 机敏松弛"],
      ["ember", "Ember · 自信乐观"],
      ["fathom", "Arbor · 随和百搭"],
      ["vale", "Vale · 明亮好奇"],
    ],
    formats: [["mp3", "MP3"], ["opus", "Opus"], ["aac", "AAC"], ["flac", "FLAC"], ["wav", "WAV"]],
    ratios,
    progressLabels,
    mode: "chat",
    type: "chat",
    list: [],
    loaded: {},
    activeId: null,
    models: ["auto"],
    model: "auto",
    imageModels: [],
    effort: "",
    webSearch: false,
    voice: "cove",
    format: "mp3",
    audio: null,
    recording: false,
    quota: null,
    settings: { ratio: "1:1", count: 1 },
    input: "",
    images: [],
    loading: false,
    error: "",
    sideOpen: false,
    gone: false,
    polling: new Set(),

    init() {
      api("/v1/models").then((result) => {
        const ids = [...new Set(result.data.map((item) => item.id))];
        this.models = [...new Set(["auto", ...result.data.filter((item) => item.type !== "image").map((item) => item.id)])];
        this.imageModels = result.data.filter((item) => item.type === "image").map((item) => item.id);
      }).catch((error) => this.error = error.message);
      api("/api/conversations").then((result) => this.list = result).catch((error) => this.error = error.message);
      this.loadQuota();
    },

    destroy() {
      this.gone = true;
      recorder?.stream.getTracks().forEach((track) => track.stop());
    },

    async loadQuota() {
      if (session.get().role !== "admin") return;
      try {
        this.quota = (await api("/api/accounts/summary")).quota;
      } catch (error) {
        toast(error.message);
      }
    },

    get active() {
      return this.loaded[this.activeId];
    },

    get messages() {
      return this.active ? this.active.messages : [];
    },

    get waiting() {
      return this.loading && this.messages.at(-1)?.role === "user";
    },

    get canSend() {
      if (this.loading) return false;
      if (this.mode === "chat") return this.input || this.images.length;
      if (this.type === "transcription") return Boolean(this.audio);
      return this.input;
    },

    get placeholder() {
      return { chat: this.webSearch ? "搜索网络并提问" : "输入问题", image: this.images.length ? "描述如何修改参考图" : "描述想要生成的画面", speech: "输入要合成的文本" }[this.type];
    },

    get settingsLabel() {
      return `${this.settings.ratio} · ${this.settings.count} 张`;
    },

    setMode(mode) {
      this.mode = mode;
      this.setType(creationModes.find((item) => item.value === mode).types[0]);
    },

    setType(type) {
      this.type = type;
      this.model = type === "image" ? this.imageModels[0] : "auto";
      this.webSearch = false;
      this.error = "";
      if (this.mode === "voice") this.images = [];
    },

    async select(id) {
      try {
        this.loaded[id] = await api(`/api/conversations/${id}`);
        this.activeId = id;
        this.error = "";
        this.sideOpen = false;
        this.poll(id);
      } catch (error) {
        this.error = error.message;
      }
    },

    newRecord() {
      this.activeId = null;
      this.error = "";
      this.sideOpen = false;
    },

    async remove(item) {
      if (!await confirmDialog({ title: "删除记录", text: `确定删除「${item.title}」吗？`, ok: "删除" })) return;
      try {
        await api(`/api/conversations/${item.id}`, { method: "DELETE" });
        this.list = this.list.filter((entry) => entry.id !== item.id);
        if (this.activeId === item.id) this.activeId = null;
      } catch (error) {
        toast(error.message);
      }
    },

    async clearAll() {
      if (!await confirmDialog({ title: "清空记录", text: "删除全部创作记录，此操作无法撤销。", ok: "全部删除" })) return;
      try {
        await api("/api/conversations", { method: "DELETE" });
        this.list = [];
        this.activeId = null;
        this.sideOpen = false;
      } catch (error) {
        toast(error.message);
      }
    },

    /** 更新本地记录并同步保存。 */
    async save(id, changes) {
      Object.assign(this.loaded[id], changes);
      await api(`/api/conversations/${id}`, { method: "PATCH", body: changes });
    },

    /** 有当前记录就一直追加一轮，只有用户点「新建」后（无当前记录）的第一次提交才创建记录；turn 只含本轮用户消息，不带上下文。 */
    async begin(type, model, title, content, extra) {
      const turn = [{ role: "user", content }];
      if (this.active) {
        const messages = [...this.active.messages, ...turn];
        await this.save(this.activeId, { messages });
        return { id: this.activeId, messages, turn };
      }
      const created = await api("/api/conversations", { method: "POST", body: { title: title.slice(0, 30), type, model, messages: turn, extra } });
      this.loaded[created.id] = created;
      this.list.unshift({ id: created.id, title: created.title, type });
      this.activeId = created.id;
      return { id: created.id, messages: turn, turn };
    },

    async addImages(files) {
      this.error = "";
      try {
        const images = await Promise.all([...files].map(async (file) => {
          if (!file.type.startsWith("image/")) throw new Error(`${file.name} 不是图片文件`);
          if (file.size > 10 * 1024 * 1024) throw new Error(`${file.name} 超过 10MB`);
          return { id: uid(), name: file.name, url: await readDataUrl(file), file };
        }));
        this.images.push(...images);
      } catch (error) {
        this.error = error.message;
      }
    },

    paste(event) {
      if (this.mode === "voice" || !event.clipboardData.files.length) return;
      event.preventDefault();
      this.addImages(event.clipboardData.files);
    },

    send() {
      if (!this.canSend) return;
      if (this.mode === "image") return this.runImageTurn(this.input, this.model, this.settings, this.images);
      if (this.type === "speech") return this.sendSpeech();
      if (this.type === "transcription") return this.sendTranscription();
      return this.sendChat();
    },

    async sendChat() {
      const extra = { web_search: this.webSearch, reasoning_effort: this.effort };
      const body = { model: this.model, stream: true, ...(this.effort && { reasoning: { effort: this.effort } }), ...(this.webSearch && { tools: [{ type: "web_search" }] }) };
      this.loading = true;
      this.error = "";
      let id, base, turn, output = "";
      try {
        ({ id, messages: base, turn } = await this.begin("chat", this.model, this.input || "图片提问", userContent(this.input, this.images), extra));
        this.input = "";
        this.images = [];
        await api.stream("/v1/responses", { ...body, input: turn }, (event) => {
          if (event.type !== "response.output_text.delta") return;
          output += event.delta;
          this.loaded[id].messages = [...base, { role: "assistant", content: output }];
        });
        await this.save(id, { messages: [...base, { role: "assistant", content: output }] });
      } catch (error) {
        this.error = error.message;
        if (id && !output) await this.save(id, { messages: [...base, { role: "assistant", content: error.message }] });
      } finally {
        this.loading = false;
      }
    },

    async sendSpeech() {
      const { input, voice, format } = this;
      this.loading = true;
      this.error = "";
      let id, base;
      try {
        ({ id, messages: base } = await this.begin("speech", voice, input, input, { voice, format }));
        this.input = "";
        const blob = await api.blob("/v1/audio/speech", { method: "POST", body: { input, voice, response_format: format } });
        await this.save(id, { messages: [...base, { role: "assistant", content: [{ type: "audio", url: await readDataUrl(blob), format }] }] });
      } catch (error) {
        this.error = error.message;
        if (id) await this.save(id, { messages: [...base, { role: "assistant", content: `合成失败：${error.message}` }] });
      } finally {
        this.loading = false;
      }
    },

    async sendTranscription() {
      const file = this.audio;
      const form = new FormData();
      form.append("file", file);
      form.append("model", "gpt-transcribe");
      this.loading = true;
      this.error = "";
      let id, base;
      try {
        ({ id, messages: base } = await this.begin("transcription", "gpt-transcribe", file.name, [{ type: "audio_file", name: file.name, size: file.size }], {}));
        this.audio = null;
        const { text } = await api("/v1/audio/transcriptions", { method: "POST", body: form });
        await this.save(id, { messages: [...base, { role: "assistant", content: text }] });
      } catch (error) {
        this.error = error.message;
        if (id) await this.save(id, { messages: [...base, { role: "assistant", content: `转写失败：${error.message}` }] });
      } finally {
        this.loading = false;
      }
    },

    pickAudio(event) {
      this.audio = event.target.files[0];
      this.error = "";
      event.target.value = "";
    },

    async startRecording() {
      this.error = "";
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const chunks = [];
        recorder = new MediaRecorder(stream);
        recorder.ondataavailable = (event) => chunks.push(event.data);
        recorder.onstop = () => {
          stream.getTracks().forEach((track) => track.stop());
          const blob = new Blob(chunks, { type: recorder.mimeType });
          this.audio = new File([blob], `录音-${dayjs().format("MMDD-HHmmss")}.webm`, { type: blob.type });
          this.recording = false;
        };
        recorder.start();
        this.recording = true;
      } catch (error) {
        this.error = error.message;
      }
    },

    stopRecording() {
      recorder.stop();
    },

    async submitImage(prompt, model, settings, refs, historyId, turnId) {
      if (!refs.length) return api("/api/tasks/image-generation", { method: "POST", body: { prompt, history_id: historyId, turn_id: turnId, model, size: sizeOf(settings), n: 1 } });
      const form = new FormData();
      refs.forEach((image) => form.append("image", image.file));
      form.append("prompt", prompt);
      if (historyId) form.append("history_id", historyId);
      if (turnId) form.append("turn_id", turnId);
      form.append("model", model);
      form.append("size", sizeOf(settings));
      form.append("n", 1);
      return api("/api/tasks/image-edit", { method: "POST", body: form });
    },

    async runImageTurn(prompt, model, settings, refs) {
      const turn = { prompt, model, settings: { ...settings }, references: refs.map(({ id, name, url }) => ({ id, name, url })) };
      const extra = { image_settings: turn.settings };
      this.loading = true;
      this.error = "";
      let id, base, parts = [];
      const assistant = (content) => ({ role: "assistant", content, image_turn: turn });
      try {
        ({ id, messages: base } = await this.begin("image", model, prompt, userContent(prompt, refs), extra));
        this.input = "";
        this.images = [];
        const first = await this.submitImage(prompt, model, settings, refs);
        const tasks = [first, ...await Promise.all(Array.from({ length: settings.count - 1 }, () => this.submitImage(prompt, model, settings, refs, first.history_id || first.id, first.turn_id || first.id)))];
        const ids = tasks.map((task) => String(task.id));
        parts = tasks.map((task, index) => imagePart(task, index + 1, tasks.length, settings.ratio));
        await this.save(id, { messages: [...base, assistant(parts)], extra: { ...extra, image_task_ids: ids } });
        await this.poll(id);
      } catch (error) {
        this.error = error.message;
        if (id) await this.save(id, { messages: [...base, assistant(parts.length ? parts.map((part) => running(part) ? { ...part, status: "error", error: error.message } : part) : `生成失败：${error.message}`)] });
      } finally {
        this.loading = false;
      }
    },

    /** 轮询会话里未结束的生图任务直到全部结束；离开页面时停止，回到会话后由 select 接着轮询。 */
    async poll(id) {
      if (this.polling.has(id)) return;
      this.polling.add(id);
      try {
        while (!this.gone) {
          const ids = this.loaded[id].messages.flatMap((message) => this.parts(message, "image_task")).filter(running).map((part) => part.task_id);
          if (!ids.length) break;
          await sleep(2000);
          if (this.gone) break;
          const found = new Map((await api(`/api/tasks?ids=${ids}`)).items.map((task) => [String(task.id), task]));
          const messages = this.loaded[id].messages.map((message) => this.parts(message, "image_task").some((part) => found.has(part.task_id)) ? { ...message, content: message.content.map((part) => found.has(part.task_id) ? imagePart(found.get(part.task_id), part.index, part.total, part.ratio) : part) } : message);
          await this.save(id, { messages });
        }
        this.loadQuota();
      } catch (error) {
        this.error = error.message;
      } finally {
        this.polling.delete(id);
      }
    },

    async retryTask(messageIndex, failed, turn) {
      if (retrying.has(failed.task_id)) return;
      retrying.add(failed.task_id);
      const id = this.activeId;
      this.loading = true;
      this.error = "";
      const replace = (taskId, part) => this.save(id, { messages: this.loaded[id].messages.map((message, index) => index === messageIndex ? { ...message, content: message.content.map((item) => item.task_id === taskId ? part : item) } : message) });
      try {
        const previous = (await api(`/api/tasks?ids=${failed.task_id}`)).items[0];
        const refs = await Promise.all(turn.references.map((ref) => fromUrl(ref.url, ref.name)));
        let part = imagePart(await this.submitImage(turn.prompt, turn.model, turn.settings, refs, previous.history_id || previous.id, previous.turn_id || previous.id), failed.index, failed.total, failed.ratio);
        await replace(failed.task_id, part);
        while (running(part)) {
          await sleep(2000);
          const next = imagePart((await api(`/api/tasks?ids=${part.task_id}`)).items[0], failed.index, failed.total, failed.ratio);
          await replace(part.task_id, next);
          part = next;
        }
        this.loadQuota();
      } catch (error) {
        this.error = error.message;
      } finally {
        retrying.delete(failed.task_id);
        this.loading = retrying.size > 0;
      }
    },

    /** 把图片记录的提示词、参考图和设置放回输入框。 */
    async reuseTurn(turn) {
      try {
        this.setMode("image");
        this.images = await Promise.all(turn.references.map((ref) => fromUrl(ref.url, ref.name)));
        this.input = turn.prompt;
        this.model = turn.model;
        this.settings = { ...turn.settings };
      } catch (error) {
        this.error = error.message;
      }
    },

    async addToEdit(url, name, turn) {
      try {
        if (this.mode === "voice" || turn) this.setMode("image");
        this.images.push(await fromUrl(url, name));
        if (turn) {
          this.model = turn.model;
          this.settings = { ...turn.settings };
        }
      } catch (error) {
        this.error = error.message;
      }
    },

    setRatio(ratio) {
      this.settings.ratio = ratio;
    },

    text: (message) => typeof message.content === "string" ? message.content : message.content.filter((part) => part.type === "text").map((part) => part.text).join(""),
    parts: (message, type) => Array.isArray(message.content) ? message.content.filter((part) => part.type === type) : [],

    openImage(message, part) {
      const done = this.parts(message, "image_task").filter((item) => item.url);
      lightbox(done.map((item) => ({ src: item.url })), done.indexOf(part));
    },

    turnMeta(turn) {
      const { ratio, count } = turn.settings;
      return `${turn.model} · ${ratio} · ${count} 张`;
    },

    taskMeta(part) {
      if (part.status === "success") return `${(part.duration_ms / 1000).toFixed(1)}s`;
      if (part.status === "running") return `${part.elapsed_seconds.toFixed(1)}s`;
      return part.status === "error" ? "生成失败" : "等待中";
    },

    lightbox,

    /** 停留在底部时跟随新内容滚动，切换记录后直接定位到底部。 */
    follow(el) {
      const changed = this.activeId !== followed;
      followed = this.activeId;
      if (!this.messages.length) return;
      if (changed || el.scrollHeight - el.scrollTop - el.clientHeight < 120) this.$nextTick(() => el.scrollTop = el.scrollHeight);
    },
  };
});

/* ---------- 页面：accounts ---------- */
/** 远程来源：key 为列表字段，items 为远程账号路径与字段，body 为导入时的请求字段。 */
const SOURCES = {
  cpa: { key: "pools", path: "/api/cpa/pools", items: "files", body: "names" },
  sub2api: { key: "servers", path: "/api/sub2api/servers", items: "accounts", body: "account_ids" },
};

const JOB_STATUS = { pending: ["排队中", "badge-info"], running: ["导入中", "badge-info"], completed: ["已完成", "badge-success"], failed: ["失败", "badge-error"] };

const importText = (data) => `新增 ${data.added} 个，跳过 ${data.skipped} 个${data.errors.length ? `，失败 ${data.errors.length} 个：${data.errors[0].error}` : ""}`;

const accountOf = (raw) => raw.access_token || raw.accessToken ? { ...raw, access_token: raw.access_token || raw.accessToken, accessToken: undefined } : null;

Alpine.data("accounts", () => {
  const timers = {};

  return {
    tab: "accounts",
    statuses: { 正常: "badge-success", 限流: "badge-warning", 异常: "badge-error", 禁用: "badge-neutral" },
    jobStatus: JOB_STATUS,

    summary: null,
    items: [],
    types: [],
    total: 0,
    page: 1,
    size: 10,
    query: "",
    type: "",
    status: "",
    loading: true,
    selected: [],
    busy: "",
    models: { open: false, loading: false, items: [] },
    detail: null,
    detailTab: "info",
    edit: { open: false, account: null, status: "", proxy: "", saving: false, testing: false },
    imp: { open: false, method: "menu", tokens: "", session: "", codex: "", email: "", oauth: null, callback: "", starting: false, submitting: false },

    pools: null,
    servers: null,
    syncing: "",
    poolForm: { open: false },
    serverForm: { open: false },
    browser: { open: false, kind: "cpa", source: null, rows: [], selected: [], query: "", page: 1, size: 50, starting: false },

    init() {
      this.loadAccounts();
      this.$watch("tab", (tab) => {
        Object.values(timers).forEach(clearTimeout);
        tab === "accounts" ? this.loadAccounts() : this.loadSources(tab);
      });
      this.$watch("query", () => this.reload());
      this.$watch("type", () => this.reload());
      this.$watch("status", () => this.reload());
    },

    destroy() {
      Object.values(timers).forEach(clearTimeout);
    },

    /* ---------- 账号 ---------- */
    async loadAccounts() {
      this.loading = true;
      const params = new URLSearchParams({ page: this.page, page_size: this.size, query: this.query, type: this.type, status: this.status });
      try {
        const [summary, data] = await Promise.all([api("/api/accounts/summary"), api(`/api/accounts?${params}`)]);
        Object.assign(this, { summary, items: data.items, types: data.types, total: data.total, selected: [] });
      } catch (error) {
        toast(error.message);
      } finally {
        this.loading = false;
      }
    },

    reload() {
      this.page = 1;
      this.loadAccounts();
    },

    get metrics() {
      const { total, active, limited, abnormal, disabled, quota, inflight } = this.summary;
      return [
        { label: "账号总数", icon: "users-round", value: total, meta: `禁用 ${disabled}` },
        { label: "正常账号", icon: "circle-check", value: active, meta: `限流 ${limited} · 异常 ${abnormal}` },
        { label: "剩余额度", icon: "coins", value: quota, meta: "全部账号合计" },
        { label: "进行中", icon: "activity", value: inflight, meta: "正在生成的图片" },
      ];
    },

    get abnormal() {
      return this.items.filter((item) => item.status === "异常");
    },

    get allSelected() {
      return this.items.length > 0 && this.selected.length === this.items.length;
    },

    resetText(value) {
      if (!value) return "—";
      const seconds = dayjs(value).diff(dayjs(), "second");
      if (seconds <= 0) return "已恢复";
      const pad = (number) => String(number).padStart(2, "0");
      return `${Math.floor(seconds / 3600)}h:${pad(Math.floor(seconds % 3600 / 60))}m`;
    },

    mask: (value) => `${value.slice(0, 28)}…${value.slice(-14)}`,

    async remove(tokens, title) {
      if (!await confirmDialog({ title, text: "删除后无法恢复。", ok: "删除" })) return;
      this.busy = "delete";
      try {
        await api("/api/accounts", { method: "DELETE", body: { tokens } });
        await this.loadAccounts();
      } catch (error) {
        toast(error.message);
      } finally {
        this.busy = "";
      }
    },

    async queryAll() {
      this.busy = "quota";
      try {
        const data = await api("/api/accounts/quota", { method: "POST" });
        if (data.errors.length) toast(`${data.queried} 个账号已更新，${data.errors.length} 个失败：${data.errors[0].error}`);
        await this.loadAccounts();
      } catch (error) {
        toast(error.message);
      } finally {
        this.busy = "";
      }
    },

    async refreshQuota(account) {
      this.busy = account.access_token;
      try {
        await api("/api/accounts/quota/refresh", { method: "POST", body: { access_token: account.access_token } });
        await this.loadAccounts();
      } catch (error) {
        toast(error.message);
      } finally {
        this.busy = "";
      }
    },

    async loadModels(refresh) {
      this.models.open = true;
      this.models.loading = true;
      try {
        this.models.items = (await api(`/v1/models${refresh ? "?refresh=true" : ""}`)).data;
      } catch (error) {
        toast(error.message);
      } finally {
        this.models.loading = false;
      }
    },

    openEdit(account) {
      this.edit = { open: true, account, status: account.status, proxy: account.proxy, saving: false, testing: false };
    },

    async testProxy() {
      this.edit.testing = true;
      try {
        const { result } = await api("/api/proxy/test", { method: "POST", body: { url: this.edit.proxy } });
        result.ok ? toast(`代理可用，耗时 ${result.latency_ms} ms，状态码 ${result.status}`, "info") : toast(`代理不可用：${result.error}`);
      } catch (error) {
        toast(error.message);
      } finally {
        this.edit.testing = false;
      }
    },

    async saveEdit() {
      this.edit.saving = true;
      try {
        await api("/api/accounts/update", { method: "POST", body: { access_token: this.edit.account.access_token, status: this.edit.status, proxy: this.edit.proxy } });
        this.edit.open = false;
        await this.loadAccounts();
      } catch (error) {
        toast(error.message);
      } finally {
        this.edit.saving = false;
      }
    },

    /* ---------- 导入 ---------- */
    get importTitle() {
      return { menu: "导入账号", oauth: "登录已有账号", token: "导入 Access Token", session: "导入 Session JSON", codex: "导入 Codex 认证 JSON", files: "导入账号 JSON 文件" }[this.imp.method];
    },

    get tokenList() {
      return this.imp.tokens.split(/\r?\n/).filter(Boolean);
    },

    openImport() {
      this.imp = { open: true, method: "menu", tokens: "", session: "", codex: "", email: "", oauth: null, callback: "", starting: false, submitting: false };
    },

    gotoSource(tab) {
      this.imp.open = false;
      this.tab = tab;
    },

    async submitImport(path, body) {
      this.imp.submitting = true;
      try {
        const data = await api(path, { method: "POST", body });
        this.imp.open = false;
        toast(importText(data), data.errors.length ? "error" : "info");
        await this.loadAccounts();
      } catch (error) {
        toast(error.message);
      } finally {
        this.imp.submitting = false;
      }
    },

    importTyped() {
      try {
        const { method, session, codex } = this.imp;
        if (method === "token") return this.submitImport("/api/accounts", this.tokenList.map((access_token) => ({ access_token })));
        if (method === "session") return this.submitImport("/api/accounts", [{ access_token: JSON.parse(session).accessToken }]);
        if (method === "codex") return this.submitImport("/api/accounts", [accountOf(JSON.parse(codex))]);
        return this.submitImport("/api/accounts/oauth/finish", { session_id: this.imp.oauth.session_id, callback: this.imp.callback });
      } catch (error) {
        toast(`内容格式不正确：${error.message}`);
      }
    },

    async readTxt(event) {
      const file = event.target.files[0];
      event.target.value = "";
      this.imp.tokens = [...this.tokenList, ...(await file.text()).split(/\r?\n/).filter(Boolean)].join("\n");
    },

    async readJsonFiles(event) {
      const files = [...event.target.files];
      event.target.value = "";
      try {
        const results = await Promise.all(files.map(async (file) => {
          const value = JSON.parse(await file.text());
          const list = Array.isArray(value) ? value : accountOf(value) ? [value] : value.accounts ?? value.items ?? [];
          return list.map(accountOf).filter(Boolean);
        }));
        const accounts = results.flat();
        const failed = results.filter((list) => !list.length).length;
        if (!accounts.length) return toast("所选文件中没有可导入的账号");
        if (await confirmDialog({ title: "确认导入", text: `识别到 ${accounts.length} 个账号${failed ? `，${failed} 个文件未识别` : ""}。`, ok: "导入", danger: false })) await this.submitImport("/api/accounts", accounts);
      } catch (error) {
        toast(`读取文件失败：${error.message}`);
      }
    },

    async startOAuth() {
      this.imp.starting = true;
      try {
        this.imp.oauth = await api("/api/accounts/oauth/start", { method: "POST", body: { email_hint: this.imp.email } });
        this.imp.callback = "";
        open(this.imp.oauth.authorize_url, "_blank", "noopener,noreferrer");
      } catch (error) {
        toast(error.message);
      } finally {
        this.imp.starting = false;
      }
    },

    /* ---------- 远程来源 ---------- */
    get sources() {
      return this[SOURCES[this.tab].key];
    },

    async loadSources(tab) {
      const { key, path } = SOURCES[tab];
      try {
        this[key] = (await api(path))[key];
        this.watchJobs(tab);
      } catch (error) {
        toast(error.message);
      }
    },

    watchJobs(tab) {
      clearTimeout(timers[tab]);
      if (this[SOURCES[tab].key].some((item) => ["pending", "running"].includes(item.import_job?.status))) timers[tab] = setTimeout(() => this.loadSources(tab), 1500);
    },

    progress: (job) => job.total ? Math.round(job.completed / job.total * 100) : 0,

    openSourceForm(item) {
      if (this.tab === "cpa") {
        this.poolForm = { open: true, id: item?.id ?? "", name: item?.name ?? "", base_url: item?.base_url ?? "", secret: "", show: false, saving: false };
        return;
      }
      this.serverForm = { open: true, id: item?.id ?? "", name: item?.name ?? "", base_url: item?.base_url ?? "", auth: item?.has_api_key ? "api_key" : "password", email: item?.email ?? "", password: "", api_key: "", group_id: item?.group_id ?? "", show: false, groups: null, loadingGroups: false, saving: false };
    },

    async savePool() {
      const form = this.poolForm;
      form.saving = true;
      try {
        const body = { name: form.name, base_url: form.base_url, ...(form.secret && { secret_key: form.secret }) };
        this.pools = (await api(form.id ? `/api/cpa/pools/${form.id}` : "/api/cpa/pools", { method: "POST", body })).pools;
        form.open = false;
      } catch (error) {
        toast(error.message);
      } finally {
        form.saving = false;
      }
    },

    async saveServer() {
      const form = this.serverForm;
      const password = form.auth === "password";
      form.saving = true;
      try {
        const body = form.id
          ? { name: form.name, base_url: form.base_url, group_id: form.group_id, ...(password ? { email: form.email, api_key: "", ...(form.password && { password: form.password }) } : { email: "", password: "", ...(form.api_key && { api_key: form.api_key }) }) }
          : { name: form.name, base_url: form.base_url, group_id: form.group_id, email: password ? form.email : "", password: password ? form.password : "", api_key: password ? "" : form.api_key };
        this.servers = (await api(form.id ? `/api/sub2api/servers/${form.id}` : "/api/sub2api/servers", { method: "POST", body })).servers;
        form.open = false;
      } catch (error) {
        toast(error.message);
      } finally {
        form.saving = false;
      }
    },

    async loadGroups() {
      const form = this.serverForm;
      form.loadingGroups = true;
      try {
        const { groups } = await api(`/api/sub2api/servers/${form.id}/groups`);
        if (!groups.length) toast("对方服务没有配置分组", "info");
        form.groups = groups.length ? groups : null;
      } catch (error) {
        toast(error.message);
      } finally {
        form.loadingGroups = false;
      }
    },

    groupLabel: (group) => `${group.name || `分组 ${group.id}`}${group.platform ? `（${group.platform}）` : ""}${group.account_count ? ` · ${group.active_account_count}/${group.account_count}` : ""}`,

    async removeSource(item) {
      if (!await confirmDialog({ title: "删除连接", text: `删除「${item.name || item.base_url}」后，已导入的账号不受影响。`, ok: "删除" })) return;
      const { key, path } = SOURCES[this.tab];
      try {
        this[key] = (await api(`${path}/${item.id}`, { method: "DELETE" }))[key];
      } catch (error) {
        toast(error.message);
      }
    },

    async browse(item) {
      this.syncing = item.id;
      try {
        this.browser = { open: false, kind: this.tab, source: item, rows: [], total: 0, selected: [], query: "", page: 1, size: 50, starting: false };
        if (this.tab === "cpa") this.browser.rows = (await api(`/api/cpa/pools/${item.id}/files`)).files.map((file) => ({ key: file.name, title: file.email || file.name, meta: file.name }));
        else await this.loadBrowser();
        this.browser.open = true;
      } catch (error) {
        toast(error.message);
      } finally {
        this.syncing = "";
      }
    },

    /** Sub2API 账号太多，按页向对方服务读取；CPA 文件少，一次读完后本地筛选。 */
    async loadBrowser() {
      const { source, page, size, query } = this.browser;
      const { accounts, total } = await api(`/api/sub2api/servers/${source.id}/accounts?page=${page}&size=${size}&search=${encodeURIComponent(query)}`);
      const rows = accounts.map((account) => ({ key: String(account.id), title: account.email || account.name || account.id, meta: `ID ${account.id}${account.expires_at ? ` · ${dayjs(account.expires_at).format("YYYY-MM-DD HH:mm")} 过期` : ""}`, plan: account.plan_type, status: account.status }));
      Object.assign(this.browser, { rows, total });
    },

    async reloadBrowser() {
      if (this.browser.kind === "cpa") return;
      try {
        await this.loadBrowser();
      } catch (error) {
        toast(error.message);
      }
    },

    get browserTotal() {
      return this.browser.kind === "cpa" ? this.browserRows.length : this.browser.total;
    },

    get browserRows() {
      if (this.browser.kind !== "cpa") return this.browser.rows;
      const query = this.browser.query.toLowerCase();
      return this.browser.rows.filter((row) => `${row.title} ${row.meta} ${row.plan ?? ""}`.toLowerCase().includes(query));
    },

    get browserPage() {
      if (this.browser.kind !== "cpa") return this.browser.rows;
      const { page, size } = this.browser;
      return this.browserRows.slice((page - 1) * size, page * size);
    },

    get browserAll() {
      return this.browserRows.length > 0 && this.browserRows.every((row) => this.browser.selected.includes(row.key));
    },

    toggleBrowserAll() {
      const keys = this.browserRows.map((row) => row.key);
      this.browser.selected = this.browserAll ? this.browser.selected.filter((key) => !keys.includes(key)) : [...new Set([...this.browser.selected, ...keys])];
    },

    async startSourceImport(all) {
      const { kind, source, selected, query } = this.browser;
      const { key, path, body } = SOURCES[kind];
      this.browser.starting = true;
      try {
        const { import_job } = await api(`${path}/${source.id}/import`, { method: "POST", body: all ? { all: true, search: query } : { [body]: selected } });
        this[key] = this[key].map((item) => item.id === source.id ? { ...item, import_job } : item);
        this.browser.open = false;
        this.watchJobs(kind);
      } catch (error) {
        toast(error.message);
      } finally {
        this.browser.starting = false;
      }
    },
  };
});

/* ---------- 页面：keys ---------- */
Alpine.data("keys", () => ({
  items: [],
  loading: true,
  query: "",
  page: 1,
  size: 20,
  form: { open: false, id: "", name: "", key: "", plan: "free", route: "web", error: "", saving: false },

  async init() {
    await this.load();
  },

  async load() {
    try {
      this.items = (await api("/api/auth/users")).items;
    } catch (error) {
      toast(error.message);
    } finally {
      this.loading = false;
    }
  },

  get filtered() {
    return this.items.filter((item) => item.name.includes(this.query) || item.key.includes(this.query));
  },

  get paged() {
    return this.filtered.slice((this.page - 1) * this.size, this.page * this.size);
  },

  openForm(item) {
    this.form = { open: true, id: item?.id ?? "", name: item?.name ?? "", key: item?.key ?? "", plan: item?.plan ?? ["free"], route: item?.route ?? ["web"], error: "", saving: false };
  },

  async save() {
    this.form.saving = true;
    try {
      const body = { name: this.form.name, key: this.form.key, plan: this.form.plan, route: this.form.route };
      this.items = (await api(this.form.id ? `/api/auth/users/${this.form.id}` : "/api/auth/users", { method: "POST", body })).items;
      this.form.open = false;
    } catch (error) {
      this.form.error = error.message;
    } finally {
      this.form.saving = false;
    }
  },

  async toggle(item, enabled) {
    try {
      this.items = (await api(`/api/auth/users/${item.id}`, { method: "POST", body: { enabled } })).items;
    } catch (error) {
      toast(error.message);
      await this.load();
    }
  },

  async remove(item) {
    if (!await confirmDialog({ title: "删除密钥", text: `删除「${item.name || item.key}」后，使用它的调用会立即失效。`, ok: "删除" })) return;
    try {
      this.items = (await api(`/api/auth/users/${item.id}`, { method: "DELETE" })).items;
    } catch (error) {
      toast(error.message);
    }
  },
}));

/* ---------- 页面：gallery ---------- */
Alpine.data("gallery", () => ({
  items: [],
  storage: null,
  loading: true,
  busy: "",
  range: [],
  view: "card",
  page: 1,
  size: 12,
  selected: [],
  byDate: { open: false, date: "" },
  cleanup: { open: false, target: 500 },

  init() {
    this.load();
  },

  get filters() {
    const [start_date, end_date] = this.range;
    return { start_date, end_date };
  },

  get filtered() {
    return Boolean(this.range.length);
  },

  get paged() {
    return this.items.slice((this.page - 1) * this.size, this.page * this.size);
  },

  get pageSelected() {
    return this.paged.length > 0 && this.paged.every((item) => this.selected.includes(item.rel));
  },

  get allSelected() {
    return this.items.length > 0 && this.items.every((item) => this.selected.includes(item.rel));
  },

  async load() {
    this.loading = true;
    try {
      const [list, storage] = await Promise.all([api(`/api/images?${new URLSearchParams(Object.entries(this.filters).filter(([, value]) => value))}`), api("/api/images/storage")]);
      this.items = list.items;
      this.storage = storage;
      this.selected = this.selected.filter((rel) => list.items.some((item) => item.rel === rel));
      this.page = 1;
    } catch (error) {
      toast(error.message);
    } finally {
      this.loading = false;
    }
  },

  async run(name, task) {
    this.busy = name;
    try {
      await task();
    } catch (error) {
      toast(error.message);
    } finally {
      this.busy = "";
    }
  },

  toggle(rels, checked) {
    this.selected = checked ? [...new Set([...this.selected, ...rels])] : this.selected.filter((rel) => !rels.includes(rel));
  },

  preview(item) {
    lightbox(this.items.map((row) => ({ src: row.url, meta: `${fmtBytes(row.size)} · ${row.width} × ${row.height}` })), this.items.indexOf(item));
  },

  download(item) {
    this.run(`download:${item.rel}`, async () => saveBlob(await api.blob(`/api/images/download/${item.rel}`), item.name));
  },

  downloadSelected() {
    this.run("download", async () => saveBlob(await api.blob("/api/images/download", { method: "POST", body: { paths: this.selected } }), "images.zip"));
  },

  async remove(body, title, text) {
    if (!await confirmDialog({ title, text, ok: "删除" })) return;
    await this.run("delete", async () => {
      await api("/api/images/delete", { method: "POST", body });
      await this.load();
    });
  },

  async removeByDate() {
    await this.run("delete", async () => {
      await api("/api/images/delete", { method: "POST", body: { end_date: this.byDate.date, all_matching: true } });
      this.byDate.open = false;
      await this.load();
    });
  },

  compress() {
    this.run("compress", async () => {
      const result = await api("/api/images/storage/compress", { method: "POST" });
      toast(`已压缩 ${result.compressed} 张图片，节省 ${fmtBytes(result.saved_bytes)}`, "info");
      await this.load();
    });
  },

  async cleanupSpace() {
    await this.run("cleanup", async () => {
      const result = await api(`/api/images/storage/cleanup-to-target?target_free_mb=${this.cleanup.target}&dry_run=false`, { method: "POST" });
      this.cleanup.open = false;
      toast(`已删除 ${result.removed} 张图片，释放 ${result.freed_mb} MB`, "info");
      await this.load();
    });
  },
}));

/* ---------- 页面：logs ---------- */
const LOG_STATUS = {
  running: { label: "调用中", title: "调用中", icon: "loader-circle", tone: "text-info", badge: "badge-info", bar: "progress-info" },
  failed: { label: "失败", title: "调用失败", icon: "circle-x", tone: "text-danger", badge: "badge-error", bar: "progress-error" },
  success: { label: "完成", title: "调用完成", icon: "circle-check", tone: "text-success", badge: "badge-success", bar: "progress-success" },
};

const LOG_FIELDS = {
  duration_ms: "耗时（毫秒）",
  endpoint: "调用地址",
  key_id: "令牌 ID",
  key_name: "令牌名称",
  model: "模型",
  request_text: "请求内容",
  role: "角色",
  stage: "当前阶段",
  started_at: "开始时间",
  status: "状态",
  updated_at: "更新时间",
};

Alpine.data("logs", () => {
  let timer;

  return {
    items: [],
    total: 0,
    page: 1,
    size: 10,
    range: [],
    selected: [],
    loading: true,
    error: "",
    auto: true,
    interval: "5",
    detail: null,
    detailTab: "overview",
    refreshedAt: "",
    label: (key) => LOG_FIELDS[key] ?? key,
    status: (log) => LOG_STATUS[log.detail.status],
    urls: (log) => log.detail.urls ?? [],
    thumb: (url) => url.replace("/images/", "/image-thumbnails/"),
    duration: (log) => log.detail.status === "running" ? Date.now() - dayjs(log.detail.started_at).valueOf() : log.detail.duration_ms,

    init() {
      this.load();
      this.schedule();
      this.$watch("auto", () => this.schedule());
      this.$watch("interval", () => this.schedule());
    },

    destroy() {
      clearInterval(timer);
    },

    schedule() {
      clearInterval(timer);
      if (this.auto) timer = setInterval(() => document.hidden || this.load(), this.interval * 1000);
    },

    async load() {
      const [start_date, end_date] = this.range;
      try {
        const data = await api(`/api/logs?${new URLSearchParams(Object.entries({ start_date, end_date, page: this.page, page_size: this.size }).filter(([, value]) => value))}`);
        this.items = data.items;
        this.total = data.total;
        if (this.detail) this.detail = data.items.find((log) => log.id === this.detail.id) ?? this.detail;
        this.error = "";
        this.refreshedAt = dayjs().format("HH:mm:ss");
      } catch (error) {
        this.error = error.message;
      } finally {
        this.loading = false;
      }
    },

    go(page, size) {
      Object.assign(this, { page, size, selected: [] });
      this.load();
    },

    get pageSelected() {
      return this.items.length > 0 && this.items.every((log) => this.selected.includes(log.id));
    },

    async remove(ids) {
      if (!await confirmDialog({ title: ids.length > 1 ? "删除所选日志" : "删除日志", text: `删除 ${ids.length} 条日志后无法恢复。`, ok: "删除" })) return;
      try {
        await api("/api/logs/delete", { method: "POST", body: { ids } });
        this.selected = this.selected.filter((id) => !ids.includes(id));
        if (ids.includes(this.detail?.id)) this.detail = null;
        await this.load();
      } catch (error) {
        toast(error.message);
      }
    },

    preview(log, index) {
      lightbox(this.urls(log).map((src) => ({ src })), index);
    },

    get scalars() {
      return Object.entries(this.detail.detail).filter(([key, value]) => !["urls", "events"].includes(key) && typeof value !== "object");
    },

    get json() {
      return JSON.stringify(this.detail.detail, null, 2);
    },

    format: (value) => typeof value === "object" ? JSON.stringify(value) : String(value),
  };
});

/* ---------- 页面：settings ---------- */
/** 左侧分组：保存时只提交有改动的分组字段，服务端按字段合并。 */
const SETTING_TABS = [
  { key: "global", label: "全局设置", fields: ["image_model_name", "default_upstream_model_name", "default_thinking_effort", "image_codex_model", "image_codex_image_model", "global_system_prompt"] },
  { key: "account", label: "账号维护", fields: ["refresh_account_interval_minute", "auto_remove_invalid_accounts"] },
  { key: "image", label: "图片生成", fields: ["base_url", "image_retention_days", "image_poll_timeout_secs", "image_account_concurrency", "image_account_retries", "remove_conversation_after_result"] },
  { key: "storage", label: "图片存储", fields: ["image_storage"] },
  { key: "proxy", label: "网络代理", fields: ["proxy"] },
  { key: "clearance", label: "FlareSolverr", fields: ["proxy_runtime"] },
];

Alpine.data("settings", () => ({
  tabs: SETTING_TABS,
  tab: "global",
  config: null,
  saved: null,
  busy: "",
  targetUrl: "https://chatgpt.com",
  results: {},
  onOff: [[true, "开启"], [false, "关闭"]],
  thinking: [["auto", "自动"], ["standard", "标准"], ["extended", "扩展"], ["max", "最大"]],
  storageModes: [["local", "仅本机"], ["webdav", "仅 WebDAV"], ["both", "本机和 WebDAV"]],
  egressModes: [["direct", "直连"], ["single_proxy", "单代理 / WARP"]],
  clearanceModes: [["none", "不启用"], ["manual", "手动 Cookie"], ["flaresolverr", "FlareSolverr"]],
  imageNumbers: [
    { key: "image_retention_days", label: "图片保留时间", desc: "超过该天数的生成图片会被自动清理。", unit: "天" },
    { key: "image_poll_timeout_secs", label: "图片轮询超时", desc: "等待单次图片生成结果的最长时间。", unit: "秒" },
    { key: "image_account_concurrency", label: "单账号图片并发", desc: "同一账号同时进行的图片任务数量上限。", unit: "个" },
    { key: "image_account_retries", label: "失败换号重试", desc: "生图失败（内容违规除外）时更换账号重试的次数，0 为不重试。", unit: "次" },
  ],
  clearanceNumbers: [
    { key: "timeout_sec", label: "获取超时", desc: "单次获取通行凭证允许等待的最长时间。" },
    { key: "refresh_interval", label: "刷新间隔", desc: "通行凭证自动重新获取的间隔。" },
  ],

  init() {
    this.load();
  },

  async load() {
    try {
      const { config } = await api("/api/settings");
      this.config = config;
      this.saved = JSON.parse(JSON.stringify(config));
      this.results = {};
    } catch (error) {
      toast(error.message);
    }
  },

  async run(name, task) {
    this.busy = name;
    try {
      await task();
    } catch (error) {
      toast(error.message);
    } finally {
      this.busy = "";
    }
  },

  isDirty(tab) {
    return SETTING_TABS.find((item) => item.key === tab).fields.some((key) => JSON.stringify(this.config[key]) !== JSON.stringify(this.saved[key]));
  },

  get dirty() {
    return SETTING_TABS.some((item) => this.isDirty(item.key));
  },

  undo() {
    this.config = JSON.parse(JSON.stringify(this.saved));
    this.results = {};
  },

  async save() {
    const fields = SETTING_TABS.filter((item) => this.isDirty(item.key)).flatMap((item) => item.fields);
    if (!fields.length) return;
    const { config } = await api("/api/settings", { method: "POST", body: Object.fromEntries(fields.map((key) => [key, this.config[key]])) });
    fields.forEach((key) => {
      this.config[key] = config[key];
      this.saved[key] = JSON.parse(JSON.stringify(config[key]));
    });
  },

  testProxy() {
    this.run("test-proxy", async () => {
      const { result } = await api("/api/proxy/test", { method: "POST", body: { url: this.config.proxy } });
      this.results.proxy = { ok: result.ok, text: result.ok ? `连接正常：HTTP ${result.status}，${result.latency_ms} ms` : `连接失败：${result.error}` };
    });
  },

  testStorage() {
    this.run("test-storage", async () => {
      await this.save();
      const { result } = await api("/api/image-storage/test", { method: "POST", body: {} });
      this.results.storage = { ok: result.ok, text: result.ok ? `连接可用：HTTP ${result.status}` : `连接失败：${result.error ?? `HTTP ${result.status}`}` };
    });
  },

  syncStorage() {
    this.run("sync", async () => {
      await this.save();
      const { result } = await api("/api/image-storage/sync", { method: "POST", body: {} });
      this.results.storage = { ok: !result.failed, text: `同步完成：上传 ${result.uploaded}，跳过 ${result.skipped}，失败 ${result.failed}` };
    });
  },

  testRuntimeProxy() {
    this.run("test-runtime", async () => {
      await this.save();
      const { result } = await api("/api/proxy/test", { method: "POST", body: { url: "" } });
      this.results.runtime = { ok: result.ok, text: result.ok ? `代理可用：HTTP ${result.status}，${result.latency_ms} ms，来源 ${result.proxy_source}` : `代理不可用：${result.error}（${result.latency_ms} ms）` };
    });
  },

  testClearance() {
    this.run("test-clearance", async () => {
      await this.save();
      const { result } = await api("/api/proxy/clearance/test", { method: "POST", body: { target_url: this.targetUrl } });
      this.results.clearance = { ok: result.ok, text: result.ok ? `获取成功：${result.has_cookies ? "已取得 Cookie" : "未取得 Cookie"}，${result.latency_ms} ms` : `获取失败：${result.error ?? result.status}（${result.latency_ms} ms）` };
    });
  },
}));

/* ---------- 页面：docs ---------- */
const docs = [
  {
    title: "模型列表", method: "GET", path: "/v1/models",
    input: [["Authorization", "header", "Bearer <auth-key>。"]],
    output: [["data", "array", "模型列表，包含 id、object、created、owned_by，生图模型额外带 type 为 image。"]],
    example: (base, key) => `curl ${base}/v1/models \\
  -H "Authorization: Bearer ${key}"`,
  },
  {
    title: "聊天补全", method: "POST", path: "/v1/chat/completions",
    input: [["model", "string", "模型名，例如 gpt-6-mini，也可用于图片兼容场景。"], ["messages", "array", "OpenAI 兼容消息数组。"], ["stream", "boolean", "可选，是否流式返回。"], ["n", "number", "可选，图片兼容场景会解析为生成数量。"]],
    output: [["id", "string", "响应 ID。"], ["choices", "array", "OpenAI 兼容 choices。"], ["usage", "object", "可选，token 使用信息。"]],
    example: (base, key) => `curl ${base}/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{"model":"gpt-6-mini","messages":[{"role":"user","content":"你好"}]}'`,
  },
  {
    title: "Responses", method: "POST", path: "/v1/responses",
    input: [["model", "string", "模型名。"], ["input", "string | array | object", "用户输入，图片生成会从中解析提示词。"], ["tools", "array", "可选，传入 web_search 可开启联网搜索。"], ["stream", "boolean", "可选，是否流式返回。"]],
    output: [["id", "string", "响应 ID。"], ["output", "array", "Responses 兼容输出。"], ["status", "string", "响应状态。"]],
    example: (base, key) => `curl ${base}/v1/responses \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{"model":"gpt-6-mini","input":"搜索 ChatGPT 最新动态","tools":[{"type":"web_search"}]}'`,
  },
  {
    title: "图片生成", method: "POST", path: "/v1/images/generations",
    input: [["prompt", "string", "图片生成提示词。"], ["model", "string", "可选，默认为生图模型。"], ["n", "number", "可选，生成数量，当前限制 1-4。"], ["size", "string", "可选，图片尺寸。"], ["quality", "string", "可选，默认 auto。"], ["response_format", "string", "可选，默认 b64_json。"]],
    output: [["data", "array", "图片结果列表。"], ["data[].b64_json", "string", "base64 图片内容。"], ["data[].url", "string", "部分配置下返回图片 URL。"]],
    example: (base, key) => `curl ${base}/v1/images/generations \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${key}" \\
  -d '{"model":"gpt-image-2.6","prompt":"一张极简产品海报","n":1}'`,
  },
  {
    title: "图片编辑", method: "POST", path: "/v1/images/edits",
    input: [["image", "file | file[] | URL", "参考图，支持 multipart 上传，也支持 JSON 图片链接。"], ["prompt", "string", "编辑提示词。"], ["model", "string", "可选，默认为生图模型。"], ["n", "number", "可选，生成数量，当前限制 1-4。"], ["size", "string", "可选，图片尺寸。"], ["quality", "string", "可选，默认 auto。"]],
    output: [["data", "array", "编辑后的图片结果列表。"], ["data[].b64_json", "string", "base64 图片内容。"], ["data[].url", "string", "部分配置下返回图片 URL。"]],
    example: (base, key) => `curl ${base}/v1/images/edits \\
  -H "Authorization: Bearer ${key}" \\
  -F "model=gpt-image-2.6" \\
  -F "prompt=改成赛博朋克夜景" \\
  -F "image=@./input.png"`,
  },
  {
    title: "语音合成", method: "POST", path: "/v1/audio/speech",
    input: [["input", "string", "要合成的文本，必填。"], ["voice", "string", "可选，官网音色 juniper/maple/cove/breeze/orbit/glimmer/ember/fathom/vale，也兼容 alloy/ash/coral 等 OpenAI 音色名。"], ["response_format", "string", "可选，音频格式，默认 mp3。"], ["model", "string", "可选，仅回显用途。"]],
    output: [["binary", "audio", "音频二进制内容，Content-Type 形如 audio/mpeg。"], ["error", "object", "失败时返回 { detail: { error } }。"]],
    example: (base, key) => `curl ${base}/v1/audio/speech \\
  -H "Authorization: Bearer ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"gpt-tts","input":"你好，这是一段语音合成的测试。","voice":"alloy"}' \\
  --output speech.mp3`,
  },
  {
    title: "语音转写", method: "POST", path: "/v1/audio/transcriptions",
    input: [["file", "file", "音频文件，必填，multipart 上传。"], ["response_format", "string", "可选，传 text 时返回纯文本。"], ["model", "string", "可选，仅回显用途。"]],
    output: [["text", "string", "转写出的文本内容。"]],
    example: (base, key) => `curl ${base}/v1/audio/transcriptions \\
  -H "Authorization: Bearer ${key}" \\
  -F "file=@speech.mp3" \\
  -F "model=gpt-transcribe"`,
  },
  {
    title: "任务状态查询", method: "GET", path: "/api/tasks?type={type}&ids={taskId1,taskId2}",
    input: [["type", "string", "可选，逗号分隔任务类型：image_generation、image_edit。"], ["ids", "string", "可选，逗号分隔数据库任务 ID；不传则返回当前用户任务。"]],
    output: [["items", "array", "任务列表，每个任务的 results 是关系化产物列表。"], ["missing_ids", "string[]", "查询指定 ids 时，返回未找到的任务 ID。"], ["items[].results[].url", "string", "图片或文件下载地址。"]],
    example: (base, key) => `curl "${base}/api/tasks?type=image_generation&ids=<task_id>" \\
  -H "Authorization: Bearer ${key}"`,
  },
];

Alpine.data("docs", () => ({
  docs,
  base: location.origin,
  key: session.get().key,
  models: [],
  guides: [["overview", "接入说明"], ["authentication", "身份认证"], ["models", "可用模型"]],
  active: "overview",

  init() {
    api("/v1/models").then((result) => this.models = result.data.map((model) => model.id)).catch((error) => toast(error.message));
  },

  jump(id) {
    this.active = id;
    document.getElementById(id).scrollIntoView({ behavior: "smooth" });
  },
}));

/* ---------- 路由与全局状态 ---------- */
const ADMIN = "admin";

/** 路由表：page 对应 index.html 中的 <template id="page-<page>"> 与同名 Alpine 组件，role 为可访问角色，bare 表示不显示侧栏。 */
const routes = {
  "/login": { page: "login", bare: true },
  "/overview": { page: "overview", role: ADMIN },
  "/chat": { page: "chat" },
  "/accounts": { page: "accounts", role: ADMIN },
  "/keys": { page: "keys", role: ADMIN },
  "/gallery": { page: "gallery", role: ADMIN },
  "/logs": { page: "logs", role: ADMIN },
  "/settings": { page: "settings", role: ADMIN },
  "/docs": { page: "docs", role: ADMIN },
};

const adminNav = [
  { group: "创作" },
  { path: "/chat", label: "创作台", icon: "message-circle" },
  { group: "管理" },
  { path: "/overview", label: "概览", icon: "layout-dashboard" },
  { path: "/accounts", label: "号池", icon: "users-round" },
  { path: "/keys", label: "密钥", icon: "key-round" },
  { path: "/gallery", label: "图库", icon: "images" },
  { path: "/logs", label: "日志", icon: "scroll-text" },
  { path: "/settings", label: "设置", icon: "settings-2" },
  { group: "文档" },
  { path: "/docs", label: "API", icon: "book-open" },
];

const homeOf = (role) => role === ADMIN ? "/overview" : "/chat";

function parseChangelog(content) {
  return content.split(/^## /m).slice(1).map((block) => {
    const [title, ...lines] = block.split("\n");
    const [version, date = ""] = title.split(" - ");
    const items = lines.flatMap((line) => {
      const match = line.match(/^\+ \[(.+?)\] (.+)$/);
      return match ? [{ type: match[1], content: match[2] }] : [];
    });
    return { version, date, items };
  }).filter((release) => release.items.length);
}

Alpine.store("app", {
  session: session.get(),
  path: "",
  bare: true,
  navOpen: false,
  version: "",
  latest: "",
  releases: [],
  releasesOpen: false,
  checking: false,
  get admin() {
    return this.session?.role === ADMIN;
  },
  get nav() {
    return !this.bare && this.admin;
  },
  get navItems() {
    return adminNav;
  },
  get hasUpdate() {
    const [latest, current] = [this.latest, this.version].map((value) => value.split(".").map(Number));
    const index = latest.findIndex((value, position) => value !== current[position]);
    return Boolean(this.latest) && index >= 0 && latest[index] > current[index];
  },
  async openReleases() {
    this.releasesOpen = true;
    this.checking = true;
    const base = "https://raw.githubusercontent.com/basketikun/chatgpt2api/main";
    const [version, changelog] = await Promise.all([fetch(`${base}/VERSION`).then((r) => r.text()), fetch(`${base}/CHANGELOG.md`).then((r) => r.text())]).finally(() => this.checking = false);
    this.latest = version.split("\n")[0];
    this.releases = parseChangelog(changelog);
  },
  logout() {
    session.clear();
    this.session = null;
    navigate("/login");
  },
});

Alpine.store("toast", { items: [] });

Alpine.store("confirm", {
  open: false,
  title: "",
  text: "",
  ok: "",
  danger: true,
  resolve: null,
  done(result) {
    this.open = false;
    this.resolve(result);
  },
});

Alpine.store("lightbox", { open: false, images: [], index: 0, zoom: false });

Alpine.magic("time", () => fmtTime);
Alpine.magic("short", () => fmtShort);
Alpine.magic("num", () => fmtNumber);
Alpine.magic("bytes", () => fmtBytes);
Alpine.magic("duration", () => fmtDuration);
Alpine.magic("md", () => markdown);
Alpine.magic("copy", (el) => (text) => copyText(text, el));
Alpine.magic("go", () => navigate);

/** 切换页面：校验登录与角色后加载页面模板和脚本，渲染进主内容区。 */
function navigate(target, replace = false) {
  const app = Alpine.store("app");
  app.session = session.get();
  let path = target;
  const route = routes[path];
  if (!app.session) path = "/login";
  else if (!route || path === "/login" || (route.role && route.role !== app.session.role)) path = homeOf(app.session.role);
  history[replace || path !== target ? "replaceState" : "pushState"](null, "", path);
  app.path = path;
  const { page, bare = false } = routes[path];
  app.bare = bare;
  document.getElementById("view").innerHTML = document.getElementById(`page-${page}`).innerHTML;
  document.getElementById("view").scrollTop = 0;
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[href^='/']");
  if (!link || link.target || link.hasAttribute("download") || event.metaKey || event.ctrlKey) return;
  event.preventDefault();
  navigate(link.getAttribute("href"));
});

addEventListener("popstate", () => location.pathname !== Alpine.store("app").path && navigate(location.pathname, true));

window.Alpine = Alpine;
Alpine.start();
fetch("/version").then((response) => response.json()).then((data) => Alpine.store("app").version = data.version);
navigate(location.pathname, true);

