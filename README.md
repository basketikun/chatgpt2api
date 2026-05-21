# 🚀 ChatGPT2API - Ultimate AI Gateway & VN MCP Hub

**ChatGPT2API** là dự án toàn diện cho phép biến tài khoản ChatGPT Web của bạn thành một API chuẩn OpenAI, đồng thời đóng vai trò là một **AI Agent Backend** mạnh mẽ. Phiên bản này được thiết kế tối ưu hóa đặc biệt cho các hệ thống nhà thông minh như **Home Assistant** (đặc biệt là lọc sạch định dạng để Loa thông minh TTS có thể đọc tự nhiên 100%), cũng như hoàn hảo cho **Open WebUI**, **n8n** và bất kỳ ứng dụng nào hỗ trợ chuẩn OpenAI API.

Kèm theo đó là **VN MCP Hub (Model Context Protocol Hub)** - Cung cấp hơn 20+ custom MCP servers giúp mở rộng bộ não AI của bạn với khả năng tìm kiếm web (Search), cập nhật thời tiết, tin tức, tài chính, luật pháp và hệ thống RAG (Knowledge Base).

---

## 🌟 Tính Năng Nổi Bật

### 🧠 Core ChatGPT2API
- **10+ AI Provider**: Hỗ trợ ChatGPT Web (Free/Plus), Codex OAuth, OpenCode (Free không cần tài khoản), Gemini (Free AI Studio), DeepSeek, Groq, Mistral, NVIDIA NIM, v.v.
- **Model Combo Orchestration**: Cơ chế tự động chuyển đổi (fallback) thông minh. Nếu API A lỗi, tự động chuyển sang API B mà không làm gián đoạn trải nghiệm người dùng.
- **Tối ưu hóa Loa Thông Minh (TTS)**: Bộ lọc RTK thông minh tự động loại bỏ các định dạng Markdown (`#`, `*`, `-`) giúp giọng nói mượt mà, tự nhiên.
- **Web Dashboard**: Giao diện quản lý trực quan cho phép thêm tài khoản, cấu hình model, theo dõi token và backup dễ dàng.
- **RTK Token Optimizer**: Thuật toán tiết kiệm 60-90% lượng token tiêu thụ mà vẫn giữ nguyên chất lượng câu trả lời.

### 🔌 VN MCP Hub
- **8 MCP VN Core**: Tích hợp sẵn Thời tiết (4 nguồn), Tin tức (6 nguồn), Tỷ giá/Vàng, Lịch Âm, Tìm kiếm DuckDuckGo, Tra cứu Luật, Phạt nguội, Chứng khoán.
- **7 Knowledge Base RAG**: Dữ liệu điện nước, y tế sơ cứu, giáo dục, ngoại ngữ, khoa học, tự nhiên và xã hội Việt Nam.
- **Federated Multi-Search**: 9 Search engines quốc tế chạy song song (Brave, Mojeek, PubMed, v.v.).
- **Studio UI**: Quản lý trực quan, tạo KB (Knowledge Base) mới từ Markdown, lưu trữ R2 Cloudflare.

---

## 💻 Yêu Cầu Hệ Thống

| Thành Phần | Tối Thiểu | Khuyến Nghị |
| :--- | :--- | :--- |
| **Hệ Điều Hành** | Linux (Ubuntu/Debian), Raspberry Pi OS, Synology/QNAP | Linux (Ubuntu/Debian) |
| **RAM** | 2GB | 4GB+ (Khuyến nghị nếu chạy kèm Chroma DB của MCP Hub) |
| **Disk** | 5GB | 20GB+ (Dành cho lưu trữ RAG và Cache) |
| **Phần Mềm** | Docker & Docker Compose | Phiên bản Docker mới nhất (24.0+) |

---

## 🚀 Hướng Dẫn Cài Đặt Chi Tiết

Dưới đây là hướng dẫn cài đặt từ dễ đến chuyên sâu trên nhiều nền tảng.

### Cách 1: Cài Đặt Nhanh Bằng Docker Compose (Khuyên dùng)

Cách này sẽ cài đặt đồng thời **ChatGPT2API** và **VN MCP Hub** để bạn có một hệ thống hoàn chỉnh.

1. Khởi tạo thư mục và file cấu hình:
```bash
mkdir -p /opt/chatgpt2api
cd /opt/chatgpt2api
```

