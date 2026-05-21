"""MCP Presets — curated list of MCP servers ready for one-click install.

Each preset describes a publicly-accessible MCP server that chatgpt2api users
can enable with a toggle. The actual server URLs are pre-filled — users only
need to provide an API key for services that require one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPPreset:
    id: str
    name: str
    description: str
    url: str
    category: str = "general"       # vn, general, knowledge, developer, search, finance, travel, ha
    icon: str = "🔌"
    homepage: str = ""
    requires_api_key: bool = False
    api_key_help: str = ""
    tags: list[str] = field(default_factory=list)


PRESETS: list[MCPPreset] = [
    # ── VN Core (local vn-mcp-hub) ──────────────────────────────────────────
    MCPPreset(
        id="vn_weather", name="Thời tiết VN", icon="🌤️", category="vn",
        description="Thời tiết 63 tỉnh thành Việt Nam qua wttr.in. Không cần key.",
        url="http://vn-mcp-hub:8005/vn_weather/mcp",
        tags=["vietnam", "weather", "free"],
    ),
    MCPPreset(
        id="vn_news", name="Tin tức VN", icon="📰", category="vn",
        description="Tin nóng từ VnExpress, Tuổi Trẻ, Thanh Niên, Dantri qua RSS.",
        url="http://vn-mcp-hub:8005/vn_news/mcp",
        tags=["vietnam", "news", "free"],
    ),
    MCPPreset(
        id="vn_currency", name="Tỷ giá & Vàng", icon="💵", category="vn",
        description="Tỷ giá VND, giá vàng SJC, ngoại tệ từ Vietcombank.",
        url="http://vn-mcp-hub:8005/vn_currency/mcp",
        tags=["vietnam", "finance", "free"],
    ),
    MCPPreset(
        id="vn_lunar", name="Lịch Âm VN", icon="📅", category="vn",
        description="Đổi dương → âm, can chi, ngày hoàng đạo.",
        url="http://vn-mcp-hub:8005/vn_lunar/mcp",
        tags=["vietnam", "calendar", "free"],
    ),
    MCPPreset(
        id="vn_search", name="Tìm kiếm Web", icon="🔍", category="search",
        description="Tìm web qua DuckDuckGo, hỗ trợ tiếng Việt. Không cần key.",
        url="http://vn-mcp-hub:8005/vn_search/mcp",
        tags=["search", "free"],
    ),
    MCPPreset(
        id="vn_law", name="Tra cứu Luật VN", icon="⚖️", category="vn",
        description="Văn bản pháp luật Việt Nam từ thuvienphapluat.vn.",
        url="http://vn-mcp-hub:8005/vn_law/mcp",
        tags=["vietnam", "legal", "free"],
    ),
    MCPPreset(
        id="vn_phat_nguoi", name="Phạt nguội", icon="🚗", category="vn",
        description="Tra cứu phạt nguội xe từ csgt.vn.",
        url="http://vn-mcp-hub:8005/vn_phat_nguoi/mcp",
        tags=["vietnam", "traffic", "free"],
    ),
    MCPPreset(
        id="vn_stock", name="Cổ phiếu VN", icon="📈", category="vn",
        description="Giá cổ phiếu, chỉ số VN-Index, HNX từ VNDirect API.",
        url="http://vn-mcp-hub:8005/vn_stock/mcp",
        tags=["vietnam", "finance", "free"],
    ),

    # ── General (local vn-mcp-hub) ──────────────────────────────────────────
    MCPPreset(
        id="youtube", name="YouTube Transcript", icon="🎬", category="general",
        description="Lấy transcript video YouTube, hỗ trợ tiếng Việt.",
        url="http://vn-mcp-hub:8005/youtube/mcp",
        tags=["youtube", "transcript", "free"],
    ),
    MCPPreset(
        id="wikipedia", name="Wikipedia", icon="📚", category="general",
        description="Bách khoa toàn thư Wikipedia đa ngôn ngữ (mặc định tiếng Việt).",
        url="http://vn-mcp-hub:8005/wikipedia/mcp",
        tags=["knowledge", "wiki", "free"],
    ),
    MCPPreset(
        id="arxiv", name="arXiv Paper", icon="📄", category="general",
        description="Tìm paper khoa học trên arXiv.",
        url="http://vn-mcp-hub:8005/arxiv/mcp",
        tags=["science", "paper", "free"],
    ),

    # ── Knowledge Base (local vn-mcp-hub RAG) ───────────────────────────────
    MCPPreset(
        id="kb_dien_nuoc", name="Kho Điện Nước", icon="⚡", category="knowledge",
        description="Kiến thức điện, nước, điều hòa, chiller (MCB, MCCB, tính tải...).",
        url="http://vn-mcp-hub:8005/kb_dien_nuoc/mcp",
        tags=["knowledge", "mechanical", "electrical", "free"],
    ),
    MCPPreset(
        id="kb_y_te", name="Kho Y Tế", icon="🏥", category="knowledge",
        description="Kiến thức y tế cơ bản, sơ cứu, bệnh thường gặp (có disclaimer).",
        url="http://vn-mcp-hub:8005/kb_y_te/mcp",
        tags=["knowledge", "medical", "free"],
    ),
    MCPPreset(
        id="kb_giao_duc", name="Kho Giáo Dục", icon="🎓", category="knowledge",
        description="Chương trình giáo dục VN, phương pháp học tập, flashcard.",
        url="http://vn-mcp-hub:8005/kb_giao_duc/mcp",
        tags=["knowledge", "education", "free"],
    ),
    MCPPreset(
        id="kb_ngoai_ngu", name="Kho Ngoại Ngữ", icon="🗣️", category="knowledge",
        description="Từ điển, dịch thuật, ngữ pháp, luyện phát âm.",
        url="http://vn-mcp-hub:8005/kb_ngoai_ngu/mcp",
        tags=["knowledge", "language", "free"],
    ),
    MCPPreset(
        id="kb_khoa_hoc", name="Kho Khoa Học", icon="🔬", category="knowledge",
        description="Vật lý, hoá học, sinh học, toán cơ bản.",
        url="http://vn-mcp-hub:8005/kb_khoa_hoc/mcp",
        tags=["knowledge", "science", "free"],
    ),
    MCPPreset(
        id="kb_tu_nhien", name="Kho Tự Nhiên", icon="🌿", category="knowledge",
        description="Động vật, thực vật, hệ sinh thái, khí hậu, địa lý VN.",
        url="http://vn-mcp-hub:8005/kb_tu_nhien/mcp",
        tags=["knowledge", "nature", "free"],
    ),
    MCPPreset(
        id="kb_xa_hoi", name="Kho Xã Hội", icon="🏛️", category="knowledge",
        description="Lịch sử VN, văn hoá, kinh tế, chính trị, 54 dân tộc.",
        url="http://vn-mcp-hub:8005/kb_xa_hoi/mcp",
        tags=["knowledge", "history", "free"],
    ),

    # ── HA Helper ──────────────────────────────────────────────────────────
    MCPPreset(
        id="ha_helper", name="HA Helper", icon="🏠", category="ha",
        description="Helper cho Home Assistant: giờ hoàng đạo, gợi ý ngữ pháp lệnh.",
        url="http://vn-mcp-hub:8005/ha_helper/mcp",
        tags=["home-assistant", "free"],
    ),

    # ── External verified free ─────────────────────────────────────────────
    MCPPreset(
        id="deepwiki", name="DeepWiki", icon="📖", category="knowledge",
        description="Tra cứu tài liệu GitHub repo qua DeepWiki. Không cần key.",
        url="https://mcp.deepwiki.com/mcp",
        homepage="https://deepwiki.com",
        tags=["knowledge", "github", "no-auth"],
    ),
    MCPPreset(
        id="exa_search", name="Exa AI Search", icon="🌐", category="search",
        description="Search engine cho AI, semantic + keyword. Không cần key.",
        url="https://mcp.exa.ai/mcp",
        homepage="https://exa.ai",
        tags=["search", "semantic", "no-auth"],
    ),
    MCPPreset(
        id="skiplagged", name="Skiplagged Flights", icon="✈️", category="travel",
        description="Tìm vé máy bay giá rẻ. Không cần key.",
        url="https://mcp.skiplagged.com/mcp",
        homepage="https://skiplagged.com",
        tags=["travel", "flights", "no-auth"],
    ),
    MCPPreset(
        id="context7", name="Context7", icon="📝", category="developer",
        description="Tra cứu thư viện, framework docs mới nhất. Không cần key.",
        url="https://mcp.context7.com/mcp",
        homepage="https://context7.com",
        tags=["developer", "docs", "no-auth"],
    ),
    MCPPreset(
        id="coingecko", name="CoinGecko", icon="🪙", category="finance",
        description="Giá crypto, market cap, volume. Không cần key.",
        url="https://mcp.api.coingecko.com/mcp",
        homepage="https://coingecko.com",
        tags=["crypto", "finance", "no-auth"],
    ),
    MCPPreset(
        id="huggingface", name="Hugging Face", icon="🤗", category="developer",
        description="Tra cứu model, dataset, paper trên Hugging Face. Không cần key.",
        url="https://huggingface.co/mcp",
        homepage="https://huggingface.co",
        tags=["ai", "models", "no-auth"],
    ),

    # ── External free tier (cần API key tự đăng ký) ────────────────────────
    MCPPreset(
        id="github", name="GitHub", icon="🐙", category="developer",
        description="Quản lý repo, issue, PR, code search qua GitHub API.",
        url="https://api.githubcopilot.com/mcp/",
        homepage="https://github.com",
        requires_api_key=True,
        api_key_help="Tạo GitHub PAT miễn phí tại https://github.com/settings/tokens",
        tags=["developer", "git", "free-tier"],
    ),
    MCPPreset(
        id="semgrep", name="Semgrep", icon="🛡️", category="developer",
        description="Phân tích code tĩnh, tìm lỗi bảo mật. API key miễn phí.",
        url="https://mcp.semgrep.ai/mcp",
        homepage="https://semgrep.com",
        requires_api_key=True,
        api_key_help="Đăng ký miễn phí tại https://semgrep.dev",
        tags=["developer", "security", "free-tier"],
    ),
    MCPPreset(
        id="courtlistener", name="CourtListener", icon="👨‍⚖️", category="general",
        description="Tra cứu án lệ, luật pháp US. Token miễn phí.",
        url="https://mcp.courtlistener.com/mcp",
        homepage="https://courtlistener.com",
        requires_api_key=True,
        api_key_help="Đăng ký miễn phí tại https://courtlistener.com",
        tags=["legal", "us-law", "free-tier"],
    ),

    # ── GitMCP generic — wrap any GitHub MCP repo ──────────────────────────
    MCPPreset(
        id="gitmcp", name="GitMCP (Generic)", icon="🔗", category="developer",
        description="Wrap bất kỳ GitHub MCP repo nào qua gitmcp.io/{owner}/{repo}. Không cần key.",
        url="https://gitmcp.io/{owner}/{repo}",
        homepage="https://gitmcp.io",
        tags=["developer", "generic", "no-auth"],
    ),
]


def get_all() -> list[dict[str, Any]]:
    """Return all presets as plain dicts (for API responses)."""
    return [
        {
            "id": p.id, "name": p.name, "description": p.description,
            "url": p.url, "category": p.category, "icon": p.icon,
            "homepage": p.homepage, "requires_api_key": p.requires_api_key,
            "api_key_help": p.api_key_help, "tags": p.tags,
        }
        for p in PRESETS
    ]


def find(id: str) -> MCPPreset | None:
    for p in PRESETS:
        if p.id == id:
            return p
    return None
