[中文](README.md) · [English](README.en.md) · [Tiếng Việt](README.vi.md)

<h1 align="center">ChatGPT2API</h1>


<p align="center">ChatGPT2API chủ yếu áp dụng kỹ thuật đảo ngược để tổng hợp và đóng gói lại các năng lực liên quan của trang chủ ChatGPT, cung cấp API / proxy ảnh tương thích OpenAI cho các tình huống tạo ảnh, chỉnh sửa ảnh và chỉnh sửa ghép nhiều ảnh của ChatGPT, đồng thời tích hợp tính năng vẽ ảnh trực tuyến, quản lý kho tài khoản, nhiều cách nhập tài khoản và khả năng triển khai tự lưu trữ bằng Docker.</p>

> [!WARNING]
> Tuyên bố miễn trừ trách nhiệm:
>
> Dự án này liên quan đến việc nghiên cứu kỹ thuật đảo ngược đối với các giao diện tạo văn bản, tạo ảnh và chỉnh sửa ảnh trên trang chủ ChatGPT, chỉ phục vụ mục đích học tập cá nhân, nghiên cứu kỹ thuật và trao đổi kỹ thuật phi thương mại.
>
> - Nghiêm cấm sử dụng dự án này cho bất kỳ mục đích thương mại, sử dụng vì lợi nhuận, thao tác hàng loạt, lạm dụng tự động hóa hoặc gọi với quy mô lớn nào.
> - Nghiêm cấm sử dụng dự án này để phá hoại trật tự thị trường, cạnh tranh không lành mạnh, đầu cơ trục lợi, bán lại dịch vụ liên quan, cũng như bất kỳ hành vi nào vi phạm điều khoản dịch vụ của OpenAI hoặc pháp luật, quy định tại địa phương.
> - Nghiêm cấm sử dụng dự án này để tạo ra, phát tán hoặc tiếp tay tạo ra nội dung vi phạm pháp luật, bạo lực, khiêu dâm, liên quan đến trẻ vị thành niên, hoặc dùng cho mục đích lừa đảo, gian lận, quấy rối hay bất kỳ mục đích bất hợp pháp, không phù hợp nào khác.
> - Người dùng phải tự chịu toàn bộ rủi ro, bao gồm nhưng không giới hạn ở việc tài khoản bị hạn chế, tạm khóa hoặc khóa vĩnh viễn, cũng như trách nhiệm pháp lý phát sinh do sử dụng sai quy định.
> - Việc sử dụng dự án này đồng nghĩa với việc bạn đã hiểu rõ và đồng ý toàn bộ nội dung của tuyên bố miễn trừ trách nhiệm này; mọi hậu quả phát sinh từ việc lạm dụng, vi phạm hoặc sử dụng trái pháp luật đều do người dùng tự chịu trách nhiệm.
> - Dự án này được xây dựng dựa trên nghiên cứu kỹ thuật đảo ngược đối với các năng lực liên quan của trang chủ ChatGPT, do đó tiềm ẩn rủi ro tài khoản bị hạn chế, tạm khóa hoặc khóa vĩnh viễn. Vui lòng không dùng tài khoản quan trọng, tài khoản thường dùng hoặc tài khoản có giá trị cao của bạn để thử nghiệm.


## Nhà tài trợ

<table>
  <tr>
    <td width="190" align="center">
      <a href="https://www.atlascloud.ai/zh?utm_source=github&utm_medium=link&utm_campaign=chatgpt2api"><img src="assets/atlascloud.svg" width="163" alt="Atlas Cloud"></a>
    </td>
    <td>
      <a href="https://www.atlascloud.ai/zh?utm_source=github&utm_medium=link&utm_campaign=chatgpt2api">Atlas Cloud</a> is a full-modal AI inference platform that gives developers a single AI API to access video generation, image generation, and LLM APIs. Instead of managing multiple vendor integrations, you connect once and get unified access to 300+ curated models across all modalities. Check out <a href="https://www.atlascloud.ai/console/coding-plan">Atlas Cloud's new coding plan promotion</a> for more budget-friendly API access.
    </td>
  </tr>
</table>

## Bắt đầu nhanh

### Chạy bằng Docker

```bash
git clone git@github.com:basketikun/chatgpt2api.git
cd chatgpt2api
docker compose up -d
```

Trước khi khởi động, hãy thiết lập `auth-key` trong `config.json`, hoặc có thể ghi đè bằng `CHATGPT2API_AUTH_KEY` trong `docker-compose.yml`.

- Bảng điều khiển web: `http://localhost:3000`
- Địa chỉ API: `http://localhost:3000/v1`
- Thư mục dữ liệu: `./data`

### Triển khai proxy ổn định WARP / FlareSolverr