2. Tạo file `docker-compose.yml` với nội dung sau:
```yaml
services:
  # Cốt lõi xử lý API
  chatgpt2api:
    image: ghcr.io/tritue2011/chatgpt2api:latest
    container_name: chatgpt2api
    restart: unless-stopped
    ports:
      - "3000:80"
    volumes:
      - ./chatgpt2api-data:/app/data
    environment:
      - CHATGPT2API_AUTH_KEY=mat_khau_cua_ban # ĐỔI MẬT KHẨU NÀY
      - STORAGE_BACKEND=json

  # Hub mở rộng tính năng AI
  vn-mcp-hub:
    image: ghcr.io/tritue2011/vn-mcp-hub:latest
    container_name: vn-mcp-hub
    restart: unless-stopped
    ports:
      - "8005:8005"
    volumes:
      - ./vn_mcp_chroma:/app/chroma_db
      - ./vn_mcp_data:/app/data
```

3. Chạy hệ thống:
```bash
docker compose up -d
```

### Cách 2: Cài Đặt Qua Portainer

1. Truy cập Portainer -> **Stacks** -> **Add stack**.
2. Đặt tên stack là `chatgpt-ai-system`.
3. Trong phần Web editor, dán đoạn mã `docker-compose.yml` phía trên vào.
4. Chỉnh sửa `CHATGPT2API_AUTH_KEY` thành mật khẩu bảo mật của bạn.
5. Cuộn xuống và bấm **Deploy the stack**.

---

## 🎛️ Đào Sâu Dashboard ChatGPT2API (Hướng Dẫn Chi Tiết Từng Tab)

Sau khi cài đặt xong, bạn truy cập vào trang quản trị tại `http://[IP_MÁY_CHỦ]:3000` và đăng nhập bằng mật khẩu (Auth Key). Giao diện bên tay trái sẽ gồm các Tab chính, đây là cách làm chủ từng mục:

### 1. Tab Overview (Tổng Quan)
- **Công dụng**: Bảng điều khiển trung tâm theo dõi sức khỏe hệ thống theo thời gian thực.
- **Tính năng**:
  - Xem số lượng Requests đang hoạt động, tỷ lệ Success Rate (Thành công/Lỗi).
  - Biểu đồ thống kê số lượng Token đã tiết kiệm được nhờ thuật toán Optimizer.
  - Theo dõi nhanh số tài khoản đang "Sống" (Active) hay "Chết" (Error).

