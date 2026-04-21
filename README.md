# chatgpt2api

本项目仅供学习与研究交流。请务必遵循 OpenAI 的使用条款及当地法律法规，不得用于非法用途！

ChatGPT 图片生成代理与账号池管理面板，提供账号维护、额度刷新和图片生成接口。

## 功能

- 兼容 OpenAI `Chat Completions` 图片响应
- 兼容 OpenAI `Responses API` 图片生成接口
- 支持图生图与参考图编辑
- 支持导入 CPA 格式文件
- 支持多种方式导入 `access_token`
- 自动刷新账号邮箱、类型、图片额度、恢复时间
- 轮询可用账号进行图片生成
- 失效 Token 自动剔除
- 提供 Web 后台管理账号和生成图片 

> 当前已支持文生图和图生图。`gpt-image-2` 仍未单独适配，默认仍走现有 ChatGPT 上游模型映射。

生图界面：

![image](assets/image.png)

Chery Studio 中使用：

![image](assets/chery_studio.png)

号池管理：

![image](assets/account_pool.png)

## 接口

所有接口都需要请求头：

```http
Authorization: Bearer <auth-key>
```

### 图片生成

```http
POST /v1/images/generations
```

```http
POST /v1/images/edits
```

```http
POST /v1/chat/completions
```

```http
POST /v1/responses
```

请求体示例：

```json
{
  "prompt": "a cyberpunk cat walking in rainy Tokyo street",
  "model": "gpt-image-1",
  "n": 1,
  "response_format": "b64_json"
}
```

图生图请求体示例：

```json
{
  "prompt": "保留主体动作，改成电影海报质感",
  "model": "gpt-image-1",
  "images": [
    {
      "name": "source.png",
      "image_url": "data:image/png;base64,<base64>"
    }
  ]
}
```

说明：

- `/v1/images/edits` 当前支持 JSON 方式传入参考图，`image` 或 `images` 都可以，值支持远程 URL 或 data URL。
- `/v1/chat/completions` 支持在 `messages[].content` 里带 `image_url`，即使 `model` 不是 `gpt-image-*`，只要消息里有图片附件也会按生图请求处理。
- `/v1/responses` 支持在 `input[].content` 里带 `input_image`。

## 部署

```bash
git clone git@github.com:basketikun/chatgpt2api.git
# 首次启动会自动生成 config.json，也可以手动复制后修改
# cp config.example.json config.json
# 可按需编辑 config.json 的密钥和 `refresh_account_interval_minute`
docker compose up -d
```

## 社区支持
学 AI , 上 L 站

[LinuxDO](https://linux.do)