Nếu luồng xử lý ảnh thường xuyên gặp phải chặn của Cloudflare, bạn có thể bật giải pháp WARP + Privoxy + FlareSolverr đi kèm:

```bash
cp .env.example .env
docker compose -f docker-compose.warp.yml up -d --build
```

Compose này sẽ khởi động:

- `warp-proxy`: cung cấp lối ra WARP SOCKS5.
- `privoxy`: chuyển proxy WARP SOCKS5 thành proxy HTTP.
- `flaresolverr`: làm mới clearance của Cloudflare.
- `init-config`: ghi cấu hình mặc định `proxy_runtime` theo kiểu idempotent.
- `app`: khởi động dịch vụ chính của ChatGPT2API.

Mặc định chỉ các request upstream tới OpenAI / ChatGPT mới đi qua proxy ổn định; các luồng phụ trợ như email tài khoản, CPA sẽ không bị bắt buộc tiếp quản. Proxy do tài khoản tự cấu hình có độ ưu tiên cao nhất, tiếp theo là runtime proxy ổn định, sau đó đến proxy tường minh và proxy toàn cục kiểu cũ.

Bạn có thể điều chỉnh cổng và các tham số runtime proxy trong `.env`, hoặc lưu thủ công, kiểm tra proxy và kiểm tra clearance trong khung "Runtime proxy ổn định" ở trang cài đặt hệ thống.

### Phát triển cục bộ

Khởi động backend:

```bash
git clone git@github.com:basketikun/chatgpt2api.git
cd chatgpt2api
uv sync
uv run main.py
```

Khởi động frontend:

```bash
cd chatgpt2api/web
bun install
bun run dev
```

Cập nhật lên phiên bản mới sau này:

```bash
docker pull ghcr.io/basketikun/chatgpt2api:latest
docker-compose down
docker-compose up -d

```

### Cấu hình backend lưu trữ

Hỗ trợ chuyển đổi phương thức lưu trữ thông qua biến môi trường `STORAGE_BACKEND`:

- `json` - tệp JSON cục bộ (mặc định)
- `sqlite` - cơ sở dữ liệu SQLite cục bộ
- `postgres` - PostgreSQL bên ngoài (cần cấu hình `DATABASE_URL`)
- `git` - kho Git riêng tư (cần cấu hình `GIT_REPO_URL` và `GIT_TOKEN`)

Ví dụ: sử dụng PostgreSQL

```yaml
environment:
  - STORAGE_BACKEND=postgres
  - DATABASE_URL=postgresql://user:password@host:5432/dbname
```

## Tính năng

### Khả năng tương thích API

- Tương thích endpoint tạo ảnh `POST /v1/images/generations`
- Tương thích endpoint chỉnh sửa ảnh `POST /v1/images/edits`
- Tương thích `POST /v1/chat/completions` hướng tới các tình huống ảnh
- Tương thích `POST /v1/responses` hướng tới các tình huống ảnh
- `GET /v1/models` trả về `gpt-image-2`, `codex-gpt-image-2`, `auto`, `gpt-5`, `gpt-5-1`, `gpt-5-2`, `gpt-5-3`, `gpt-5-3-mini`,
  `gpt-5-mini`
- Hỗ trợ trả về nhiều kết quả tạo ảnh thông qua `n`
- Hỗ trợ tạo tệp PPT có thể chỉnh sửa
- Hỗ trợ tạo tệp PSD có thể chỉnh sửa
- Hỗ trợ truy cập endpoint vẽ ảnh trong Codex thông qua kỹ thuật đảo ngược, chỉ khả dụng với các gói đăng ký `Plus` / `Team` / `Pro`, bí danh model là `codex-gpt-image-2`, nếu cần bạn có thể tự ánh xạ lại về
  `gpt-image-2` ở các tình huống khác để phân biệt với vẽ ảnh trên trang chủ; điều này cũng có nghĩa là cùng một tài khoản sẽ có đồng thời hai hạn mức tạo ảnh riêng, một cho trang chủ và một cho Codex

### Tính năng vẽ ảnh trực tuyến

- Tích hợp sẵn không gian làm việc vẽ ảnh trực tuyến, hỗ trợ tạo ảnh, chỉnh sửa ảnh và chỉnh sửa ghép nhiều ảnh
- Hỗ trợ chọn model `gpt-image-2`, `codex-gpt-image-2`, `auto`, `gpt-5`, `gpt-5-1`, `gpt-5-2`, `gpt-5-3`, `gpt-5-3-mini`, `gpt-5-mini`
- Chế độ chỉnh sửa hỗ trợ tải lên ảnh tham chiếu
- Frontend hỗ trợ tương tác tạo nhiều ảnh
- Lưu lịch sử phiên ảnh trên máy, hỗ trợ xem lại, xóa và xóa toàn bộ
- Hỗ trợ cache URL ảnh phía server
- Theo dõi tiến độ tạo ảnh, có thể tiếp tục chờ sau khi hết thời gian chờ
- Tải chậm (lazy load) ảnh và ghi nhớ vị trí cuộn, tối ưu hiệu năng khi có nhiều ảnh

