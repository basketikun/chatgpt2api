# VN MCP Hub — Vietnamese MCP Server Hub

20+ custom MCP servers: search, weather, news, finance, law, knowledge base RAG, Home Assistant helper. Chạy cùng chatgpt2api để mở rộng khả năng AI.

**Tính năng:**
- 8 MCP VN core: thời tiết, tin tức, tỷ giá, lịch âm, search, luật, phạt nguội, cổ phiếu
- 7 Knowledge Base RAG: điện nước, y tế, giáo dục, ngoại ngữ, khoa học, tự nhiên, xã hội
- 3 General: YouTube transcript, Wikipedia, arXiv
- Federated Multi-Search: 9 search engines quốc tế song song
- Auto-update scheduler: tự động cập nhật KB theo lịch
- Cloudflare R2 storage: lưu RAG lên cloud, đồng bộ nhiều máy
- Studio UI: quản lý MCP, source toggle, tạo KB mới, cấu hình R2

## Yêu cầu hệ thống

| Môi trường | Tối thiểu | Khuyến nghị |
|-----------|----------|------------|
| RAM | 2GB | 4GB+ |
| Disk | 5GB | 20GB+ (Chroma DB + R2 cache) |
| Docker | 24.0+ | latest |

## Cài đặt nhanh

### Docker CLI
```bash
docker run -d --name vn-mcp-hub --restart unless-stopped \
  -p 8005:8005 \
  -v vn_mcp_chroma:/app/chroma_db \
  -v vn_mcp_data:/app/data \
  ghcr.io/tritue2011/vn-mcp-hub:latest
```

- Studio: `http://your-ip:8005/studio`
- Health: `http://your-ip:8005/health`

### Docker Compose
```yaml
services:
  vn-mcp-hub:
    image: ghcr.io/tritue2011/vn-mcp-hub:latest
    container_name: vn-mcp-hub
    restart: unless-stopped
    ports:
      - "8005:8005"
    volumes:
      - vn_mcp_chroma:/app/chroma_db
      - vn_mcp_data:/app/data

volumes:
  vn_mcp_chroma:
  vn_mcp_data:
```

### NAS (Synology / QNAP)

**Container Manager (Synology):**
1. Registry → tìm `vn-mcp-hub` → Download
2. Launch → Port 8005:8005, Volume `/app/chroma_db` + `/app/data`

### Portainer
1. Stacks → Add stack → paste docker-compose.yml
2. Deploy

## Cấu hình ban đầu

1. Đợi container khởi động (~30s, tự ingest Chroma)
2. Mở `http://your-ip:8005/studio`
3. **R2 Storage**: cấu hình Cloudflare R2 để đồng bộ RAG cloud
4. **MCP Servers**: tạo KB mới từ markdown, bật/tắt nguồn

## Danh sách MCP (20 built-in)

### VN Core (8)
| MCP | Mô tả |
|-----|-------|
| vn_weather | Thời tiết 4 nguồn (Open-Meteo, AccuWeather, NWS, wttr) |
| vn_news | Tin tức 6 nguồn (VnExpress, Tuổi Trẻ, Thanh Niên, Dân Trí, BBC, Google) |
| vn_currency | Tỷ giá Vietcombank, giá vàng SJC |
| vn_lunar | Lịch âm dương, can chi |
| vn_search | Tìm web DuckDuckGo |
| vn_law | Văn bản pháp luật |
| vn_phat_nguoi | Tra cứu phạt nguội |
| vn_stock | Cổ phiếu VN (VNDirect) |

### Knowledge Base RAG (7)
| KB | Nội dung |
|----|---------|
| kb_dien_nuoc | Điện, nước, điều hòa, chiller |
| kb_y_te | Y tế cơ bản, sơ cứu |
| kb_giao_duc | Giáo dục VN |
| kb_ngoai_ngu | Học ngoại ngữ |
| kb_khoa_hoc | Vật lý, hóa, sinh, toán |
| kb_tu_nhien | Động thực vật, khí hậu |
| kb_xa_hoi | Lịch sử, văn hóa, chính trị VN |

### General (3) + HA (1) + Search (1)
| MCP | Mô tả |
|-----|-------|
| youtube | Transcript YouTube |
| wikipedia | Wikipedia đa ngôn ngữ |
| arxiv | Paper khoa học |
| ha_helper | Giờ hoàng đạo, gợi ý lệnh HA |
| federated_search | Multi-search 9 nguồn quốc tế |

## Federated Multi-Search (9 nguồn)

| Backend | Quốc gia | Auth |
|---------|----------|------|
| DuckDuckGo | Global | Free |
| Wikipedia | Global | Free |
| Brave Search | US | API key (free 2000/mo) |
| Mojeek | UK | API key (free tier) |
| Semantic Scholar | US | Free |
| CrossRef | Global | Free |
| PubMed (NIH) | US | Free |
| OpenAlex | Global | Free |
| Internet Archive | US | Free |

## RAG Lifecycle

- **Khi hỏi**: RAG trước → nếu trống mới search → gợi ý "Bạn muốn tìm thêm?"
- **Scheduler**: chạy nền mỗi 1h, kiểm tra KB hết hạn → tự search cập nhật
- **R2 Sync**: đồng bộ cloud mỗi 6h, pull từ máy khác
- **Curate**: chatgpt2api tự động lưu kết quả đã tổng hợp vào RAG

## API

| Endpoint | Mô tả |
|----------|-------|
| `GET /api/rag/list` | Danh sách RAG collections |
| `GET /api/rag/export/{name}` | Export JSON (cho n8n) |
| `POST /api/rag/upload/{name}` | Upload collection lên R2 |
| `POST /api/rag/curate/{name}` | Thêm curated content |
| `POST /api/studio/kb` | Tạo KB mới |
| `POST /api/studio/validate-mcp` | Test MCP URL |
| `/<name>/mcp` | MCP JSON-RPC endpoint |

## Troubleshooting

| Vấn đề | Giải pháp |
|--------|----------|
| RAG không trả kết quả | `docker logs vn-mcp-hub \| grep RAG` |
| Search không hoạt động | Kiểm tra DNS container |
| R2 upload fail | Kiểm tra credentials trong Studio → R2 |
| Out of disk | `docker system prune -af` |

## Update

```bash
docker pull ghcr.io/tritue2011/vn-mcp-hub:latest && docker rm -f vn-mcp-hub
# Chạy lại lệnh docker run ở trên
```