### 2. Tab Account Pool (Kho Tài Khoản ChatGPT)
- **Công dụng**: Nơi quản lý các tài khoản ChatGPT Web miễn phí và trả phí (Plus/Pro).
- **Cách lấy Access Token an toàn**:
  1. Mở trình duyệt ẩn danh (Incognito), đăng nhập [chatgpt.com](https://chatgpt.com).
  2. Dán link `https://chatgpt.com/api/auth/session` vào thanh địa chỉ.
  3. Copy chuỗi rất dài nằm sau chữ `"accessToken":`. (Chú ý: Đóng cửa sổ, KHÔNG BẤM ĐĂNG XUẤT).
- **Cách sử dụng Tab**:
  - Bấm **Import Access Token**.
  - Dán token của bạn vào (mỗi token một dòng). Bấm Xác nhận.
  - Hệ thống tự động phân loại đây là tài khoản Free hay Plus. Bạn có thể bật/tắt (Toggle) từng tài khoản. Nếu bị báo màu đỏ, nghĩa là Token đã hết hạn, bạn cần xóa và nạp lại.

### 3. Tab Providers (Nhà Cung Cấp Bên Thứ 3)
- **Công dụng**: Dùng khi bạn không muốn phụ thuộc hoàn toàn vào ChatGPT mà muốn dùng thêm Gemini, DeepSeek, Groq.
- **Cách sử dụng**:
  - Bấm chọn nhà cung cấp (Ví dụ: **Gemini AI Studio**).
  - Dán API Key lấy từ trang của Google vào ô trống.
  - Bấm **Save**. Bây giờ hệ thống đã sẵn sàng dùng các Model của bên thứ 3 bằng prefix tương ứng (như `gemini_free/auto`).

### 4. Tab Combos (Định Tuyến & Fallback Thông Minh - Quan Trọng Nhất)
- **Công dụng**: Tạo ra một luồng xử lý thông minh để AI không bao giờ bị "đơ" nếu một nguồn bị lỗi.
- **Cách cấu hình "Bất Tử"**:
  1. Bấm **Create Combo**. Đặt tên dễ nhớ: `AI Agent`.
  2. Tại phần Fallback Chain, thêm theo thứ tự từ xịn đến dự phòng:
     - Dòng 1: `cx/auto` (Codex OAuth - xịn nhất nếu bạn có).
     - Dòng 2: `chatgpt/auto` (Tài khoản ChatGPT thường).
     - Dòng 3: `gemini_free/auto` (Google Gemini API dự phòng 1).
     - Dòng 4: `oc/auto` (OpenCode - Dự phòng cuối cùng không cần token).
  3. **Cơ chế**: Khi bạn gọi model `AI Agent`, hệ thống thử `cx/auto`. Nếu lỗi 429 hoặc rớt mạng, nó lập tức trong chưa tới 1 giây chuyển sang `chatgpt/auto`, cứ thế để đảm bảo luôn có kết quả trả về cho Loa thông minh.

### 5. Tab Models (Quản Lý Model)
- **Công dụng**: Hiển thị/Ẩn các model khả dụng để các ứng dụng như n8n, OpenWebUI quét được.
- **Cách sử dụng**: Bạn có thể bật (tích xanh) hoặc tắt (bỏ chọn) bất kỳ model nào bạn không muốn xuất hiện trong API `/v1/models`. Nếu bạn dùng Codex, hãy đảm bảo chọn đúng tên (như `cx/gpt-4o`).

### 6. Tab MCP Servers (Công Cụ Mở Rộng AI)
- **Công dụng**: Gắn thêm "Tay chân", "Mắt mũi" cho AI (giúp AI biết Search Google, xem thời tiết, đọc tin tức).
- **Cách kết nối với VN MCP Hub**:
  1. Mục **MCP Hub URL**: Điền `http://[IP_MÁY_CHỦ]:8005` (hoặc `http://vn-mcp-hub:8005` nếu chạy chung compose).
  2. Hệ thống sẽ tự quét ra các "Preset" như: Thời tiết, Chứng khoán, Pháp luật.
  3. Bấm **Install/Bật** các công cụ bạn thích. Khi kích hoạt, AI Agent tự động có khả năng gọi tool mỗi khi có người dùng hỏi.

### 7. Tab Backup / System
- **Công dụng**: Sao lưu cấu hình và tài khoản phòng khi chuyển máy chủ.
- **Cách dùng**: 
  - **Export**: Xuất ra file JSON toàn bộ API Key, Access Token.
  - **Import 9router Backup**: Hỗ trợ nhập file backup từ hệ thống 9router chuyên dụng cũ trực tiếp vào.

---

## 🧠 Đào Sâu Giao Diện VN MCP Hub Studio (Cơ Sở Dữ Liệu RAG)

Truy cập trang `http://[IP_MÁY_CHỦ]:8005/studio` để mở giao diện kiểm soát trí nhớ và công cụ của AI.

### 1. Tab Knowledge Base (Trí Nhớ Cục Bộ - RAG)
- **Khái niệm**: RAG (Retrieval-Augmented Generation) là kho kiến thức bạn tự dạy cho AI.
- **Cách sử dụng**:
  - Tại đây có sẵn các kho: Điện nước, Sơ cứu y tế, Luật.
  - Bạn có thể bấm **Create New KB**, tải lên file PDF tài liệu công ty hoặc file TXT hướng dẫn gia đình. Hub sẽ tự động băm nhỏ (chunking) và nhét vào Chroma DB. AI sau này sẽ tự ưu tiên tìm trong kho này trước khi tra Google.

### 2. Tab Multi-Search (Cấu Hình Tìm Kiếm)
- **Công dụng**: Chọn các Search Engine quốc tế để AI quét dữ liệu thời gian thực.
- **Cách sử dụng**: Bật/tắt các nguồn: DuckDuckGo (Mặc định ngon nhất), Brave Search (Cần dán API Key), Wikipedia. Nếu RAG cục bộ không có đáp án, Hub sẽ âm thầm gọi Search.

### 3. Tab Cloud Storage (Đồng Bộ Đám Mây)
- **Công dụng**: Nếu ổ cứng máy chủ hỏng, bạn sẽ mất công sức dạy AI. Tab này dùng Cloudflare R2 (hoặc AWS S3) để sao lưu.
- **Cách cấu hình**: Nhập Endpoint URL, Access Key, Secret Key của bucket R2. Bật chế độ tự động đồng bộ (Auto Sync) lúc 2h sáng.

---

## 🏠 Hướng Dẫn Tích Hợp Chi Tiết (Home Assistant, n8n, WebUI)

### 1. Tích Hợp Vào Home Assistant (Làm Trợ Lý Ảo)

1. Trong Home Assistant, vào **Settings** -> **Devices & Services** -> **Add Integration**.
2. Tìm kiếm **OpenAI Conversation**.
3. Điền cấu hình:
   - **API Key**: `mat_khau_cua_ban` (Biến CHATGPT2API_AUTH_KEY).
   - **Base URL**: `http://[IP_MÁY_CHỦ_CHATGPT2API]:3000/v1`
4. Bấm **Submit**. 
5. Bấm nút **Configure** trên Integration vừa thêm, chọn model là `AI Agent` (Tên Combo bạn đã tạo ở Tab Combos).

#### 🔊 Tối Ưu Hóa Giọng Nói (TTS) Cho Loa Thông Minh
Mở **Settings** -> **Voice Assistants** -> Chọn trợ lý của bạn. Ở phần **Instructions (Chỉ thị)**, dán đoạn sau để AI trả lời tự nhiên nhất:

> *"Bạn là trợ lý ảo nhà thông minh. Hãy trả lời cực kỳ ngắn gọn, tự nhiên và giống văn nói của con người để hệ thống TTS có thể đọc mượt mà. Tuyệt đối KHÔNG sử dụng các ký tự định dạng (như dấu sao *, dấu thăng #, gạch đầu dòng -). Không dùng danh sách liệt kê, hạn chế tối đa ngoặc đơn. Trả lời thẳng vào trọng tâm câu hỏi. QUAN TRỌNG: Ngay cả khi lấy dữ liệu từ Web Search hoặc MCP, tuyệt đối không được dùng định dạng liệt kê."*

### 2. Tích Hợp Open WebUI
1. Mở Admin Panel -> **Settings** -> **Connections** -> **OpenAI API**.
2. Bật công tắc kích hoạt.
3. **URL**: `http://[IP_MÁY_CHỦ_CHATGPT2API]:3000/v1`
4. **Key**: `mat_khau_cua_ban`
5. Bấm biểu tượng Refresh để nạp danh sách Model.

### 3. Tích Hợp n8n
1. Kéo node **OpenAI Chat Model**.
2. Ở phần **Credential**, tạo mới OpenAI API.
3. Điền Base URL (dưới phần Override): `http://[IP_MÁY_CHỦ_CHATGPT2API]:3000/v1`
4. Điền API Key.

---

## 🛠️ Danh Sách API Endpoints & Model Prefix

### Model Prefix
| Prefix | Nguồn cung cấp (Provider) | Ghi chú |
| :--- | :--- | :--- |
| `cx/` | Codex OAuth | Dành cho ChatGPT Pro/Plus, tự động lấy token mới. |
| `chatgpt/` | ChatGPT Web | Dành cho tài khoản Free. |
| `oc/` | OpenCode | Nguồn phụ miễn phí, không cần đăng nhập. |
| `gemini_free/` | Gemini AI Studio | Cần nhập API Key từ Google (Miễn phí). |
| `custom:...` | Custom Provider | Bất kỳ API nào hỗ trợ chuẩn OpenAI. |

---

## 🚨 Khắc Phục Sự Cố (Troubleshooting)

| Tình Trạng | Nguyên Nhân & Cách Xử Lý |
| :--- | :--- |
| **Container tự thoát liên tục (Crash loop)** | Xem log bằng lệnh: `docker logs chatgpt2api`. Thường do nhập sai cú pháp biến môi trường. |
| **Trợ lý trả lời có mã `#`, `*` đọc khó nghe** | Kiểm tra lại System Prompt trong Home Assistant. Chắc chắn đã thêm đoạn hướng dẫn không dùng định dạng. |
| **Báo lỗi 400 "Model not supported"** | Bạn đang dùng model không tồn tại. Vào Tab Combos/Models kiểm tra xem model có đúng định dạng Prefix không (VD: `chatgpt/auto`). |
| **Tài khoản ChatGPT bị Expired liên tục** | Do bạn bấm nút Log Out ở trình duyệt lúc lấy Token. Cách xử lý: Lấy lại Token mới từ Tab ẩn danh và đóng cửa sổ lại, KHÔNG Log Out. |
| **MCP Tools không phản hồi hoặc báo rỗng** | Kiểm tra URL MCP Server ở Tab MCP Servers. Test thử bằng lệnh: `curl http://[IP]:8005/health`. |
| **Ổ cứng đầy (Out of disk)** | Do log hoặc cache docker (đặc biệt là Chroma DB) cũ. Chạy lệnh: `docker system prune -af` |

---

## 🔄 Cập Nhật Phiên Bản Mới

Khi có bản cập nhật từ nhà phát triển, bạn không cần xóa dữ liệu. Chỉ cần chạy:

```bash
cd /opt/chatgpt2api
docker compose pull
docker compose up -d
```
Hệ thống sẽ tự động cập nhật image, mọi cấu hình tài khoản hay RAG của bạn đều được giữ nguyên 100%.