### Tính năng quản lý kho tài khoản

- Tự động làm mới email, loại, hạn mức và thời gian hồi phục của tài khoản (theo dõi tiến độ bất đồng bộ)
- Luân phiên các tài khoản khả dụng để thực hiện tạo ảnh và chỉnh sửa ảnh
- Tự động loại bỏ token không hợp lệ khi gặp lỗi dạng token hết hạn
- Định kỳ kiểm tra các tài khoản bị giới hạn tốc độ và tự động làm mới
- Hỗ trợ đăng nhập lại bằng mật khẩu để khôi phục tài khoản bất thường, có thể tự động đăng nhập lại sau khi làm mới
- Hỗ trợ cấu hình proxy HTTP / HTTPS / SOCKS5 / SOCKS5H toàn cục từ giao diện web
- Hỗ trợ runtime proxy ổn định WARP / FlareSolverr
- Hỗ trợ tìm kiếm, lọc, làm mới hàng loạt, xuất, chỉnh sửa thủ công và dọn dẹp tài khoản
- Hỗ trợ bốn cách nhập tài khoản: nhập tệp CPA JSON cục bộ, nhập từ máy chủ CPA từ xa, nhập từ máy chủ `sub2api`, nhập `access_token`
- Hỗ trợ cấu hình máy chủ `sub2api` trong trang cài đặt, lọc và nhập hàng loạt tài khoản OpenAI OAuth từ đó

### Thử nghiệm / Đang lên kế hoạch

- Xem trạng thái chi tiết tại: [Danh sách tính năng](./docs/feature-status.en.md)

## Ảnh chụp màn hình

<table width="100%">
  <tr>
    <td width="50%"><img src="https://i.ibb.co/Jj8nfwwP/image.png" alt="image" border="0"></td>
    <td width="50%"><img src="https://i.ibb.co/pqf235v/image-edit.png" alt="image edit" border="0"></td>
  </tr>
  <tr>
    <td width="50%"><img src="https://i.ibb.co/tPcqtVfd/chery-studio.png" alt="chery studio" border="0"></td>
    <td width="50%"><img src="https://i.ibb.co/PsT9YHBV/account-pool.png" alt="account pool" border="0"></td>
  </tr>
  <tr>
    <td width="50%"><img src="https://i.ibb.co/rRWLG08q/new-api.png" alt="new api" border="0"></td>
  </tr>
</table>

## API

Tất cả các endpoint AI đều yêu cầu header:

```http
Authorization: Bearer <auth-key>
```

<details>
<summary><code>GET /v1/models</code></summary>
<br>

Trả về danh sách các model ảnh hiện đang được cung cấp.

```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer <auth-key>"
```

<details>
<summary>Giải thích</summary>
<br>

| Trường | Giải thích                                                                                                 |
|:-----|:-----------------------------------------------------------------------------------------------------------|
| Model trả về | `gpt-image-2`, `codex-gpt-image-2`, `auto`, `gpt-5`, `gpt-5-1`, `gpt-5-2`, `gpt-5-3`, `gpt-5-3-mini`, `gpt-5-mini` |
| Tình huống tích hợp | Có thể tích hợp vào các upstream hoặc client như Cherry Studio, New API |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/images/generations</code></summary>
<br>

Endpoint tạo ảnh tương thích OpenAI, dùng để tạo ảnh từ văn bản.

```bash
curl http://localhost:8000/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "一只漂浮在太空里的猫",
    "n": 1,
    "response_format": "b64_json"
  }'
```

<details>
<summary>Giải thích trường</summary>
<br>

| Trường                | Giải thích                                                 |
|:------------------|:---------------------------------------------------|
| `model`           | Model ảnh, giá trị hợp lệ hiện tại theo kết quả trả về của `/v1/models`, khuyến nghị dùng `gpt-image-2` |
| `prompt`          | Prompt tạo ảnh                                            |
| `n`               | Số lượng tạo ra, backend hiện giới hạn ở mức `1-4`                                 |
| `response_format` | Trường này hiện có mặt trong model request, giá trị mặc định là `b64_json`                       |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/images/edits</code></summary>
<br>

Endpoint chỉnh sửa ảnh tương thích OpenAI, có thể tải lên tệp ảnh, hoặc truyền link ảnh theo định dạng JSON chính thức để tạo kết quả chỉnh sửa.

