# AGENTS.md

## 前端（`web/`）

- 无构建的 HTML + CSS + JS 三文件：daisyUI 5 提供组件样式，Alpine.js 负责交互。`index.html` 放外壳与各页面模板 `<template id="page-<名>">`，`index.css` 放 Token 与样式，`index.js` 放请求、通用函数、Web Components 与页面组件。
- 新增页面：加 `<template id="page-<名>">`，根节点 `x-data="<名>"`；`index.js` 用 `Alpine.data("<名>", ...)` 注册，并在 `routes` 与导航登记；定时器、图表在 `destroy()` 中释放。
- 样式只用 `index.css` 开头的语义 Token，不写裸色值和裸像素：
  - 字号：正文 13px，辅助 12px，区块标题 14px，页面标题 18px，指标数字 24px。
  - 间距：4 的倍数（`--space-1…12`），控件内 4–8，组件内 12–16，区块间 24，页面边距 32。
  - 控件高度 24 / 32 / 40，后台默认 `sm`。
  - 圆角取 `--radius-control` / `--radius-panel` / `--radius-dialog`；子元素圆角 = 父圆角 − 内边距。
  - 卡片用 `--color-surface-muted` 灰底，不加描边；表格、表单、侧栏等主体区域保持白底，表格直接铺在页面上用行线区分；阴影只给下拉、弹窗。
  - 输入框、下拉、复选框用浅描边，聚焦只加深边框；选中状态用浅灰描边。
- 布局：内容页根节点 `.page`，首行 `.page-head`；全高工作区用 `.workspace`；排列用 `.vstack`、`.row`、`.grid`；卡片 `.panel`，主体区域 `.panel.panel-flush`。普通页面只保留一层纵向滚动，表格、列表不设限高。
- 设置页：左侧 `.settings-nav` + `.nav-item` 分组，右侧每行 `.setting-row`（名称加一行说明在左，控件在右），长控件用 `.setting-row-block`；右上角放「撤销」与「保存」，无改动时禁用，有未保存改动的分组显示圆点，保存只提交有改动的分组。
- 弹窗默认 560px 宽，`modal-md` 720px，`modal-wide` 880px，高度内部滚动；详情多时在 `.modal-head` 放分段控件分 Tab，关闭按钮放标题行右侧，关键状态用 `.inline-stats`。
- 组件选择：
  - 主操作 `btn btn-sm btn-primary`，一个区域只放一个；普通 `btn btn-sm`；次要与行内 `btn btn-ghost btn-sm`（纯图标加 `btn-square`、`aria-label`、`tooltip`）；删除 `btn btn-sm btn-error btn-soft` + `confirmDialog()`。
  - 同一数据的视图切换 `tabs tabs-box tabs-sm`；业务区块切换 `tabs tabs-border`。
  - 立即生效的开关 `toggle toggle-sm`；随表单保存的布尔项：设置页用「开启 / 关闭」分段控件，其他表单用 `checkbox checkbox-sm` + `.check-row`。
  - 选项用 `<ui-select>`（多选加 `multiple`，值为数组），日期用 `<ui-date>`，分页用 `<ui-pager>`，只读状态用 `badge badge-sm badge-soft`。
  - 字段说明用标签后的 `info` 图标 + `tooltip`；页面级问题用 `alert alert-soft alert-warning`；失败提示用 `toast(text, type)`；空状态 `.empty` + 图标 + 一句话；加载用 `skeleton` 或 `loading loading-spinner loading-xs`。
  - 可复制字段用 `.copyable` + `$copy`。
- 文案：只写标题、字段名与关键数值，说明收进提示气泡；用书面简短的业务语言；按钮写动作，表头写业务名称；失败时显示真实原因。
- 脚本：请求统一 `api(path, { method, body })`（二进制 `api.blob`，流式 `api.stream`），页面里直接写路径；模板魔法方法 `$time`、`$short`、`$num`、`$bytes`、`$duration`、`$md`、`$copy`、`$go`；全局函数 `toast`、`confirmDialog`、`lightbox`、`copyText`、`markdown`、`saveBlob`、`readDataUrl`、`urlToFile`、`sleep`；图标 `<ui-icon name="...">`（见 `index.html` 开头的图标集）。
- 自定义类名避开 daisyUI 已占用的名字（`stack`、`stat`、`chat`、`prose`），布局用 `vstack`、`row`、`grid`，指标卡用 `metric-*`，Markdown 正文用 `markdown`。