```bash
curl http://localhost:8000/v1/images/edits \
  -H "Authorization: Bearer <auth-key>" \
  -F "model=gpt-image-2" \
  -F "prompt=把这张图改成赛博朋克夜景风格" \
  -F "n=1" \
  -F "image=@./input.png"
```

Cũng có thể truyền trực tiếp URL ảnh:

```bash
curl http://localhost:8000/v1/images/edits \
  -H "Authorization: Bearer <auth-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "把这张图改成赛博朋克夜景风格",
    "images": [
      {"image_url": "https://example.com/input.png"}
    ]
  }'
```

<details>
<summary>Giải thích trường</summary>
<br>

| Trường          | Giải thích                                            |
|:------------|:-----------------------------------------------|
| `model`     | Model ảnh, `gpt-image-2`                           |
| `prompt`    | Prompt chỉnh sửa ảnh                                       |
| `n`         | Số lượng tạo ra, backend hiện giới hạn ở mức `1-4`                            |
| `image`     | Tệp ảnh cần chỉnh sửa, tải lên bằng multipart/form-data           |
| `images`    | Mảng JSON tham chiếu ảnh, hỗ trợ `{"image_url": "https://..."}` |
| `image_url` | Ở chế độ form cũng có thể truyền trực tiếp link ảnh, hỗ trợ lặp lại trường này để truyền nhiều ảnh                     |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/chat/completions</code></summary>
<br>

Endpoint tương thích Chat Completions hướng tới các tình huống văn bản, tìm kiếm web và ảnh, không phải một proxy chat đa năng đầy đủ.

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "model": "gpt-image-2",
    "messages": [
      {
        "role": "user",
        "content": "生成一张雨夜东京街头的赛博朋克猫"
      }
    ],
    "n": 1
  }'
```

<details>
<summary>Giải thích trường</summary>
<br>

| Trường                   | Giải thích                                                                           |
|:---------------------|:-----------------------------------------------------------------------------|
| `model`              | Model văn bản, tìm kiếm hoặc ảnh; model tìm kiếm sẽ kích hoạt logic tương thích tìm kiếm web                                                   |
| `messages`           | Mảng tin nhắn, hỗ trợ nội dung request dạng văn bản, tìm kiếm và ảnh                                                          |
| `n`                  | Số lượng ảnh tạo ra, theo cách triển khai hiện tại được diễn giải là số lượng ảnh                                                          |
| `stream`             | Được hỗ trợ ở cả ba tình huống văn bản, tìm kiếm và ảnh, vẫn đang trong giai đoạn thử nghiệm                                                           |
| `tools`              | Tình huống văn bản hỗ trợ `web_search` / `web_search_preview` / `web_search_preview_2025_03_11` |
| `web_search_options` | Khi được truyền vào sẽ kích hoạt logic tương thích tìm kiếm web                                                               |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/responses</code></summary>
<br>

Endpoint tương thích Responses API hướng tới văn bản, tìm kiếm web và gọi tool tạo ảnh, không phải một proxy Responses API đa năng đầy đủ.

```bash
curl http://localhost:8000/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "model": "gpt-5",
    "input": "生成一张未来感城市天际线图片",
    "tools": [
      {
        "type": "image_generation"
      }
    ]
  }'
```

<details>
<summary>Giải thích trường</summary>
<br>

| Trường       | Giải thích                                                                                      |
|:---------|:----------------------------------------------------------------------------------------|
| `model`  | Trường này sẽ được phản hồi lại nguyên trạng trong response; tìm kiếm và tạo ảnh sẽ áp dụng logic tương thích tương ứng                                                             |
| `input`  | Nội dung đầu vào; tìm kiếm dùng đoạn văn bản cuối cùng của người dùng, tạo ảnh cần phân tích ra được prompt                                                          |
| `tools`  | Hỗ trợ `image_generation`, `web_search`, `web_search_preview`, `web_search_preview_2025_03_11` |
| `stream` | Đã triển khai, nhưng vẫn đang trong giai đoạn thử nghiệm                                                                               |

<br>
</details>
</details>

## Hỗ trợ cộng đồng

Học AI, ghé LinuxDO: [LinuxDO](https://linux.do)

## Contributors

Cảm ơn tất cả các nhà phát triển đã đóng góp cho dự án này:

<a href="https://github.com/basketikun/chatgpt2api/graphs/contributors">
  <img alt="Contributors" src="https://contrib.rocks/image?repo=basketikun/chatgpt2api" />
</a>

## Star History

[![Star History Chart](https://api.star-history.com/chart?repos=basketikun/chatgpt2api&type=date&legend=top-left)](https://www.star-history.com/?repos=basketikun%2Fchatgpt2api&type=date&legend=top-left)
